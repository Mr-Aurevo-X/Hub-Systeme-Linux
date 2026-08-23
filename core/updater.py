# SPDX-License-Identifier: GPL-3.0-or-later
"""Public-channel auto-update (Flatpak only, no GitHub token)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import ssl
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from core import host

log = logging.getLogger("gest.updater")

Channel = Literal["flatpak", "native"]

GEST_REPO = "Mr-Aurevo-X/Hub-Systeme-Linux"
FLATPAK_RELEASES_API = f"https://api.github.com/repos/{GEST_REPO}/releases"
FLATPAK_PUBLIC_RELEASES = f"https://github.com/{GEST_REPO}/releases"
FLATPAK_ASSET = "org.mraurevox.HubSysteme.flatpak"
SHORTCUT_ASSET = "INSTALLER-RACCOURCI-FLATPAK.sh"
FLATPAK_DIRECT = (
    f"https://github.com/{GEST_REPO}/releases/download/"
    "v{version}/" + FLATPAK_ASSET
)
SHORTCUT_DIRECT = (
    f"https://github.com/{GEST_REPO}/releases/download/"
    "v{version}/" + SHORTCUT_ASSET
)

NATIVE_RELEASES_API = "https://api.github.com/repos/Mr-Aurevo-X/linux-releases/releases"
NATIVE_PUBLIC_RELEASES = "https://github.com/Mr-Aurevo-X/linux-releases/releases"
NATIVE_ASSET_TMPL = "Gest_Linux_Pro-{version}.tar.gz"
NATIVE_DIRECT = (
    "https://github.com/Mr-Aurevo-X/linux-releases/releases/download/"
    "Gest_Linux_Pro-v{version}/" + NATIVE_ASSET_TMPL
)

APP_ID = "org.mraurevox.HubSysteme"
TAG_PREFIX = "v"
_TAG_RE = re.compile(r"(?:Gest_Linux_Pro-v|v)(\d+\.\d+\.\d+)")
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_NOTES_MAX = 480

# Back-compat aliases (Flatpak channel defaults)
RELEASES_API = FLATPAK_RELEASES_API
PUBLIC_RELEASES = FLATPAK_PUBLIC_RELEASES
ASSET_NAME = FLATPAK_ASSET
DIRECT_URL = (
    f"https://github.com/{GEST_REPO}/releases/download/"
    f"v{{version}}/{FLATPAK_ASSET}"
)

# Only GitHub public release APIs + their HTTPS CDNs. No other host, ever.
_ALLOWED_API_URLS = frozenset({FLATPAK_RELEASES_API, NATIVE_RELEASES_API})
_ALLOWED_GITHUB_PATH_PREFIXES = (
    f"/repos/{GEST_REPO}/",
    f"/{GEST_REPO}/",
    "/repos/Mr-Aurevo-X/linux-releases/",
    "/Mr-Aurevo-X/linux-releases/",
)
_CDN_HOSTS = frozenset(
    {
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "github-releases.githubusercontent.com",
    }
)
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_BUNDLE_BYTES = 80 * 1024 * 1024


class UpdateError(Exception):
    """Raised when download or install fails after an update was offered."""


def _require_allowed_url(url: str, *, kind: Literal["api", "download", "any"] = "any") -> str:
    """Reject anything that is not HTTPS GitHub (API, our repos, or release CDN)."""
    text = (url or "").strip()
    if not text:
        raise UpdateError("URL vide")
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme != "https":
        raise UpdateError("URL non HTTPS refusée")
    if parsed.username or parsed.password:
        raise UpdateError("URL avec identifiants refusée")
    host = (parsed.hostname or "").lower()
    if parsed.port not in (None, 443):
        raise UpdateError("Port non autorisé")
    path = parsed.path or "/"

    if kind in ("api", "any") and text in _ALLOWED_API_URLS:
        return text
    if kind == "api":
        raise UpdateError("API de mise à jour non autorisée")

    github_ok = host in {"github.com", "api.github.com"} and any(
        path.startswith(prefix) for prefix in _ALLOWED_GITHUB_PATH_PREFIXES
    )
    if kind == "download":
        if github_ok:
            return text
        raise UpdateError(f"Hôte ou dépôt non autorisé : {host}{path}")

    if github_ok or host in _CDN_HOSTS:
        return text
    raise UpdateError(f"Hôte ou dépôt non autorisé : {host}{path}")


class _BlockHttpHandler(urllib.request.BaseHandler):
    def http_open(self, req: urllib.request.Request) -> Any:
        raise urllib.error.URLError("HTTP clair interdit")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _require_allowed_url(str(newurl), kind="any")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        _BlockHttpHandler(),
        _SafeRedirectHandler(),
        urllib.request.HTTPSHandler(context=_ssl_context()),
    )


def update_channel() -> Channel:
    """Public channel is Flatpak only. Native tar.gz is no longer shipped."""
    return "flatpak"


def local_version() -> str:
    candidates: list[Path] = []
    if host.is_flatpak():
        candidates.append(Path("/app/share/hub-systeme/VERSION"))
    candidates.append(Path(__file__).resolve().parent.parent / "VERSION")
    if not host.is_flatpak():
        candidates.append(Path.home() / ".local" / "share" / "hub-systeme" / "VERSION")
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return "0.0.0"


def parse_semver(version: str) -> tuple[int, int, int] | None:
    match = _SEMVER_RE.fullmatch(version.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def version_from_release(tag: str, name: str = "") -> str | None:
    for text in (tag, name):
        match = _TAG_RE.search(text or "")
        if match:
            return match.group(1)
    if tag.startswith("v") and parse_semver(tag[1:].strip()):
        return tag[1:].strip()
    if tag.startswith(TAG_PREFIX):
        rest = tag[len(TAG_PREFIX) :].strip()
        if parse_semver(rest):
            return rest
    return None


def updates_dir() -> Path:
    """Host-visible cache (not sandbox XDG_DATA_HOME)."""
    path = Path.home() / ".local" / "share" / "hub-systeme" / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_download_url(version: str, channel: Channel | None = None) -> str:
    ch = channel or update_channel()
    if ch == "flatpak":
        return FLATPAK_DIRECT.format(version=version)
    return NATIVE_DIRECT.format(version=version)


def restart_hint(channel: Channel | None = None) -> str:
    ch = channel or update_channel()
    if ch == "flatpak":
        return f"flatpak run {APP_ID}"
    return "hub-systeme"


def flatpak_install_block(info: dict[str, Any]) -> str:
    version = str(info.get("version") or "")
    url = str(info.get("download_url") or public_download_url(version, "flatpak"))
    asset = str(info.get("asset_name") or FLATPAK_ASSET)
    shortcut_url = str(info.get("shortcut_url") or SHORTCUT_DIRECT.format(version=version))
    return (
        f"rm -f {asset}\n"
        f"wget --no-continue -O {asset} \\\n  {url}\n"
        f"flatpak install --user -y --reinstall ./{asset}\n"
        f"rm -f {SHORTCUT_ASSET}\n"
        f"wget --no-continue -O {SHORTCUT_ASSET} \\\n  {shortcut_url}\n"
        f"bash ./{SHORTCUT_ASSET}\n"
        f"flatpak run {APP_ID}"
    )


def format_update_dialog_commands(info: dict[str, Any]) -> str:
    channel = str(info.get("channel") or update_channel())
    if channel == "flatpak":
        return flatpak_install_block(info)
    latest = str(info.get("version") or "?")
    url = str(info.get("download_url") or public_download_url(latest, "native"))
    asset = str(info.get("asset_name") or _asset_name("native", latest))
    return f"curl -fL -o {asset} \\\n  {url}"


def format_update_dialog_body(info: dict[str, Any]) -> str:
    latest = str(info.get("version") or "?")
    current = str(info.get("current") or local_version())
    release_url = str(info.get("html_url") or PUBLIC_RELEASES)
    parts = [
        f"Hub Système {latest} disponible (vous avez {current}).",
        "",
        f"Release : {release_url}",
    ]
    notes = str(info.get("notes") or "").strip()
    if notes:
        parts.extend(["", notes])
    return "\n".join(parts)


def app_display_name() -> str:
    return f"Hub Système {local_version()}"


def _user_agent() -> str:
    return f"HubSysteme/{local_version()}"


def _http_json(url: str, timeout: float = 15.0) -> Any:
    _require_allowed_url(url, kind="api")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "application/vnd.github+json",
        },
    )
    with _opener().open(req, timeout=timeout) as resp:
        raw = resp.read(_MAX_JSON_BYTES + 1)
    if len(raw) > _MAX_JSON_BYTES:
        raise UpdateError("Réponse de mise à jour trop volumineuse")
    return json.loads(raw.decode("utf-8"))


def _snippet(body: str | None) -> str:
    text = (body or "").strip().replace("\r\n", "\n")
    if not text:
        return ""
    if len(text) > _NOTES_MAX:
        return text[: _NOTES_MAX - 1].rstrip() + "…"
    return text


def _asset_name(channel: Channel, version: str) -> str:
    if channel == "flatpak":
        return FLATPAK_ASSET
    return NATIVE_ASSET_TMPL.format(version=version)


def _asset_url(item: dict[str, Any], version: str, channel: Channel) -> str:
    wanted = _asset_name(channel, version)
    for asset in item.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != wanted:
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if not url:
            continue
        try:
            return _require_allowed_url(url, kind="download")
        except UpdateError:
            continue
    return public_download_url(version, channel)


def check_for_update(*, raise_on_error: bool = False) -> dict[str, Any] | None:
    """Return latest newer Gest release for the active channel, or None."""
    channel = update_channel()
    api = FLATPAK_RELEASES_API if channel == "flatpak" else NATIVE_RELEASES_API
    public = FLATPAK_PUBLIC_RELEASES if channel == "flatpak" else NATIVE_PUBLIC_RELEASES
    try:
        payload = _http_json(api)
    except urllib.error.HTTPError as exc:
        log.info("update check skipped (HTTP %s, channel=%s)", exc.code, channel)
        if raise_on_error:
            raise UpdateError(f"HTTP {exc.code}") from exc
        return None
    except UpdateError:
        if raise_on_error:
            raise
        log.info("update check skipped (url refusée, channel=%s)", channel)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        log.info("update check skipped (%s, channel=%s)", exc, channel)
        if raise_on_error:
            raise UpdateError(str(exc)) from exc
        return None

    if not isinstance(payload, list):
        if raise_on_error:
            raise UpdateError("Réponse invalide du canal de mises à jour")
        return None

    current = local_version()
    current_tuple = parse_semver(current) or (0, 0, 0)
    best: dict[str, Any] | None = None
    best_tuple = current_tuple

    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("draft") or item.get("prerelease"):
            continue
        tag = str(item.get("tag_name") or "")
        name = str(item.get("name") or "")
        version = version_from_release(tag, name)
        if version is None:
            continue
        parsed = parse_semver(version)
        if parsed is None or parsed <= best_tuple:
            continue
        # Prefer releases that actually ship the expected asset.
        url = _asset_url(item, version, channel)
        try:
            url = _require_allowed_url(url, kind="download")
        except UpdateError:
            continue
        if channel == "native" and not url.split("?", 1)[0].endswith(".tar.gz"):
            continue
        if channel == "flatpak" and not url.split("?", 1)[0].endswith(".flatpak"):
            continue
        best_tuple = parsed
        best = {
            "version": version,
            "current": current,
            "tag": tag or f"{TAG_PREFIX}{version}",
            "name": name,
            "notes": _snippet(str(item.get("body") or "")),
            "html_url": str(item.get("html_url") or public),
            "download_url": url,
            "channel": channel,
            "asset_name": _asset_name(channel, version),
        }

    return best


def download_bundle(url: str, dest: Path | None = None) -> Path:
    safe_url = _require_allowed_url(url, kind="download")
    if dest is None:
        dest = updates_dir() / "update.bin"
    target = dest
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    req = urllib.request.Request(
        safe_url,
        headers={"User-Agent": _user_agent(), "Accept": "application/octet-stream"},
    )
    written = 0
    try:
        with _opener().open(req, timeout=120) as resp, tmp.open("wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_BUNDLE_BYTES:
                    raise UpdateError("Fichier de mise à jour trop volumineux")
                out.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError, UpdateError) as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"Téléchargement impossible : {exc}") from exc
    if tmp.stat().st_size <= 0:
        tmp.unlink(missing_ok=True)
        raise UpdateError("Fichier de mise à jour vide")
    tmp.replace(target)
    return target


def install_flatpak_bundle(path: Path) -> None:
    bundle = path.expanduser().resolve()
    if not bundle.is_file():
        raise UpdateError(f"Paquet introuvable : {bundle}")
    if not bundle.read_bytes()[:7].startswith(b"flatpak"):
        raise UpdateError("Fichier Flatpak invalide (magic)")
    exe = host.which("flatpak") or "flatpak"
    completed = host.run(
        [exe, "install", "--user", "-y", str(bundle)],
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=host.host_cwd(),
    )
    if completed.returncode == 0:
        return
    err = (completed.stderr or completed.stdout or "flatpak install a échoué").strip()
    raise UpdateError(err)


def _find_extract_root(extract_dir: Path) -> Path:
    children = [p for p in extract_dir.iterdir() if p.is_dir()]
    for child in children:
        if (child / "install.sh").is_file() and (child / "main.py").is_file():
            return child
    if (extract_dir / "install.sh").is_file() and (extract_dir / "main.py").is_file():
        return extract_dir
    raise UpdateError("Archive native invalide : install.sh / main.py introuvables")


def install_native_tarball(path: Path) -> None:
    archive = path.expanduser().resolve()
    if not archive.is_file():
        raise UpdateError(f"Archive introuvable : {archive}")
    # Extract outside the live install tree — rsync --delete into
    # ~/.local/share/hub-systeme would delete a nested source mid-copy.
    work = Path(tempfile.mkdtemp(prefix="gest-update-"))
    try:
        try:
            with tarfile.open(archive, "r:gz") as tar:
                # Python 3.12+: refuse suspicious members when available.
                extract_kw: dict[str, Any] = {}
                if hasattr(tarfile, "data_filter"):
                    extract_kw["filter"] = "data"
                tar.extractall(work, **extract_kw)
        except (tarfile.TarError, OSError) as exc:
            raise UpdateError(f"Extraction impossible : {exc}") from exc
        root = _find_extract_root(work)
        install_sh = root / "install.sh"
        completed = host.run(
            ["bash", str(install_sh), "--skip-deps"],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(root),
        )
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "install.sh a échoué").strip()
            raise UpdateError(err)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_bundle(path: Path, channel: Channel | None = None) -> None:
    ch = channel or update_channel()
    if ch == "flatpak":
        install_flatpak_bundle(path)
    else:
        install_native_tarball(path)


def apply_update(info: dict[str, Any]) -> Path:
    url = _require_allowed_url(str(info.get("download_url") or ""), kind="download")
    channel: Channel = "flatpak"
    raw_ch = str(info.get("channel") or update_channel())
    if raw_ch in ("flatpak", "native"):
        channel = raw_ch  # type: ignore[assignment]
    version = str(info.get("version") or "").strip()
    if parse_semver(version) is None:
        raise UpdateError("Version de mise à jour invalide")
    dest = updates_dir() / _asset_name(channel, version)
    bundle = download_bundle(url, dest=dest)
    install_bundle(bundle, channel=channel)
    return bundle


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _shell_download_cmd(url: str, dest: Path) -> str:
    """wget first (Mint 21 often has no curl), then curl. Never emit a glob like *curl."""
    q_url = _shell_quote(url)
    q_dest = _shell_quote(str(dest))
    return "\n".join(
        [
            "if command -v wget >/dev/null 2>&1; then",
            f"  wget --no-continue -O {q_dest} --https-only --max-redirect=8 --timeout=30 --quota=80m {q_url}",
            "elif command -v curl >/dev/null 2>&1; then",
            (
                "  curl -fL --proto '=https' --tlsv1.2 "
                f"--max-filesize {_MAX_BUNDLE_BYTES} --progress-bar -o {q_dest} {q_url}"
            ),
            "else",
            '  echo "ERREUR : ni wget ni curl. Mint/Ubuntu : sudo apt install wget" >&2',
            "  exit 1",
            "fi",
        ]
    )


def write_check_report_script(
    *,
    info: dict[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    """Terminal script that shows the update-check result (and optional install)."""
    script = updates_dir() / "run-check.sh"
    current = local_version()
    channel = update_channel()
    canal = "Flatpak" if channel == "flatpak" else "natif"
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'echo "=========================================="',
        'echo " Hub Système — vérification MAJ"',
        'echo "=========================================="',
        "echo",
        f'echo "Version locale : {current}"',
        f'echo "Canal         : {canal}"',
        "echo",
    ]
    if error:
        lines += [
            'echo "Résultat : ÉCHEC"',
            f"echo {_shell_quote(error)}",
            "echo",
        ]
    elif info is None:
        lines += [
            'echo "Résultat : déjà à jour."',
            "echo",
        ]
    else:
        latest = str(info.get("version") or "?")
        notes = str(info.get("notes") or "").strip()
        update_script = write_update_script(info)
        q_upd = _shell_quote(str(update_script.resolve()))
        flag = updates_dir() / "proceed-install"
        q_flag = _shell_quote(str(flag.resolve()))
        try:
            flag.unlink(missing_ok=True)
        except OSError:
            pass
        lines += [
            f'echo "Résultat : mise à jour {latest} disponible."',
            "echo",
        ]
        if notes:
            lines += [f"echo {_shell_quote(notes)}", "echo"]
        lines += [
            'echo "Installation dans ce terminal (recommandé)."',
            'read -r -p "Installer maintenant ? [O/n] " ans || true',
            'ans="${ans:-O}"',
            'if [[ "${ans}" == [nN]* ]]; then',
            '  echo "Annulé."',
            "  exit 0",
            "fi",
            f"touch {q_flag}",
            "echo",
            'echo "L\'application va se fermer, puis installation…"',
            "sleep 1",
            f"bash {q_upd}",
            "echo",
        ]
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def write_update_script(info: dict[str, Any]) -> Path:
    """Write a visible bash updater that downloads, installs, then relaunches."""
    url = _require_allowed_url(str(info.get("download_url") or "").strip(), kind="download")
    channel: Channel = "flatpak"
    raw_ch = str(info.get("channel") or update_channel())
    if raw_ch in ("flatpak", "native"):
        channel = raw_ch  # type: ignore[assignment]
    version = str(info.get("version") or "?").strip() or "?"
    if parse_semver(version) is None:
        raise UpdateError("Version de mise à jour invalide")
    dest = updates_dir() / _asset_name(channel, version)
    shortcut_dest = updates_dir() / SHORTCUT_ASSET
    script = updates_dir() / "run-update.sh"
    # /tmp — never extract under ~/.local/share/hub-systeme (rsync self-delete).
    work = Path(tempfile.gettempdir()) / f"gest-update-{version}"
    download = _shell_download_cmd(url, dest)
    shortcut_url = SHORTCUT_DIRECT.format(version=version)
    download_shortcut = _shell_download_cmd(shortcut_url, shortcut_dest)

    if channel == "flatpak":
        body = f"""#!/usr/bin/env bash
set -euo pipefail
echo "=========================================="
echo " Hub Système — mise à jour Flatpak {version}"
echo "=========================================="
echo
echo "==> Téléchargement…"
{download}
echo
echo "==> Installation Flatpak (utilisateur)…"
flatpak install --user -y {_shell_quote(str(dest))}
echo
echo "==> Raccourci menu…"
{download_shortcut}
bash {_shell_quote(str(shortcut_dest))}
echo
echo "==> Relance de l'application…"
nohup flatpak run {APP_ID} >/dev/null 2>&1 &
sleep 1
echo
echo "OK — Hub Système {version} installé."
echo "Vous pouvez fermer ce terminal."
"""
    else:
        body = f"""#!/usr/bin/env bash
set -euo pipefail
echo "=========================================="
echo " Hub Système — mise à jour native {version}"
echo "=========================================="
echo
echo "==> Téléchargement…"
{download}
echo
echo "==> Extraction…"
rm -rf {_shell_quote(str(work))}
mkdir -p {_shell_quote(str(work))}
tar -xzf {_shell_quote(str(dest))} -C {_shell_quote(str(work))}
ROOT="$(find {_shell_quote(str(work))} -maxdepth 2 -type f -name install.sh | head -n1 | xargs -r dirname)"
if [[ -z "${{ROOT}}" || ! -f "${{ROOT}}/install.sh" ]]; then
  echo "ERREUR : install.sh introuvable dans l'archive." >&2
  exit 1
fi
echo "==> Installation (install.sh --skip-deps)…"
bash "${{ROOT}}/install.sh" --skip-deps
rm -rf {_shell_quote(str(work))}
echo
echo "==> Relance de l'application…"
if command -v hub-systeme >/dev/null 2>&1; then
  nohup hub-systeme >/dev/null 2>&1 &
elif [[ -x "$HOME/.local/bin/hub-systeme" ]]; then
  nohup "$HOME/.local/bin/hub-systeme" >/dev/null 2>&1 &
elif [[ -f "$HOME/.local/share/hub-systeme/LANCER.sh" ]]; then
  nohup bash "$HOME/.local/share/hub-systeme/LANCER.sh" >/dev/null 2>&1 &
else
  echo "ATTENTION : lanceur introuvable — relancez manuellement hub-systeme."
fi
sleep 1
echo
echo "OK — Hub Système {version} installé."
echo "Vous pouvez fermer ce terminal."
"""

    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def _terminal_commands(script: Path) -> list[list[str]]:
    path = str(script.resolve())
    hold = (
        f"bash {_shell_quote(path)}; echo; "
        "echo 'Appuyez sur Entrée pour fermer…'; read -r _ || true"
    )
    hold_q = _shell_quote(hold)
    # Prefer Konsole so the user always sees check/install progress.
    return [
        ["konsole", "--hide-menubar", "-e", "bash", "-lc", hold],
        ["xdg-terminal-exec", "--", "bash", "-lc", hold],
        ["gnome-terminal", "--", "bash", "-lc", hold],
        ["kgx", "-e", "bash", "-lc", hold],
        ["xfce4-terminal", "-e", f"bash -lc {hold_q}"],
        ["mate-terminal", "-e", f"bash -lc {hold_q}"],
        ["xterm", "-hold", "-e", "bash", path],
    ]


def _maybe_host(cmd: list[str]) -> list[str]:
    if not host.is_flatpak():
        return cmd
    home = str(Path.home())
    return ["flatpak-spawn", "--host", f"--directory={home}", "--", *cmd]


def open_terminal_script(script: Path) -> None:
    """Open Konsole (or another terminal) running the script; do not wait for exit."""
    import subprocess
    import time

    last_err = "aucun terminal trouvé"
    for cmd in _terminal_commands(script):
        wrapped = _maybe_host(cmd)
        probe = wrapped[0]
        if probe not in {"flatpak-spawn", "xdg-terminal-exec"}:
            if host.which(probe) is None:
                continue
        try:
            proc = subprocess.Popen(
                wrapped,
                start_new_session=True,
                cwd=str(Path.home()),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            last_err = str(exc)
            continue
        time.sleep(0.35)
        code = proc.poll()
        if code in (None, 0):
            return
        last_err = f"{probe} code {code}"
    raise UpdateError(
        "Impossible d'ouvrir Konsole pour suivre la mise à jour "
        f"({last_err}). Installez konsole."
    )


def launch_check_terminal(
    *,
    info: dict[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    """Show update-check result in Konsole; may install if the user confirms."""
    script = write_check_report_script(info=info, error=error)
    open_terminal_script(script)
    return script


def launch_update_terminal(info: dict[str, Any]) -> Path:
    """Prepare and open the update terminal; caller should quit the app."""
    script = write_update_script(info)
    open_terminal_script(script)
    return script
