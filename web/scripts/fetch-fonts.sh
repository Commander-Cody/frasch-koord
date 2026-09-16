#!/usr/bin/env bash
# Downloads the Noto Sans glyph ranges OSM Bright needs into public/fonts (~100 MB, not in git).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d "public/fonts/Noto Sans Regular" ] && { echo "fonts already present"; exit 0; }
mkdir -p public/fonts && tmp=$(mktemp -d)
curl -L https://github.com/openmaptiles/fonts/releases/download/v2.0/noto-sans.zip -o "$tmp/noto-sans.zip"
unzip -q "$tmp/noto-sans.zip" -d "$tmp/x"
for s in "Noto Sans Regular" "Noto Sans Italic" "Noto Sans Bold"; do
  src=$(find "$tmp/x" -type d -name "$s" | head -1); cp -r "$src" public/fonts/
done
rm -rf "$tmp"; du -sh public/fonts
