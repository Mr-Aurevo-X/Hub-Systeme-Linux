#!/usr/bin/env bash
# Crée / met à jour le raccourci menu Hub Système (installation Flatpak).
set -euo pipefail

APP_ID="org.mraurevox.HubSysteme"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
EXPORT="${XDG_DATA_HOME:-$HOME/.local/share}/flatpak/exports/share/applications/${APP_ID}.desktop"
DESKTOP="${APPS}/${APP_ID}.desktop"

mkdir -p "${APPS}"

if [[ -f "${EXPORT}" ]]; then
  cp -f "${EXPORT}" "${DESKTOP}"
else
  cat > "${DESKTOP}" << EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Hub Système
Comment=Gestion système Linux (santé, monitoring, paquets, clichés)
Comment[en]=Linux system manager (monitoring, services, cleaner)
Exec=flatpak run ${APP_ID}
Icon=${APP_ID}
Terminal=false
Categories=System;Monitor;
StartupNotify=true
StartupWMClass=${APP_ID}
EOF
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APPS}" 2>/dev/null || true
fi

echo "Raccourci menu créé : ${DESKTOP}"
