#!/usr/bin/env bash
# RTK Kiro CLI hook — block-and-redirect to RTK equivalents for token savings.
# Requires: rtk in PATH, jq
#
# Kiro exit-code protocol (preToolUse):
#   0 = allow execution unchanged
#   2 = block; stderr is forwarded to the LLM so it retries with the suggestion
#
# This is a thin delegating hook: all rewrite logic lives in `rtk rewrite`
# (src/discover/registry.rs). To add or change rewrite rules, edit the Rust
# registry — not this file.
#
# Prefer `rtk hook kiro` (native binary) over this script when possible.

if ! command -v jq &>/dev/null; then
  exit 0
fi

if ! command -v rtk &>/dev/null; then
  exit 0
fi

INPUT=$(cat)
CMD=$(jq -r '.tool_input.command // empty' <<<"$INPUT")

[ -z "$CMD" ] && exit 0

REWRITTEN=$(rtk rewrite "$CMD" 2>/dev/null)
EXIT_CODE=$?

# Exit 0 = rewrite + allow, Exit 3 = rewrite + ask — both mean RTK has a better command.
# Exit 1 = no rewrite (pass through), Exit 2 = deny rule (pass through).
if { [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 3 ]; } && [ "$CMD" != "$REWRITTEN" ]; then
  echo "[RTK] Token savings available. Use: $REWRITTEN" >&2
  exit 2
fi

exit 0
