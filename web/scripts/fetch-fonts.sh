#!/usr/bin/env bash
# Puts the glyph ranges web/fonts.lock lists into public/fonts/ (~2.6 MB,
# not in git), and nothing else: Vite ships public/fonts/ as it is, and
# vite-plugins/glyphs.ts stops a build where it holds anything else.
#
#  - every listed range there: whatever else is there (an earlier, fuller
#    fetch) is deleted, nothing is downloaded
#  - a listed range missing: the zip fonts.lock pins is downloaded, checked
#    against its sha256, and public/fonts/ rebuilt from it
#
# Usage: scripts/fetch-fonts.sh [web-dir]   (default: the web/ it lives in)
set -euo pipefail
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tiles/fetch.sh
source "$SCRIPTS/../../tiles/fetch.sh"
cd "${1:-$SCRIPTS/..}"

lock_value() {
  sed -n "s/^$1=//p" fonts.lock
}

FONTS_URL=$(lock_value FONTS_URL)
FONTS_SHA256=$(lock_value FONTS_SHA256)
IFS=, read -ra STACKS <<< "$(lock_value STACKS)"
read -ra RANGES <<< "$(lock_value RANGES)"

# every file public/fonts/ is to hold, as <stack>/<range>.pbf
LISTED=()
for s in "${STACKS[@]}"; do
  for r in "${RANGES[@]}"; do LISTED+=("$s/$r.pbf"); done
done

all_listed_present() {
  local f
  for f in "${LISTED[@]}"; do [ -f "public/fonts/$f" ] || return 1; done
}

# Deletes every file and directory under public/fonts/ that fonts.lock does not list.
prune_unlisted() {
  local -A keep=()
  local f removed=0
  for f in "${LISTED[@]}"; do keep[$f]=1; done
  while IFS= read -r -d '' f; do
    if [ -z "${keep[${f#public/fonts/}]:-}" ]; then rm -f "$f"; removed=$((removed + 1)); fi
  done < <(find public/fonts -type f -print0)
  find public/fonts -mindepth 1 -type d -empty -delete
  if [ "$removed" -gt 0 ]; then
    echo "removed $removed glyph files fonts.lock does not list"
  else
    echo "fonts already present"
  fi
}

# Copies the listed ranges out of the unpacked zip at $1 into the directory $2.
copy_listed() {
  local unpacked=$1 dest=$2 s r src
  for s in "${STACKS[@]}"; do
    src=$(find "$unpacked" -type d -name "$s" | head -1)
    mkdir -p "$dest/$s"
    for r in "${RANGES[@]}"; do
      if [ -z "$src" ] || [ ! -f "$src/$r.pbf" ]; then
        echo "fetch-fonts: $FONTS_URL has no range $r of $s" >&2
        return 1
      fi
      cp "$src/$r.pbf" "$dest/$s/"
    done
  done
}

if all_listed_present; then
  prune_unlisted
  exit 0
fi
command -v unzip >/dev/null || { echo "fetch-fonts: unzip is not installed" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fetch_verified "$FONTS_URL" "$tmp/noto-sans.zip" sha256 "$FONTS_SHA256"
unzip -q "$tmp/noto-sans.zip" -d "$tmp/x"
copy_listed "$tmp/x" "$tmp/fonts"
mkdir -p public
rm -rf public/fonts
mv "$tmp/fonts" public/fonts
du -sh public/fonts
