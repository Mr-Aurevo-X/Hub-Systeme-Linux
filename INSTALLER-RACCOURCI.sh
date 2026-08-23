#!/usr/bin/env bash
# Crée un raccourci sur le Bureau de la VM qui lance correctement l'app
# (évite le double-clic "muet" sur le partage noexec).
set -e
SHARE="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SHARE/LANCER.sh" || ! -f "$SHARE/main.py" ]]; then
  echo "ERREUR : ce script doit être lancé depuis le dossier Hub-Systeme."
  echo "  Trouvé : $SHARE"
  echo "  Exemple :"
  echo "    bash \"$SHARE/INSTALLER-RACCOURCI.sh\""
  echo "  ou, déjà dans le dossier :"
  echo "    bash INSTALLER-RACCOURCI.sh"
  exit 1
fi
DESKTOP="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
[[ -d "$DESKTOP" ]] || DESKTOP="$HOME/Bureau"
[[ -d "$DESKTOP" ]] || DESKTOP="$HOME"

OUT="$DESKTOP/Hub-Systeme.desktop"

cat > "$OUT" << EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Hub Système
Comment=Gestion système Linux (monitoring, services, nettoyeur…)
Exec=bash "$SHARE/LANCER.sh"
Path=$SHARE
Icon=utilities-system-monitor
Terminal=true
Categories=System;Monitor;
StartupNotify=true
EOF

chmod +x "$OUT"
# Linux Mint / Cinnamon : marquer comme de confiance
gio set "$OUT" metadata::trusted true 2>/dev/null || true

echo "Raccourci créé : $OUT"
echo "Double-clique CE fichier sur le Bureau (pas le .sh du partage)."
echo "Au premier lancement, un terminal vérifie GTK4 / Libadwaita / psutil."
