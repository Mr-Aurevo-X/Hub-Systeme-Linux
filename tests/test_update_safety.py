# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import io
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core import plugins, updater


def _release_item(version: str) -> dict:
    return {
        "tag_name": f"v{version}",
        "name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "html_url": f"https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/tag/v{version}",
        "body": "notes",
        "assets": [
            {
                "name": "org.mraurevox.HubSysteme.flatpak",
                "browser_download_url": (
                    "https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/"
                    f"v{version}/org.mraurevox.HubSysteme.flatpak"
                ),
            }
        ],
    }


def test_update_channel_is_flatpak_only() -> None:
    assert updater.update_channel() == "flatpak"
    url = updater.public_download_url("1.4.11")
    assert url.endswith("org.mraurevox.HubSysteme.flatpak")
    assert "Hub-Systeme-Linux/releases/download/v" in url
    assert "linux-flatpak-releases" not in url


def test_flatpak_install_block_includes_menu_shortcut() -> None:
    info = {"version": "2.2.3", "channel": "flatpak"}
    block = updater.flatpak_install_block(info)
    assert "INSTALLER-RACCOURCI-FLATPAK.sh" in block
    assert "bash ./INSTALLER-RACCOURCI-FLATPAK.sh" in block
    assert "rm -f org.mraurevox.HubSysteme.flatpak" in block
    assert "wget --no-continue -O org.mraurevox.HubSysteme.flatpak" in block
    assert "rm -f INSTALLER-RACCOURCI-FLATPAK.sh" in block
    assert updater.SHORTCUT_DIRECT.format(version="2.2.3") in block


def test_update_urls_allow_our_github_only() -> None:
    ok_native = (
        "https://github.com/Mr-Aurevo-X/linux-releases/releases/download/"
        "Gest_Linux_Pro-v1.4.4/Gest_Linux_Pro-1.4.4.tar.gz"
    )
    ok_flatpak = (
        "https://github.com/Mr-Aurevo-X/Hub-Systeme-Linux/releases/download/"
        "v1.4.4/org.mraurevox.HubSysteme.flatpak"
    )
    ok_cdn = "https://release-assets.githubusercontent.com/github-production-release-asset/abc"
    assert updater._require_allowed_url(ok_native, kind="download") == ok_native
    assert updater._require_allowed_url(ok_flatpak, kind="download") == ok_flatpak
    assert updater._require_allowed_url(ok_cdn, kind="any") == ok_cdn
    with pytest.raises(updater.UpdateError):
        updater._require_allowed_url(ok_cdn, kind="download")
    assert updater._require_allowed_url(updater.NATIVE_RELEASES_API, kind="api") == updater.NATIVE_RELEASES_API
    assert updater._require_allowed_url(updater.FLATPAK_RELEASES_API, kind="api") == updater.FLATPAK_RELEASES_API


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/Mr-Aurevo-X/linux-releases/releases",
        "https://evil.example/malware.tar.gz",
        "https://github.com/evil/malware/releases/download/x/x.tar.gz",
        "https://api.github.com/repos/evil/malware/releases",
        "file:///etc/passwd",
        "https://user:pass@github.com/Mr-Aurevo-X/linux-releases/x",
        "https://github.com:8443/Mr-Aurevo-X/linux-releases/x",
        "javascript:alert(1)",
    ],
)
def test_update_urls_reject_backdoors(url: str) -> None:
    with pytest.raises(updater.UpdateError):
        updater._require_allowed_url(url, kind="any")


def test_write_update_script_prefers_wget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "updates_dir", lambda: tmp_path)
    url = (
        "https://github.com/Mr-Aurevo-X/linux-releases/releases/download/"
        "Gest_Linux_Pro-v1.4.8/Gest_Linux_Pro-1.4.8.tar.gz"
    )
    path = updater.write_update_script(
        {"download_url": url, "channel": "native", "version": "1.4.8"}
    )
    text = path.read_text(encoding="utf-8")
    assert "command -v wget" in text
    assert text.find("command -v wget") < text.find("command -v curl")
    assert "*curl" not in text
    assert "sudo apt install wget" in text


def test_asset_url_ignores_foreign_download() -> None:
    item = {
        "assets": [
            {
                "name": "Gest_Linux_Pro-1.4.4.tar.gz",
                "browser_download_url": "https://evil.example/backdoor.tar.gz",
            }
        ]
    }
    url = updater._asset_url(item, "1.4.4", "native")
    assert url == updater.public_download_url("1.4.4", "native")
    updater._require_allowed_url(url, kind="download")


def test_plugin_rejects_path_escape_and_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plug = tmp_path / "plugins"
    plug.mkdir()
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # plugins_dir uses XDG_DATA_HOME/hub-systeme/plugins
    real = tmp_path / "hub-systeme" / "plugins"
    real.mkdir(parents=True)
    good = real / "ok.sh"
    good.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    good.chmod(0o700)

    outside = tmp_path / "evil.sh"
    outside.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
    outside.chmod(0o700)
    link = real / "link.sh"
    os.symlink(outside, link)

    assert plugins._safe_plugin_path("ok.sh").name == "ok.sh"
    with pytest.raises(plugins.PluginError):
        plugins._safe_plugin_path("../evil.sh")
    with pytest.raises(plugins.PluginError):
        plugins._safe_plugin_path("link.sh")
    names = {p["name"] for p in plugins.list_plugins()}
    assert names == {"ok.sh"}


def test_plugin_rejects_world_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    real = tmp_path / "hub-systeme" / "plugins"
    real.mkdir(parents=True)
    bad = real / "open.sh"
    bad.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
    bad.chmod(0o707)
    with pytest.raises(plugins.PluginError):
        plugins._safe_plugin_path("open.sh")


def test_releases_latest_api_is_allowed() -> None:
    latest = updater.FLATPAK_RELEASES_LATEST_API
    assert latest.endswith("/releases/latest")
    assert updater._require_allowed_url(latest, kind="api") == latest
    compact = updater.FLATPAK_RELEASES_LIST_API
    assert "per_page=" in compact
    assert updater._require_allowed_url(compact, kind="api") == compact


def test_check_for_update_uses_latest_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "local_version", lambda: "1.1.2")
    calls: list[str] = []

    def fake_http(url: str, timeout: float = 15.0) -> object:
        calls.append(url)
        return _release_item("1.1.3")

    monkeypatch.setattr(updater, "_http_json", fake_http)
    found = updater.check_for_update()
    assert found is not None
    assert found["version"] == "1.1.3"
    assert calls[0] == updater.FLATPAK_RELEASES_LATEST_API


def test_check_for_update_falls_back_after_latest_504(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "local_version", lambda: "1.1.2")
    calls: list[str] = []

    def fake_http(url: str, timeout: float = 15.0) -> object:
        calls.append(url)
        if url.endswith("/latest"):
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", hdrs=None, fp=io.BytesIO())
        return [_release_item("1.1.3")]

    monkeypatch.setattr(updater, "_http_json", fake_http)
    found = updater.check_for_update()
    assert found is not None
    assert found["version"] == "1.1.3"
    assert calls[0] == updater.FLATPAK_RELEASES_LATEST_API
    assert updater.FLATPAK_RELEASES_LIST_API in calls


def test_http_json_retries_gateway_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        def read(self, _n: int) -> bytes:
            return b'{"ok":true}'

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *_a: object) -> bool:
            return False

    attempts = {"n": 0}

    class FakeOpener:
        def open(self, req: urllib.request.Request, timeout: float = 15.0) -> FakeResp:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise urllib.error.HTTPError(
                    req.full_url, 504, "Gateway Time-out", hdrs=None, fp=io.BytesIO()
                )
            return FakeResp()

    monkeypatch.setattr(updater, "_opener", lambda: FakeOpener())
    monkeypatch.setattr(updater.time, "sleep", lambda _s: None)
    assert updater._http_json(updater.FLATPAK_RELEASES_LATEST_API) == {"ok": True}
    assert attempts["n"] == 3
