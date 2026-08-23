#!/usr/bin/env bash
# Lance Hub Système.
# - code sur le partage (souvent noexec) → toujours via bash + python3 système
# - GTK4 / Libadwaita / PyGObject viennent des paquets apt (pas d'un venv)
# - logs en local XDG

set +e
SHARE="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SHARE/main.py" ]]; then
  echo "ERREUR : main.py introuvable dans $SHARE"
  echo "Sur la VM VirtualBox, le partage est sous /media/sf_Partage_VM/… (pas /mnt/d/…)."
  echo "Depuis le dossier projet : bash LANCER.sh"
  exit 1
fi
LOCAL="${XDG_DATA_HOME:-$HOME/.local/share}/hub-systeme"
LOG="$LOCAL/launch.log"

mkdir -p "$LOCAL"
chmod 700 "$LOCAL" 2>/dev/null || true
touch "$LOG"
chmod 600 "$LOG" 2>/dev/null || true

exec > >(tee -a "$LOG") 2>&1

echo "========== $(date) =========="
echo "SHARE=$SHARE"
echo "LOCAL=$LOCAL"
echo

pause() {
  echo
  echo "Appuie sur Entrée pour fermer…"
  if [[ -r /dev/tty ]]; then
    read -r _ </dev/tty
  else
    sleep 8
  fi
}

need_pkg() {
  echo "ERREUR : dépendance manquante — $1"
  echo
  echo "Installe les paquets système adaptés à ta distribution :"
  echo "  Debian/Ubuntu/Mint : sudo apt update && sudo apt install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-psutil policykit-1 adwaita-icon-theme"
  echo "  Fedora        : sudo dnf install -y python3 python3-gobject gtk4 libadwaita python3-psutil polkit"
  echo "  Arch/CachyOS  : sudo pacman -Sy --needed python python-gobject gtk4 libadwaita python-psutil polkit"
  echo "  openSUSE      : sudo zypper install python3 python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 python3-psutil polkit"
  echo "  Alpine        : sudo apk add python3 py3-gobject3 gtk4.0 libadwaita py3-psutil polkit"
  pause
  exit 1
}

command -v python3 >/dev/null || need_pkg "python3"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || need_pkg "python3 >= 3.10"

cd "$SHARE" || { pause; exit 1; }
export PYTHONPATH="$SHARE${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Same logic as core/display_env.py — CachyOS/Arch bare metal: no GSK/GDK/LIBGL.
# Mint/jammy/VM fallbacks stay gated; re-export KEY=VALUE only when applied.
while IFS= read -r _line; do
  [[ -z "${_line}" ]] && continue
  export "${_line}"
  echo "${_line}"
done < <(python3 -c 'from core.display_env import apply_safe_display_env
for k, v in apply_safe_display_env().items():
    print(f"{k}={v}")')

# cairo GI is required only when the cairo renderer was actually applied.
if [[ "${GSK_RENDERER:-}" == "cairo" ]]; then
python3 - <<'PY' || { echo "ERREUR : module cairo introuvable (PyGObject cairo)."; echo "  Debian/Ubuntu/Mint : sudo apt install python3-gi-cairo python3-cairo"; pause; exit 1; }
import sys
ok = False
try:
    import gi
    from gi.repository import cairo  # noqa: F401
    ok = True
except Exception:
    pass
if not ok:
    try:
        import cairo  # noqa: F401
        ok = True
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
if not ok:
    sys.exit(1)
PY
fi

python3 - <<'PY' || need_pkg "python3-gi / GTK4 / Libadwaita / psutil"
import sys
try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, Adw  # noqa: F401
    import psutil  # noqa: F401
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
PY

echo "Python : $(command -v python3)"
echo "Démarrage UI…"

python3 "$SHARE/main.py"
CODE=$?
echo "exit=$CODE"
if [[ $CODE -ne 0 ]]; then
  echo "Erreur — détails dans $LOG"
  pause
  exit "$CODE"
fi
exit 0
