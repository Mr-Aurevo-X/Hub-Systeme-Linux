#!/usr/bin/env bash
# Publie le .flatpak Gest sur Mr-Aurevo-X/Hub-Systeme (tag vX.Y.Z).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_REPO="Mr-Aurevo-X/Hub-Systeme"
APP_ID="org.mraurevox.HubSysteme"

FROM_DIR=""
FILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-dir)
      FROM_DIR="${2:?}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,5p' "$0"
      exit 0
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION" 2>/dev/null || true)"
if [[ -z "${VERSION}" ]]; then
  echo "ERREUR : VERSION introuvable."
  exit 1
fi

TAG="v${VERSION}"
TITLE="Hub Système ${VERSION}"
LEGAL_NOTES=""
if [[ -f "${ROOT}/packaging/public-legal-notes.md" ]]; then
  LEGAL_NOTES="$(cat "${ROOT}/packaging/public-legal-notes.md")"
fi
NOTES="$(cat <<EOF
## Hub Système ${VERSION}

Notification MAJ avec commandes curl / flatpak copiables (pas d’install auto dans l’app).

\`\`\`bash
wget -O ${APP_ID}.flatpak \\
  https://github.com/${PUBLIC_REPO}/releases/download/${TAG}/${APP_ID}.flatpak
flatpak install --user -y --reinstall ./${APP_ID}.flatpak
wget -O INSTALLER-RACCOURCI-FLATPAK.sh \\
  https://github.com/${PUBLIC_REPO}/releases/download/${TAG}/INSTALLER-RACCOURCI-FLATPAK.sh
bash ./INSTALLER-RACCOURCI-FLATPAK.sh
flatpak run ${APP_ID}
\`\`\`

${LEGAL_NOTES}
EOF
)"

if [[ -n "${FROM_DIR}" ]]; then
  while IFS= read -r -d '' f; do
    FILES+=("$f")
  done < <(find "${FROM_DIR}" -type f -name "${APP_ID}*.flatpak" -print0)
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  unversioned="${ROOT}/dist/${APP_ID}.flatpak"
  versioned="${ROOT}/dist/${APP_ID}-${VERSION}.flatpak"
  if [[ ! -f "${unversioned}" && -f "${versioned}" ]]; then
    cp "${versioned}" "${unversioned}"
  fi
  if [[ -f "${unversioned}" ]]; then
    FILES+=("${unversioned}")
  fi
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERREUR : aucun .flatpak (bash packaging/build-flatpak.sh)."
  exit 1
fi

if [[ -f "${ROOT}/LEGAL.md" ]]; then
  FILES+=("${ROOT}/LEGAL.md")
fi
if [[ -f "${ROOT}/INSTALLER-RACCOURCI-FLATPAK.sh" ]]; then
  FILES+=("${ROOT}/INSTALLER-RACCOURCI-FLATPAK.sh")
fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "manque: $1" >&2; exit 1; }; }
need gh

echo "==> ${PUBLIC_REPO} tag=${TAG}"
gh release create "${TAG}" "${FILES[@]}" -R "${PUBLIC_REPO}" --title "${TITLE}" --notes "${NOTES}" 2>/dev/null \
  || gh release upload "${TAG}" "${FILES[@]}" -R "${PUBLIC_REPO}" --clobber
gh release edit "${TAG}" -R "${PUBLIC_REPO}" --title "${TITLE}" --notes "${NOTES}" 2>/dev/null || true
echo "OK → https://github.com/${PUBLIC_REPO}/releases/tag/${TAG}"
