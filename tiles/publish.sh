#!/usr/bin/env bash
# Publish a built tile archive for the website: upload tiles/data/<stem>.pmtiles
# as the asset of a new GitHub release of this repo, tagged
# tiles-<yyyymmdd>-<first 8 hex digits of its sha256>, and pin web/tiles.lock
# to it. Commit the lock afterwards; `npm run fetch-assets` then fetches that
# archive and `npm run build` ships it.
#
# Usage: tiles/publish.sh <region>   (as for build.sh, e.g. schleswig-holstein)
# Needs: gh, logged in with the right to create releases.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=tiles/fetch.sh
source ./fetch.sh

STEM=$(region_stem "${1:?region name, e.g. schleswig-holstein}")
ARCHIVE="data/${STEM}.pmtiles"
LOCK="../web/tiles.lock"
[ -f "$ARCHIVE" ] || { echo "publish.sh: no $ARCHIVE -- build it first (just tiles)" >&2; exit 1; }

SHA256=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
TAG="tiles-$(date -u +%Y%m%d)-${SHA256:0:8}"
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
URL="https://github.com/${REPO}/releases/download/${TAG}/${STEM}.pmtiles"

gh release create "$TAG" --repo "$REPO" --latest=false --title "Tiles ${TAG#tiles-}" --notes "\
The tile archive the website is built with, pinned in web/tiles.lock.
Built by tiles/build.sh from commit $(git rev-parse --short HEAD); the inputs it was built from are stamped into the archive's metadata (\`built_from\`, see web/README.md).

sha256 ${SHA256}

Map data © OpenStreetMap contributors, available under the Open Database License (ODbL), https://www.openstreetmap.org/copyright." \
  "$ARCHIVE"

cat > "$LOCK" <<EOF
# The tile archive the website ships, published by \`just publish-tiles\`
# (tiles/publish.sh). scripts/fetch-tiles.sh fetches it and
# vite-plugins/tiles.ts puts it into the build; both check its sha256.
ARCHIVE_URL=${URL}
ARCHIVE_SHA256=${SHA256}
EOF
echo "published ${URL}; pinned in web/tiles.lock -- commit it"
