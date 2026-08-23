#!/usr/bin/env bash
# Met à jour LEGAL-Crypto-Tracker.md sur les hubs (README CT-only = crypto-tracker/packaging/sync-public-readmes.sh).
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GEST_VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
need() { command -v "$1" >/dev/null 2>&1 || { echo "manque: $1" >&2; exit 1; }; }
need gh
need base64

put_legal_file() {
  local repo="$1"
  local dest="LEGAL-Hub-Systeme.md"
  local b64 sha
  b64="$(base64 -w0 < "${ROOT}/LEGAL.md")"
  sha="$(gh api "repos/${repo}/contents/${dest}" --jq .sha 2>/dev/null || true)"
  local args=(-f message="docs: Hub Système LEGAL.md (copyright / CGU / RGPD)" -f content="${b64}")
  if [[ -n "${sha}" && "${sha}" != "null" ]]; then
    args+=(-f sha="${sha}")
  fi
  gh api -X PUT "repos/${repo}/contents/${dest}" "${args[@]}" --jq .content.path >/dev/null
  echo "OK ${dest} → ${repo}"
}

echo "Gest ${GEST_VERSION} : hubs CT-only — pas de README hub depuis Gest."
echo "Flatpak : https://github.com/Mr-Aurevo-X/Hub-Systeme/releases"
put_legal_file "Mr-Aurevo-X/linux-releases"
put_legal_file "Mr-Aurevo-X/linux-flatpak-releases"
