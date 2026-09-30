#!/usr/bin/env bash
# Download helper for tiles/build.sh, tiles/publish.sh and
# web/scripts/fetch-{tiles,fonts}.sh: fetch a file to a `.part` sibling,
# reject it if it looks like an HTML error page, verify its checksum, and
# only then move it into place. On any failure: non-zero exit, a message on
# stderr, and neither the destination nor the `.part` file left behind.
#
# Meant to be sourced, not run: `source ./fetch.sh` from build.sh, or from
# tiles/tests/test_fetch.py via a subprocess.
#
# Public functions:
#   fetch_verified <url> <dest> <algo> <expected-hash>
#     algo is "sha256" or "md5".
#   fetch_geofabrik_verified <url> <dest>
#     Geofabrik-specific: fetches "<url>.md5" (format "<md5>  <filename>")
#     and verifies the download against it.
#   fetch_pinned <url> <dest> <sha256>
#     A download pinned by checksum: does nothing when <dest> exists and
#     matches, else (missing, or a wrong checksum) downloads it again with
#     fetch_verified. Creates <dest>'s directory.
#   geofabrik_path <region>
#     Expands a bare name to europe/germany/<region>; keeps a full Geofabrik
#     path (e.g. europe/denmark) as given. Validates either form and prints
#     the result, or fails on an invalid $REGION.
#   region_stem <region>
#     The file stem (last path component) of geofabrik_path's result.
#   geofabrik_extract_name <region> [snapshot]
#     The Geofabrik file of a region: <stem>-latest.osm.pbf, or with a
#     snapshot (yymmdd, e.g. 260923) <stem>-<yymmdd>.osm.pbf. Fails on a
#     malformed snapshot; an empty one means none.
#   geofabrik_extract_url <region> [snapshot]
#     Its download URL, e.g. https://download.geofabrik.de/europe/denmark-latest.osm.pbf
set -euo pipefail

# 200/302-with-an-HTML-body is how Geofabrik answers a wrong path; `curl
# --fail` alone does not treat that as an error, so the content itself has to
# be sniffed. A real extract or jar never starts with '<' once whitespace is
# skipped, so that is enough to tell an error page from the real file.
_fetch_looks_like_html() {
  # zero bytes dropped too: a PBF starts with one, and bash warns about it
  local first
  first=$(head -c 4096 "$1" | LC_ALL=C tr -d '[:space:]\000' | head -c1)
  [ "$first" = "<" ]
}

_fetch_checksum() {
  local algo=$1 file=$2
  case "$algo" in
    sha256) sha256sum "$file" | cut -d' ' -f1 ;;
    md5) md5sum "$file" | cut -d' ' -f1 ;;
    *) echo "fetch: unsupported checksum algorithm: $algo" >&2; return 1 ;;
  esac
}

fetch_verified() {
  local url=$1 dest=$2 algo=$3 expected=$4
  local part="${dest}.part"
  rm -f "$part"
  if ! curl --fail -sS -L -o "$part" "$url"; then
    rm -f "$part"
    echo "fetch: download failed: $url" >&2
    return 1
  fi
  if _fetch_looks_like_html "$part"; then
    rm -f "$part"
    echo "fetch: $url returned an HTML page, not the expected file" >&2
    return 1
  fi
  local actual
  if ! actual=$(_fetch_checksum "$algo" "$part"); then
    rm -f "$part"
    return 1
  fi
  if [ "$actual" != "$expected" ]; then
    rm -f "$part"
    echo "fetch: checksum mismatch for $url: expected $expected, got $actual" >&2
    return 1
  fi
  mv "$part" "$dest"
}

# Geofabrik publishes an MD5 sidecar at "<url>.md5", one line formatted
# "<md5>  <filename>" (md5sum's own output format).
_fetch_geofabrik_md5() {
  local md5_url=$1
  local part
  part=$(mktemp)
  if ! curl --fail -sS -L -o "$part" "$md5_url"; then
    rm -f "$part"
    echo "fetch: download failed: $md5_url" >&2
    return 1
  fi
  if _fetch_looks_like_html "$part"; then
    rm -f "$part"
    echo "fetch: $md5_url returned an HTML page, not a checksum file" >&2
    return 1
  fi
  local line hash
  line=$(head -n1 "$part")
  rm -f "$part"
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
  expected=$(_fetch_geofabrik_md5 "${url}.md5") || return 1
  fetch_verified "$url" "$dest" md5 "$expected"
}

# REGION as given on the command line may be a bare Geofabrik file stem
# (kept meaning europe/germany/<name>, for backwards compatibility) or a
# full Geofabrik path such as europe/denmark. Either way it ends up in a
# URL and in file paths, so it is validated before use.
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

# A download pinned by checksum: what is already at <dest> and matches is
# kept, whatever is missing or does not match is fetched again.
fetch_pinned() {
  local url=$1 dest=$2 sha256=$3
  if [ -f "$dest" ] && [ "$(_fetch_checksum sha256 "$dest")" = "$sha256" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  fetch_verified "$url" "$dest" sha256 "$sha256"
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
  printf '%s\n' "https://download.geofabrik.de/${path%/*}/${name}"
}
