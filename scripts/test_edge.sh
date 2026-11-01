#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_edge.sh — test logic thuần của Edge Functions bằng Node (không cần Deno).
#
# Cách làm: esbuild transpile TS → JS, rồi `node --test`. Nhờ vậy CI kiểm tra được
# logic push (chống spam, chống gửi trùng) mà không cần Supabase/FCM.
#
# Dùng:  bash scripts/test_edge.sh
# Cần:   node >= 20 (có sẵn `node --test`)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="tests/edge/.build"
mkdir -p "$OUT"

echo "▶ Transpile TS → JS (esbuild)"
for f in push_plan query; do
  npx --yes esbuild@0.23.1 \
    "supabase/functions/_shared/$f.ts" \
    --bundle --format=esm --platform=neutral \
    --outfile="$OUT/$f.mjs" >/dev/null
  echo "  ✓ $OUT/$f.mjs"
done

echo "▶ node --test"
node --test tests/edge/*.test.mjs
