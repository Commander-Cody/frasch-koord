#!/usr/bin/env bash
# Links a freshly built archive for the web dev server, so a build can be
# tried out right away. The dev server serves only the archive of the name
# web/tiles.lock pins (the last part of its ARCHIVE_URL), so only a build of
# that name is linked. `npm run fetch-assets` (`just setup`) points the link
# back at the published archive.
#
# Meant to be sourced, not run: `source ./devlink.sh` from build.sh, or from
# tiles/tests/test_devlink.py via a subprocess.
#
# Public functions:
#   link_dev_archive <tiles.lock> <link dir> <archive>
#     Links <link dir>/<pinned name> to <archive>, a path relative to <link
#     dir>, when the archive's file name is the pinned one, replacing what
#     was there; otherwise says why it links nothing.
set -euo pipefail

# shellcheck source=tiles/lock.sh
source "$(dirname "${BASH_SOURCE[0]}")/lock.sh"

link_dev_archive() {
  local lock=$1 dir=$2 archive=$3 pinned
  pinned=$(basename "$(lock_get "$lock" ARCHIVE_URL)")
  if [ "$(basename "$archive")" != "$pinned" ]; then
    echo "devlink: $archive not linked for the dev server, which serves only $pinned (pinned in $lock)"
    return 0
  fi
  ln -sfn "$archive" "$dir/$pinned"
  echo "devlink: $dir/$pinned -> $archive for the dev server; \`just setup\` goes back to the published archive"
}
