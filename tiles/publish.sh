#!/usr/bin/env bash
# Publish a built tile archive for the website: upload tiles/data/<stem>.pmtiles
# as the asset of a new GitHub release of this repo, tagged
# tiles-<yyyymmdd>-<first 8 hex digits of its sha256>, and pin web/tiles.lock
# to it: its ARCHIVE_URL and ARCHIVE_SHA256 lines. Commit the lock
# afterwards; `npm run fetch-assets` then fetches that archive and
# `npm run build` ships it, under the asset's name.
#
# Usage: tiles/publish.sh <region>   (as for build.sh, e.g. schleswig-holstein)
#        `just publish-tiles` runs `just check-tiles` on the archive first.
# Needs: gh, logged in with the right to create releases.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=tiles/geofabrik.sh
source ./geofabrik.sh
# shellcheck source=tiles/lock.sh
source ./lock.sh

STEM=$(region_stem "${1:?region name, e.g. schleswig-holstein}")
ARCHIVE="data/${STEM}.pmtiles"
LOCK="../web/tiles.lock"
[ -f "$ARCHIVE" ] || { echo "publish.sh: no $ARCHIVE -- build it first (just tiles)" >&2; exit 1; }

SHA256=$(checksum_of sha256 "$ARCHIVE")
TAG="tiles-$(date -u +%Y%m%d)-${SHA256:0:8}"
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
URL="https://github.com/${REPO}/releases/download/${TAG}/${STEM}.pmtiles"

gh release create "$TAG" --repo "$REPO" --latest=false --title "Tiles ${TAG#tiles-}" --notes "\
The tile archive the website is built with, pinned in web/tiles.lock.
Built by tiles/build.sh and published from commit $(git rev-parse --short HEAD). What it was built from is stamped into the archive's metadata: the name files' git blob hashes (\`built_from\`, see web/README.md) and the extract's replication time.

sha256 ${SHA256}

Map data © OpenStreetMap contributors, available under the Open Database License (ODbL), https://www.openstreetmap.org/copyright." \
  "$ARCHIVE"

lock_set "$LOCK" ARCHIVE_URL "$URL"
lock_set "$LOCK" ARCHIVE_SHA256 "$SHA256"
echo "published ${URL}; pinned in web/tiles.lock -- commit it"
