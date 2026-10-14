#!/bin/bash
# Blockscout Merits daily check-in — cron wrapper (script-only, no LLM).
# Pakai token tersimpan (tokens.json). Silent kalau tidak ada yang perlu dilaporkan.
set -uo pipefail

DIR="/root/bots/blockscout-claim"

# Belum login / token belum ada -> jangan berisik tiap hari.
if [ ! -s "$DIR/tokens.json" ]; then
    exit 0
fi

OUT="$(cd "$DIR" && timeout 900 python3 claim.py --quiet 2>&1)"

# Laporkan hanya kalau ada claim BARU (SUCCESS / +N dengan N>0) atau ADA kegagalan.
# Catatan: ringkasan selalu memuat ", 0 gagal" -> jangan match kata 'gagal' polos.
if echo "$OUT" | grep -qE 'SUCCESS|FAIL |claimed \(\+[1-9]|, [1-9][0-9]* gagal'; then
    echo "$OUT"
fi
exit 0
