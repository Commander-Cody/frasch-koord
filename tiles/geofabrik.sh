#!/usr/bin/env bash
# The OSM extracts of Geofabrik: what a region's file is called, where it is
# downloaded from, and the download itself, verified by Geofabrik's own MD5
# sidecar (with fetch.sh, which this sources).
#
# Meant to be sourced, not run: `source ./geofabrik.sh` from build.sh, the
# justfile's `extracts`, or tiles/tests/test_geofabrik.py via a subprocess.
#
# Public functions:
#   geofabrik_path <region>
#     Expands a bare name to europe/germany/<region>; keeps a full Geofabrik
#     path (e.g. europe/denmark) as given. Validates either form and prints
#     the result, or fails on an invalid region.
#   region_stem <region>
#     The file stem (last path component) of geofabrik_path's result.
#   geofabrik_extract_name <region> [snapshot]
#     The Geofabrik file of a region: <stem>-latest.osm.pbf, or with a
#     snapshot (yymmdd, e.g. 260923) <stem>-<yymmdd>.osm.pbf. Fails on a
#     malformed snapshot; an empty one means none.
#   geofabrik_extract_url <region> [snapshot]
#     Its download URL, e.g. https://download.geofabrik.de/europe/denmark-latest.osm.pbf
#   fetch_geofabrik_verified <url> <dest>
#     Fetches "<url>.md5" (format "<md5>  <filename>") and verifies the
#     download against it.
#   fetch_geofabrik_extract <region> <dir> [snapshot]
#     Puts the region's extract into <dir> under geofabrik_extract_name's
#     name, downloaded and verified -- unless it is there already. Creates
#     <dir>.
#
# Env: GEOFABRIK_URL, the server the extracts are downloaded from (default
#      https://download.geofabrik.de),
#      REFRESH=1 to download an extract that is there already again (e.g.
#      after Geofabrik's next update).
set -euo pipefail
# shellcheck source=tiles/fetch.sh
source "$(dirname "${BASH_SOURCE[0]}")/fetch.sh"

GEOFABRIK_URL=${GEOFABRIK_URL:-https://download.geofabrik.de}

# Geofabrik publishes an MD5 sidecar at "<url>.md5", one line formatted
# "<md5>  <filename>" (md5sum's own output format).
_geofabrik_md5() {
  local md5_url=$1
  local line hash
  line=$(fetch_text "$md5_url" | head -n1) || return 1
  hash=${line%% *}
  if [[ ! $hash =~ ^[0-9a-fA-F]{32}$ ]]; then
    echo "fetch: could not parse a checksum out of $md5_url" >&2
    return 1
  fi
  printf '%s\n' "$hash"
}

fetch_geofabrik_verified() {
  local url=$1 dest=$2
  local expected
  expected=$(_geofabrik_md5 "${url}.md5") || return 1
  fetch_verified "$url" "$dest" md5 "$expected"
}

# A region may be a bare Geofabrik file stem (kept meaning
# europe/germany/<name>, for backwards compatibility) or a full Geofabrik
# path such as europe/denmark. Either way it ends up in a URL and in file
# paths, so it is validated before use.
geofabrik_path() {
  local region=$1
  if [[ ! $region =~ ^[a-z0-9-]+(/[a-z0-9-]+)*$ ]]; then
    echo "fetch: invalid region: $region (expected e.g. schleswig-holstein or europe/denmark)" >&2
    return 1
  fi
  case "$region" in
    */*) printf '%s\n' "$region" ;;
    *) printf '%s\n' "europe/germany/$region" ;;
  esac
}

region_stem() {
  local path
  path=$(geofabrik_path "$1") || return 1
  printf '%s\n' "${path##*/}"
}

# The Geofabrik file of a region: the `-latest` one, or with a snapshot
# (yymmdd, e.g. 260923) the one Geofabrik dated that day. Named by the
# region's stem, so it is also the file's name in tiles/data.
geofabrik_extract_name() {
  local stem snapshot=${2:-}
  stem=$(region_stem "$1") || return 1
  if [ -n "$snapshot" ] && [[ ! $snapshot =~ ^[0-9]{6}$ ]]; then
    echo "fetch: invalid snapshot: $snapshot (expected yymmdd, e.g. 260923)" >&2
    return 1
  fi
  printf '%s\n' "${stem}-${snapshot:-latest}.osm.pbf"
}

geofabrik_extract_url() {
  local path name
  path=$(geofabrik_path "$1") || return 1
  name=$(geofabrik_extract_name "$1" "${2:-}") || return 1
  printf '%s\n' "${GEOFABRIK_URL}/${path%/*}/${name}"
}

fetch_geofabrik_extract() {
  local region=$1 dir=$2 snapshot=${3:-}
  local dest url
  dest="$dir/$(geofabrik_extract_name "$region" "$snapshot")" || return 1
  if [ "${REFRESH:-}" = "1" ] || [ ! -f "$dest" ]; then
    url=$(geofabrik_extract_url "$region" "$snapshot") || return 1
    mkdir -p "$dir"
    fetch_geofabrik_verified "$url" "$dest"
  fi
}
