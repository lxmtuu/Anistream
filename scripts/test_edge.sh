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
npx --yes esbuild@0.23.1 \
  supabase/functions/_shared/push_plan.ts \
  --bundle --format=esm --platform=neutral \
  --outfile="$OUT/push_plan.mjs" >/dev/null
echo "  ✓ $OUT/push_plan.mjs"

echo "▶ node --test"
node --test tests/edge/*.test.mjs
