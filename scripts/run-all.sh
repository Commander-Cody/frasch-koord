#!/usr/bin/env bash
# Runs each argument as one shell command, in order, and keeps going after a
# failure, so a single run reports every problem: `just check` and
# `npm run check` in web/.
#
# Usage: scripts/run-all.sh <command>...
set -uo pipefail

failed=()
for command in "$@"; do
  echo "run-all: $command"
  bash -c "$command" || failed+=("$command")
done

for command in "${failed[@]}"; do
  echo "run-all: failed: $command" >&2
done
[ ${#failed[@]} -eq 0 ]
