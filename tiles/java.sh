#!/usr/bin/env bash
# Which Java build.sh runs Planetiler with. Meant to be sourced, not run:
# `source ./java.sh` from build.sh, or from tiles/tests/test_java.py.
#
# Public functions:
#   find_java_home
#     JAVA_HOME if set, else a JDK under ~/.local/opt/jdk-21*, else the one
#     `java` on PATH belongs to; fails with a message when there is none.
#   java_major <version line>
#     The major version in the first line of `java -version`: 17 for
#     `openjdk version "17" 2021-09-14` (a GA release has no dot), 21 for
#     `"21.0.2"`, 1 for a pre-9 `"1.8.0_392"`. Fails, printing nothing, on a
#     line without a version.
set -euo pipefail

find_java_home() {
  if [ -n "${JAVA_HOME:-}" ]; then
    printf '%s\n' "$JAVA_HOME"
    return 0
  fi
  # An unmatched glob is left as the literal pattern (nullglob is off), which
  # simply fails the -d test below -- unlike `ls ... | head`, it cannot trip
  # `set -e -o pipefail` on a missing directory.
  local candidates=(~/.local/opt/jdk-21*)
  if [ -d "${candidates[0]}" ]; then
    printf '%s\n' "${candidates[0]}"
    return 0
  fi
  if command -v java >/dev/null 2>&1; then
    dirname "$(dirname "$(command -v java)")"
    return 0
  fi
  echo "build.sh: no Java found (set JAVA_HOME, install a JDK under ~/.local/opt/jdk-21*, or put java on PATH)" >&2
  return 1
}

java_major() {
  local major
  major=$(printf '%s' "$1" | sed -nE 's/.*"([0-9]+)[".].*/\1/p')
  [[ $major =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$major"
}
