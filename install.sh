#!/usr/bin/env bash
# Hub Système — installation utilisateur (~/.local) + deps systeme (sudo)
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

APP_ID="hub-systeme"
APP_NAME="Hub Système"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="${SCRIPT_DIR}/VERSION"
VERSION="$(tr -d '[:space:]' < "${VERSION_FILE}" 2>/dev/null || echo "1.0.0")"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${HOME}/.local/bin"
INSTALL_DIR="${DATA_HOME}/${APP_ID}"
APPS_DIR="${DATA_HOME}/applications"
DESKTOP_DST="${APPS_DIR}/${APP_ID}.desktop"
LAUNCHER="${BIN_DIR}/${APP_ID}"

SKIP_DEPS=0
for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=1 ;;
    -h|--help)
      echo "Usage: bash install.sh [--skip-deps]"
      echo "  Installe ${APP_NAME} dans ${INSTALL_DIR}"
      echo "  Launcher : ~/.local/bin/${APP_ID}"
      exit 0
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

detect_os_pretty() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "${PRETTY_NAME:-${NAME:-Linux}} (${ID:-inconnu})"
  else
    echo "Linux (os-release absent)"
  fi
}

detect_pkg_family() {
  if need_cmd apt-get; then
    echo "apt (Debian/Ubuntu/Mint)"
  elif need_cmd dnf; then
    echo "dnf (Fedora/RHEL)"
  elif need_cmd pacman; then
    echo "pacman (Arch/CachyOS)"
  elif need_cmd zypper; then
    echo "zypper (openSUSE)"
  elif need_cmd apk; then
    echo "apk (Alpine)"
  else
    echo "aucun (apt/dnf/pacman/zypper/apk)"
  fi
}

flatpak_hint() {
  echo
  echo "Si GTK4 / Libadwaita ne sont pas disponibles sur cette distro, utilisez le Flatpak :"
  echo "  https://github.com/Mr-Aurevo-X/Hub-Systeme/releases"
  echo "  (runtime Flathub org.gnome.Platform 49 — compatible toutes distros)"
}

run_as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif need_cmd sudo; then
    sudo "$@"
  else
    echo "ERREUR : droits administrateur requis et sudo introuvable." >&2
    echo "Relancez en root ou installez sudo." >&2
    exit 1
  fi
}

install_deps_apt() {
  echo "==> Dependances systeme (apt)…"
  run_as_root apt-get update
  run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    python3-psutil \
    policykit-1 \
    adwaita-icon-theme
}

install_deps_dnf() {
  echo "==> Dependances systeme (dnf)…"
  run_as_root dnf install -y \
    python3 \
    python3-gobject \
    gtk4 \
    libadwaita \
    python3-psutil \
    polkit
}

install_deps_pacman() {
  echo "==> Dependances systeme (pacman)…"
  run_as_root pacman -Sy --needed --noconfirm \
    python \
    python-gobject \
    gtk4 \
    libadwaita \
    python-psutil \
    polkit
}

install_deps_zypper() {
  echo "==> Dependances systeme (zypper)…"
  run_as_root zypper --non-interactive install \
    python3 \
    python3-gobject \
    typelib-1_0-Gtk-4_0 \
    typelib-1_0-Adw-1 \
    python3-psutil \
    polkit
}

install_deps_apk() {
  echo "==> Dependances systeme (apk)…"
  run_as_root apk add --no-cache \
    python3 \
    py3-gobject3 \
    gtk4.0 \
    libadwaita \
    py3-psutil \
    polkit
}

install_system_deps() {
  if [[ "${SKIP_DEPS}" -eq 1 ]]; then
    echo "==> --skip-deps : installation des paquets ignoree."
    return 0
  fi
  if need_cmd apt-get; then
    install_deps_apt
  elif need_cmd dnf; then
    install_deps_dnf
  elif need_cmd pacman; then
    install_deps_pacman
  elif need_cmd zypper; then
    install_deps_zypper
  elif need_cmd apk; then
    install_deps_apk
  else
    echo "ATTENTION : gestionnaire de paquets non detecte (apt/dnf/pacman/zypper/apk)."
    echo "Installez manuellement : python3, PyGObject, GTK4, Libadwaita, psutil, polkit."
    flatpak_hint
  fi
}

verify_python_stack() {
  if ! need_cmd python3; then
    echo "ERREUR : python3 introuvable apres installation."
    flatpak_hint
    exit 1
  fi
  if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "ERREUR : Python 3.10+ requis (trouvé $(python3 --version 2>&1))."
    flatpak_hint
    exit 1
  fi
  if ! python3 - <<'PY'
import sys
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw  # noqa: F401
    import psutil  # noqa: F401
except Exception as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)
PY
  then
    echo "ERREUR : GTK4 / Libadwaita / psutil indisponibles pour python3."
    echo "Cause fréquente : paquets manquants ou trop anciens sur cette distro."
    echo "Relancez sans --skip-deps, ou installez les paquets listés dans packaging/COMPAT.md."
    flatpak_hint
    exit 1
  fi
}

install_app_files() {
  echo "==> Fichiers application → ${INSTALL_DIR}"
  mkdir -p "${INSTALL_DIR}" "${BIN_DIR}" "${APPS_DIR}"

  # Copie propre (sans caches / git / cursor)
  # Important: never --delete the live updates/ cache when SCRIPT_DIR lives under it
  # (self-eating rsync → "file has vanished").
  if need_cmd rsync; then
    rsync -a --delete \
      --exclude '.git/' \
      --exclude '.cursor/' \
      --exclude 'venv/' \
      --exclude '.venv/' \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      --exclude 'dist/' \
      --exclude '.pytest_cache/' \
      --exclude 'updates/' \
      "${SCRIPT_DIR}/" "${INSTALL_DIR}/"
  else
    # Fallback sans rsync — conserve updates/
    find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 ! -name 'updates' -exec rm -rf {} +
    for item in main.py VERSION LICENSE COPYRIGHT LEGAL.md README.md requirements.txt \
                LANCER.sh INSTALLER-RACCOURCI.sh Hub-Systeme.desktop \
                install.sh uninstall.sh Makefile MANIFEST \
                core ui packaging; do
      if [[ -e "${SCRIPT_DIR}/${item}" ]]; then
        cp -a "${SCRIPT_DIR}/${item}" "${INSTALL_DIR}/"
      fi
    done
    find "${INSTALL_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  fi

  chmod +x "${INSTALL_DIR}/LANCER.sh" \
           "${INSTALL_DIR}/install.sh" \
           "${INSTALL_DIR}/uninstall.sh" \
           "${INSTALL_DIR}/INSTALLER-RACCOURCI.sh" \
           "${INSTALL_DIR}/main.py" 2>/dev/null || true
}

install_launcher() {
  echo "==> Launcher → ${LAUNCHER}"
  cat > "${LAUNCHER}" << EOF
#!/usr/bin/env bash
# Launcher ${APP_NAME} (installe)
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR}"
export PYTHONPATH="\${INSTALL_DIR}\${PYTHONPATH:+:\$PYTHONPATH}"
exec bash "\${INSTALL_DIR}/LANCER.sh" "\$@"
EOF
  chmod +x "${LAUNCHER}"
}

install_desktop_entry() {
  echo "==> Entree bureau → ${DESKTOP_DST}"
  if [[ -f "${SCRIPT_DIR}/packaging/${APP_ID}.desktop" ]]; then
    sed -e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
        -e "s|@LAUNCHER@|${LAUNCHER}|g" \
        "${SCRIPT_DIR}/packaging/${APP_ID}.desktop" > "${DESKTOP_DST}"
  else
    cat > "${DESKTOP_DST}" << EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=${APP_NAME}
Comment=Gestion systeme Linux (monitoring, services, nettoyeur)
Exec=${LAUNCHER}
Path=${INSTALL_DIR}
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
StartupNotify=true
EOF
  fi
  chmod +x "${DESKTOP_DST}"
  if need_cmd update-desktop-database; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
  fi
  if need_cmd gio; then
    gio set "${DESKTOP_DST}" metadata::trusted true 2>/dev/null || true
  fi
}

ensure_path_hint() {
  case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *)
      echo
      echo "Note : ${BIN_DIR} n'est pas dans votre PATH."
      echo "Ajoutez par exemple dans ~/.bashrc :"
      echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
      ;;
  esac
}

main() {
  echo "${APP_NAME} v${VERSION} — installation native"
  echo "Source : ${SCRIPT_DIR}"
  echo "Systeme : $(detect_os_pretty)"
  echo "Paquets : $(detect_pkg_family)"
  [[ -f "${SCRIPT_DIR}/main.py" ]] || {
    echo "ERREUR : main.py introuvable. Lancez depuis le dossier extrait / clone."
    exit 1
  }

  install_system_deps
  verify_python_stack
  install_app_files
  install_launcher
  install_desktop_entry
  ensure_path_hint

  echo
  echo "OK — ${APP_NAME} v${VERSION} installe (pile GTK de cette distro)."
  echo "  App     : ${INSTALL_DIR}"
  echo "  Lancer  : ${APP_ID}"
  echo "  ou      : ${LAUNCHER}"
  echo "  ou      : bash ${INSTALL_DIR}/LANCER.sh"
  echo "Desinstaller : bash ${INSTALL_DIR}/uninstall.sh"
  echo "Flatpak (toutes distros) : https://github.com/Mr-Aurevo-X/Hub-Systeme/releases"
}

main "$@"
