#!/usr/bin/env bash
# Downloads the Noto Sans glyph ranges OSM Bright needs into public/fonts (~100 MB, not in git).
set -euo pipefail
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tiles/fetch.sh
source "$SCRIPTS/../../tiles/fetch.sh"
cd "$SCRIPTS/.."

FONTS_URL="https://github.com/openmaptiles/fonts/releases/download/v2.0/noto-sans.zip"
FONTS_SHA256="d117316544b43a5dde7ee761b36e17701e9f85574e181d76a74814240fdbaf34"
# the font stacks the style names (src/style/frasch-bright.json)
STACKS=("Noto Sans Regular" "Noto Sans Italic" "Noto Sans Bold")

present=true
for s in "${STACKS[@]}"; do [ -d "public/fonts/$s" ] || present=false; done
$present && { echo "fonts already present"; exit 0; }
command -v unzip >/dev/null || { echo "fetch-fonts: unzip is not installed" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fetch_verified "$FONTS_URL" "$tmp/noto-sans.zip" sha256 "$FONTS_SHA256"
unzip -q "$tmp/noto-sans.zip" -d "$tmp/x"
mkdir -p public/fonts
for s in "${STACKS[@]}"; do
  src=$(find "$tmp/x" -type d -name "$s" | head -1); rm -rf "public/fonts/$s"; cp -r "$src" public/fonts/
done
du -sh public/fonts
