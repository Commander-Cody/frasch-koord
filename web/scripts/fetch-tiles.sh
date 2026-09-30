#!/usr/bin/env bash
# Downloads the published tile archive web/tiles.lock pins (~125 MB, not in
# git) into .cache/tiles/<sha256>.pmtiles and links
# public/tiles/schleswig-holstein.pmtiles to it, for the dev server.
# `npm run build` takes the archive from the cache (vite-plugins/tiles.ts).
#
# Usage: scripts/fetch-tiles.sh [web-dir]   (default: the web/ it lives in)
set -euo pipefail
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=tiles/fetch.sh
source "$SCRIPTS/../../tiles/fetch.sh"
cd "${1:-$SCRIPTS/..}"

lock_value() {
  sed -n "s/^$1=//p" tiles.lock
}

ARCHIVE_URL=$(lock_value ARCHIVE_URL)
ARCHIVE_SHA256=$(lock_value ARCHIVE_SHA256)
# It names a file in .cache/tiles/, so it has to be a hash and nothing else.
if [[ ! $ARCHIVE_SHA256 =~ ^[0-9a-f]{64}$ ]]; then
  echo "fetch-tiles: tiles.lock pins no sha256 (ARCHIVE_SHA256=$ARCHIVE_SHA256)" >&2
  exit 1
fi
CACHED=".cache/tiles/$ARCHIVE_SHA256.pmtiles"
LINK="public/tiles/schleswig-holstein.pmtiles"

# Ours to (re)point: no archive there yet, or a link to an earlier fetch.
# Anything else is someone's own archive, e.g. a link to tiles/data/.
ours_to_link() {
  { [ ! -e "$LINK" ] && [ ! -L "$LINK" ]; } || [[ $(readlink "$LINK") == ../../.cache/tiles/* ]]
}

fetch_pinned "$ARCHIVE_URL" "$CACHED" "$ARCHIVE_SHA256"
if ours_to_link; then
  ln -sfn "../../$CACHED" "$LINK"
else
  echo "kept $LINK (-> $(readlink "$LINK" || echo "a file")): the dev server serves that, a build the fetched archive"
fi
# Earlier pins' archives: ~125 MB each, and nothing uses them any more.
find .cache/tiles -name '*.pmtiles' ! -name "$ARCHIVE_SHA256.pmtiles" -delete
