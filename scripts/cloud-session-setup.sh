#!/usr/bin/env bash
# SessionStart hook (.claude/settings.json): sets a Claude cloud session up
# like `just setup`, with the Node of web/.nvmrc, and puts that Node on the
# PATH of the session's later commands. Does nothing outside cloud sessions.
#
# Expects nvm with that Node installed, which the cloud environment's setup
# script provides.
set -euo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

# A SessionStart hook's stdout goes into Claude's context; keep setup logs out.
exec >&2
cd "$(dirname "$0")/.."

if [ ! -s "$HOME/.nvm/nvm.sh" ]; then
  echo "cloud-session-setup: nvm not found at ~/.nvm; install it and the Node of web/.nvmrc in the cloud environment's setup script" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$HOME/.nvm/nvm.sh"
nvm use "$(cat web/.nvmrc)"
echo "export PATH=\"$(dirname "$(command -v node)"):\$PATH\"" >> "$CLAUDE_ENV_FILE"

uv run just setup
