#!/usr/bin/env bash
# The lock files that pin what the tiles and the site are built from
# (tiles/sources.lock, web/tiles.lock, web/fonts.lock): `KEY=value` lines,
# and `#` comment lines that explain them. web/vite-plugins/build/pins.ts
# reads the same format for the site.
#
# Meant to be sourced, not run: `source ./lock.sh` from build.sh and
# publish.sh, or from tiles/tests/test_lock.py via a subprocess.
#
# Public functions:
#   lock_get <file> <key>
#     Prints the key's value; fails when the file has no line for it.
#   lock_set <file> <key> <value>
#     Rewrites the key's line to the value, and nothing else of the file;
#     fails, leaving the file as it was, when it has no line for the key.
set -euo pipefail

lock_get() {
  local file=$1 key=$2 line
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ $line == "$key="* ]]; then
      printf '%s\n' "${line#*=}"
      return 0
    fi
  done < "$file"
  echo "lock: $file has no $key= line -- restore it from git" >&2
  return 1
}

lock_set() {
  local file=$1 key=$2 value=$3 line found=""
  local part="${file}.part"
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ $line == "$key="* ]]; then
      printf '%s=%s\n' "$key" "$value"
      found=1
    else
      printf '%s\n' "$line"
    fi
  done < "$file" > "$part"
  if [ -z "$found" ]; then
    rm -f "$part"
    echo "lock: $file has no $key= line -- restore it from git" >&2
    return 1
  fi
  mv "$part" "$file"
}
