#!/usr/bin/env bash
# Which files of the name pipeline build.sh names to the frasch commands.
# Meant to be sourced, not run: `source ./workspace.sh` from build.sh, or from
# tiles/tests/test_workspace.py.
#
# Public functions:
#   workspace_options <file>...
#     Sets the array WORKSPACE_OPTIONS to the path options of the <file>s
#     (names, dialects, areas, objects, curation) whose environment variable
#     (NAMES, DIALECTS, ...) is set and not empty: `--names "$NAMES"` and so
#     on. A file without one is left out, so that the command works on its
#     own default (frasch/paths.py) and build.sh declares none of its own.
set -euo pipefail

workspace_options() {
  local file variable
  WORKSPACE_OPTIONS=()
  for file in "$@"; do
    variable=${file^^}
    if [ -n "${!variable:-}" ]; then
      WORKSPACE_OPTIONS+=("--$file" "${!variable}")
    fi
  done
}
