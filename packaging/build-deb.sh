#!/usr/bin/env bash
# Hub Système - construit un .deb simple (Debian/Ubuntu)
# Installe sous /opt/hub-systeme + /usr/bin/hub-systeme + entree .desktop
# Note : install.sh (utilisateur ~/.local) reste la methode d'installation primaire.
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION" 2>/dev/null || echo "0.0.0")"
PKG_NAME="hub-systeme"
ARCH="all"
OUT_DIR="${ROOT}/dist"
STAGE="${OUT_DIR}/deb-stage"
DEB_ROOT="${STAGE}/${PKG_NAME}_${VERSION}_${ARCH}"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Erreur : commande requise manquante : $1" >&2
    echo "Installez dpkg-dev / dpkg-deb sur Debian/Ubuntu." >&2
    exit 1
  fi
}

need_cmd dpkg-deb

rm -rf "${STAGE}"
mkdir -p \
  "${DEB_ROOT}/DEBIAN" \
  "${DEB_ROOT}/opt/${PKG_NAME}" \
  "${DEB_ROOT}/usr/bin" \
  "${DEB_ROOT}/usr/share/applications" \
  "${DEB_ROOT}/usr/share/doc/${PKG_NAME}"

copy_tree() {
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude='.git' \
      --exclude='.cursor' \
      --exclude='venv' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='dist' \
      --exclude='.pytest_cache' \
      "${ROOT}/" "${DEB_ROOT}/opt/${PKG_NAME}/"
  else
    tar -C "${ROOT}" \
      --exclude='.git' \
      --exclude='.cursor' \
      --exclude='venv' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='dist' \
      --exclude='.pytest_cache' \
      -cf - . | tar -C "${DEB_ROOT}/opt/${PKG_NAME}" -xf -
  fi
}

copy_tree

cat > "${DEB_ROOT}/usr/bin/hub-systeme" << 'WRAP'
#!/usr/bin/env bash
exec python3 /opt/hub-systeme/main.py "$@"
WRAP
chmod 755 "${DEB_ROOT}/usr/bin/hub-systeme"

cat > "${DEB_ROOT}/usr/share/applications/hub-systeme.desktop" << 'DESK'
[Desktop Entry]
Type=Application
Version=1.0
Name=Hub Système
Comment=Gestion systeme Linux (monitoring, services, nettoyeur)
Exec=/usr/bin/hub-systeme
Path=/opt/hub-systeme
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
StartupNotify=true
DESK

{
  echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
  echo "Upstream-Name: Hub Système"
  echo "Source: https://github.com/Mr-Aurevo-X/Hub-Systeme"
  echo
  echo "Files: *"
  echo "Copyright: 2026 Mr-Aurevo-X"
  echo "License: GPL-3.0-or-later"
  echo
  cat "${ROOT}/LICENSE"
} > "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/copyright"
cp "${ROOT}/README.md" "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/README.md"
cp "${ROOT}/LEGAL.md" "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/LEGAL.md"
cp "${ROOT}/COPYRIGHT" "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/COPYRIGHT"
{
  echo "${PKG_NAME} (${VERSION}) unstable; urgency=medium"
  echo
  echo "  * Release ${VERSION}"
  echo
  echo " -- Mr-Aurevo-X <noreply@users.noreply.github.com>  $(date -R)"
} > "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/changelog"
gzip -9fn "${DEB_ROOT}/usr/share/doc/${PKG_NAME}/changelog"

INSTALLED_SIZE="$(du -sk "${DEB_ROOT}/opt" "${DEB_ROOT}/usr" | awk '{s+=$1} END {print s}')"
cat > "${DEB_ROOT}/DEBIAN/control" << CTRL
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Mr-Aurevo-X <noreply@users.noreply.github.com>
Depends: python3, python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, python3-psutil, policykit-1
Recommends: timeshift, snapper, flatpak, adwaita-icon-theme
Homepage: https://github.com/Mr-Aurevo-X/Hub-Systeme
Description: Utilitaire de gestion systeme Linux (GTK4 / Libadwaita)
 Hub Système offre monitoring, processus, services systemd, nettoyeur,
 paquets, journaux, reseau, securite, alertes et plus.
 Installation primaire recommandee : bash install.sh (utilisateur).
 Ce paquet place l'application sous /opt/hub-systeme.
CTRL

find "${DEB_ROOT}" -type d -exec chmod 755 {} +
find "${DEB_ROOT}/opt/${PKG_NAME}" -type f -exec chmod 644 {} +
chmod 755 \
  "${DEB_ROOT}/opt/${PKG_NAME}/main.py" \
  "${DEB_ROOT}/opt/${PKG_NAME}/install.sh" \
  "${DEB_ROOT}/opt/${PKG_NAME}/uninstall.sh" \
  "${DEB_ROOT}/opt/${PKG_NAME}/LANCER.sh" \
  "${DEB_ROOT}/opt/${PKG_NAME}/INSTALLER-RACCOURCI.sh" \
  "${DEB_ROOT}/usr/bin/hub-systeme"
if [[ -f "${DEB_ROOT}/opt/${PKG_NAME}/packaging/build-deb.sh" ]]; then
  chmod 755 "${DEB_ROOT}/opt/${PKG_NAME}/packaging/build-deb.sh"
fi

mkdir -p "${OUT_DIR}"
DEB_FILE="${OUT_DIR}/${PKG_NAME}_${VERSION}_${ARCH}.deb"

if command -v fakeroot >/dev/null 2>&1; then
  fakeroot dpkg-deb --build --root-owner-group "${DEB_ROOT}" "${DEB_FILE}"
else
  dpkg-deb --build --root-owner-group "${DEB_ROOT}" "${DEB_FILE}"
fi

echo "OK -> ${DEB_FILE}"
ls -lh "${DEB_FILE}"
