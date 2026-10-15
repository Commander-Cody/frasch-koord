#!/usr/bin/env bash
# Download helper for tiles/build.sh and tiles/geofabrik.sh: fetch a file to
# a `.part` sibling, reject it if it looks like an HTML error page, verify its
# checksum, and only then move it into place. On any failure: non-zero exit,
# a message on stderr, and neither the destination nor the `.part` file left
# behind.
#
# Meant to be sourced, not run: `source ./fetch.sh` from build.sh, or from
# tiles/tests/test_fetch.py via a subprocess.
#
# Public functions:
#   fetch_verified <url> <dest> <algo> <expected-hash>
#     algo is "sha256" or "md5".
#   fetch_pinned <url> <dest> <sha256>
#     A download pinned by checksum: does nothing when <dest> exists and
#     matches, else (missing, or a wrong checksum) downloads it again with
#     fetch_verified. Creates <dest>'s directory.
#   fetch_text <url>
#     Prints a small text file (a checksum sidecar), or fails on an HTML page.
#   checksum_of <algo> <file>
#     The file's checksum in hex; algo as for fetch_verified.
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

checksum_of() {
  local algo=$1 file=$2
  case "$algo" in
    sha256) sha256sum "$file" | cut -d' ' -f1 ;;
    md5) md5sum "$file" | cut -d' ' -f1 ;;
    *) echo "fetch: unsupported checksum algorithm: $algo" >&2; return 1 ;;
  esac
}

# Downloads <url> to <file>; removes it again when the download fails or is
# an HTML page.
_fetch_to() {
  local url=$1 file=$2
  if ! curl --fail -sS -L -o "$file" "$url"; then
    rm -f "$file"
    echo "fetch: download failed: $url" >&2
    return 1
  fi
  if _fetch_looks_like_html "$file"; then
    rm -f "$file"
    echo "fetch: $url returned an HTML page, not the expected file" >&2
    return 1
  fi
}

fetch_verified() {
  local url=$1 dest=$2 algo=$3 expected=$4
  local part="${dest}.part"
  rm -f "$part"
  _fetch_to "$url" "$part" || return 1
  local actual
  if ! actual=$(checksum_of "$algo" "$part"); then
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

fetch_text() {
  local url=$1
  local part
  part=$(mktemp)
  _fetch_to "$url" "$part" || return 1
  cat "$part"
  rm -f "$part"
}

# A download pinned by checksum: what is already at <dest> and matches is
# kept, whatever is missing or does not match is fetched again.
fetch_pinned() {
  local url=$1 dest=$2 sha256=$3
  if [ -f "$dest" ] && [ "$(checksum_of sha256 "$dest")" = "$sha256" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  fetch_verified "$url" "$dest" sha256 "$sha256"
}
