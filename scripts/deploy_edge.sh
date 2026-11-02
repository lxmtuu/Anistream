#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_edge.sh — deploy Edge Functions kể cả khi MÁY CHƯA CÀI `supabase`.
#
# Vì sao cần: lần deploy 02/11/2026 chết ở `bash: supabase: command not found`
# ⇒ bản vá `home` (shelf "Tập mới hôm nay" đang toàn tập CHƯA CHIẾU) nằm trong
# git mà KHÔNG chạy trên production. "CI xanh nhưng việc thật không xảy ra" là
# đúng kiểu hỏng dự án này phải tránh, nên script tự tìm CLI và tự dùng `npx`.
#
# Dùng:  bash scripts/deploy_edge.sh                 # deploy tất cả
#        bash scripts/deploy_edge.sh home            # chỉ 1 function
#        bash scripts/deploy_edge.sh --check         # chỉ xem CLI/token, không deploy
#
# Cần: node >= 18 (để `npx supabase`), và đăng nhập 1 lần:
#        npx --yes supabase@latest login
#      hoặc đặt biến môi trường SUPABASE_ACCESS_TOKEN (sbp_…).
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
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "❌ tham số lạ: $a"; exit 2 ;;
    *) TARGET+=("$a") ;;
  esac
done
[ ${#TARGET[@]} -eq 0 ] && TARGET=("${FUNCS_ALL[@]}")

# ── 1. Tìm CLI: ưu tiên bản cài sẵn, không có thì dùng npx ──────────────────
if command -v supabase >/dev/null 2>&1; then
  SUPABASE=(supabase)
  echo "✅ dùng supabase CLI trên PATH ($(supabase --version 2>/dev/null | head -1))"
elif command -v npx >/dev/null 2>&1; then
  SUPABASE=(npx --yes supabase@latest)
  echo "ℹ️  không có 'supabase' trên PATH → dùng: npx --yes supabase@latest"
  echo "   (lần đầu sẽ tải CLI ~20–60s)"
else
  echo "❌ Không có 'supabase' và cũng không có 'npx'."
  echo "   Cài Node.js ≥ 18: https://nodejs.org  rồi chạy lại script này."
  exit 2
fi

# ── 2. Kiểm đăng nhập: thiếu là DỪNG, không deploy nửa vời ──────────────────
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

# ── 3. Deploy ───────────────────────────────────────────────────────────────
FAIL=0
for f in "${TARGET[@]}"; do
  [ -d "supabase/functions/$f" ] || { echo "❌ không có supabase/functions/$f"; FAIL=1; continue; }
  echo
  echo "▶ deploy $f"
  # `push` cần verify_jwt=false (cron/FCM gọi thẳng); các function còn lại cũng
  # đang để false vì app gọi bằng anon key qua gateway.
  if "${SUPABASE[@]}" functions deploy "$f" --project-ref "$PROJECT_REF" --no-verify-jwt; then
    echo "  ✅ $f xong"
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

# ── 4. Liệt kê phiên bản đang ACTIVE để đối chiếu ───────────────────────────
echo
echo "▶ Phiên bản đang chạy trên project:"
"${SUPABASE[@]}" functions list --project-ref "$PROJECT_REF" || true
echo
echo "✅ deploy xong. Kiểm bằng mắt: các function vừa deploy phải có VERSION mới."
