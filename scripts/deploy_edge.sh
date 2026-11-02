#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_edge.sh — deploy Edge Functions kể cả khi MÁY CHƯA CÀI `supabase`,
# và CHỨNG MINH là version đã đổi (không tin mỗi exit code).
#
# Vì sao cần: 02/11/2026 hai lần deploy liên tiếp không xảy ra:
#   1. `bash: supabase: command not found` — bản vá `home` (shelf "Tập mới hôm
#      nay" đang toàn tập CHƯA CHIẾU) nằm trong git mà không chạy production;
#   2. lần sau CLI có chạy nhưng DỪNG ở câu hỏi "Deploy 1 Function … ?" và chờ
#      người bấm Y.
# Nên script: tự tìm CLI (kể cả qua `npx`), luôn `--yes`, và so VERSION trước/sau.
#
# Dùng:  bash scripts/deploy_edge.sh                 # deploy home search schedule anime
#        bash scripts/deploy_edge.sh home            # chỉ 1 function
#        bash scripts/deploy_edge.sh --check         # chỉ xem CLI/token, không deploy
#
# Cờ CLI v3 (2 biến thể được tự thử): `--remote=<ref>` (mới) / `--project-ref`
# (cũ), `--use-api` (bundle phía Supabase ⇒ KHÔNG cần Docker), `--yes`.
#
# Cần: node >= 18 (để `npx supabase`) + đăng nhập 1 lần:
#        npx --yes supabase@latest login
#      hoặc biến môi trường SUPABASE_ACCESS_TOKEN (sbp_…).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PROJECT_REF="${SUPABASE_PROJECT_REF:-snpzrblwiamqtrnifdis}"
FUNCS_ALL=(home search schedule anime)
CHECK_ONLY=0
TARGET=()

for a in "$@"; do
  case "$a" in
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    -*) echo "❌ tham số lạ: $a"; exit 2 ;;
    *) TARGET+=("$a") ;;
  esac
done
[ ${#TARGET[@]} -eq 0 ] && TARGET=("${FUNCS_ALL[@]}")

# ── 1. Tìm CLI ──────────────────────────────────────────────────────────────
if command -v supabase >/dev/null 2>&1; then
  SUPABASE=(supabase)
  echo "✅ dùng supabase CLI trên PATH"
elif command -v npx >/dev/null 2>&1; then
  SUPABASE=(npx --yes supabase@latest)
  echo "ℹ️  không có 'supabase' trên PATH → dùng: npx --yes supabase@latest"
  echo "   (lần đầu sẽ tải CLI ~20–60s)"
else
  echo "❌ Không có 'supabase' và cũng không có 'npx'."
  echo "   Cài Node.js ≥ 18: https://nodejs.org  rồi chạy lại script này."
  exit 2
fi

# ── 2. Kiểm đăng nhập: thiếu là DỪNG ───────────────────────────────────────
if [ -z "${SUPABASE_ACCESS_TOKEN:-}" ]; then
  if ! "${SUPABASE[@]}" projects list >/dev/null 2>&1; then
    echo "❌ Chưa đăng nhập Supabase CLI (và không có SUPABASE_ACCESS_TOKEN)."
    echo "   Chạy 1 lần:   npx --yes supabase@latest login"
    echo "   hoặc:         export SUPABASE_ACCESS_TOKEN=sbp_…"
    echo "   → Không deploy gì cả để tránh tưởng là đã cập nhật."
    exit 2
  fi
fi
echo "✅ đã xác thực (project $PROJECT_REF)"

if [ "$CHECK_ONLY" = "1" ]; then
  echo "✅ --check xong, không deploy."
  exit 0
fi

# ── 3. Đọc VERSION trước khi deploy (để chứng minh sau đó) ────────────────
list_json() {
  "${SUPABASE[@]}" functions list --remote="$PROJECT_REF" --output json 2>/dev/null \
    || "${SUPABASE[@]}" functions list --project-ref "$PROJECT_REF" --output json 2>/dev/null
}

# stdin: JSON của `functions list`  →  mỗi dòng "slug<TAB>version"
versions() {
  python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    sys.exit(1)
rows = d if isinstance(d, list) else (d.get("functions") or d.get("data") or [])
for f in rows:
    if isinstance(f, dict) and f.get("slug"):
        print("%s\t%s" % (f["slug"], f.get("version")))
' 2>/dev/null
}

BEFORE="$(list_json | versions || true)"
if [ -z "$BEFORE" ]; then
  echo "⚠ KHÔNG đọc được danh sách function TRƯỚC khi deploy → sẽ không chứng"
  echo "  minh được VERSION đã đổi; cuối script bạn phải tự đối chiếu."
fi

# ── 4. Deploy ───────────────────────────────────────────────────────────────
FAIL=0
for f in "${TARGET[@]}"; do
  [ -d "supabase/functions/$f" ] || { echo "❌ không có supabase/functions/$f"; FAIL=1; continue; }
  echo
  echo "▶ deploy $f"
  # `--yes`      : không hỏi "Deploy N Function … ?" (đã từng đứng chờ ở đây)
  # `--use-api`  : bundle phía Supabase, không cần Docker Desktop
  # `--remote`   : cờ CLI v3; CLI v2 dùng `--project-ref` → tự lùi
  if "${SUPABASE[@]}" functions deploy "$f" --remote="$PROJECT_REF" \
       --no-verify-jwt --use-api --yes; then
    echo "  ✅ $f xong"
  elif "${SUPABASE[@]}" functions deploy "$f" --project-ref "$PROJECT_REF" \
       --no-verify-jwt --yes; then
    echo "  ✅ $f xong (CLI cũ)"
  else
    echo "  ❌ $f THẤT BẠI (đừng coi là đã cập nhật)"
    FAIL=1
  fi
done

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "❌ Có function deploy hỏng — production vẫn chạy bản CŨ."
  exit 1
fi

# ── 5. CHỨNG MINH: version phải đổi ────────────────────────────────────────
echo
echo "▶ Phiên bản đang chạy trên project:"
AFTER="$(list_json | versions || true)"
printf '%s\n' "$AFTER" | sed 's/^/  /'

if [ -z "$BEFORE" ] || [ -z "$AFTER" ]; then
  echo
  echo "✅ deploy xong (exit code OK) nhưng CHƯA xác minh được version."
  echo "   Đối chiếu tay: hàm vừa deploy phải có version mới trong danh sách trên."
  exit 0
fi

BAD=0
echo
for f in "${TARGET[@]}"; do
  b=$(printf '%s\n' "$BEFORE" | awk -F'\t' -v s="$f" '$1==s{print $2}')
  a=$(printf '%s\n' "$AFTER"  | awk -F'\t' -v s="$f" '$1==s{print $2}')
  if [ -n "$a" ] && [ "$a" != "$b" ]; then
    echo "  ✅ $f: version $b → $a"
  else
    echo "  ❌ $f: version KHÔNG đổi (vẫn $b) — deploy không ăn"
    BAD=1
  fi
done

if [ "$BAD" -ne 0 ]; then
  echo
  echo "❌ Deploy báo xong nhưng version không đổi — production vẫn là bản CŨ."
  exit 1
fi
echo
echo "✅ deploy xong VÀ đã xác minh version đổi."
