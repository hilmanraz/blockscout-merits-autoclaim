#!/bin/bash
# Blockscout Merits daily check-in — cron wrapper (script-only, no LLM).
# Uses the stored token in tokens.json. Silent unless something actually happened.
#
# Works from any install location — resolves its own directory.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Not logged in yet -> stay quiet.
if [ ! -s "$DIR/tokens.json" ]; then
    exit 0
fi

OUT="$(cd "$DIR" && timeout 900 python3 claim.py --quiet 2>&1)"

# Report only on a real claim or a real failure.
# NOTE: the summary always contains ", 0 gagal" -> don't match the bare word.
if echo "$OUT" | grep -qE 'SUCCESS|FAIL |claimed \(\+[1-9]|, [1-9][0-9]* gagal'; then
    echo "$OUT"
fi
exit 0
