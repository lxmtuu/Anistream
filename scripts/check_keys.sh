#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# check_keys.sh — kiểm tra 2 API key (TMDB + YouTube) có DÙNG ĐƯỢC không.
#
# Vì sao cần: key sai / chưa bật API / hết quota đều ra lỗi khó hiểu ("Request had
# insufficient authentication scopes", "accessNotConfigured"…). Script này gọi thử
# 1 request cho mỗi dịch vụ và nói thẳng: key ổn, hay sai ở đâu, sửa ở đâu.
#
# Dùng:  bash scripts/check_keys.sh
# Exit: 0 = cả 2 key ổn (hoặc không cấu hình → bỏ qua) · 1 = có key HỎNG
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

FAIL=0
have() { command -v curl >/dev/null 2>&1; }
have || { echo "❌ cần curl" >&2; exit 2; }

# Đọc .env (không ghi đè biến đã có)
if [ -f .env ]; then
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac
    k="$(echo "$k" | tr -d ' ')"
    v="$(echo "$v" | sed -e 's/^["'\'']//' -e 's/["'\'']$//' -e 's/\r$//')"
    [ -z "${!k:-}" ] && export "$k=$v"
  done < .env
fi

echo "▶ Kiểm API key"
echo

# ── TMDB ────────────────────────────────────────────────────────────────────
if [ -z "${TMDB_API_KEY:-}" ]; then
  echo "  ⚠ TMDB_API_KEY trống → bỏ qua (app vẫn chạy, nhưng tên là romaji"
  echo "    và phần lớn bộ không có danh sách tập)"
else
  body=$(curl -sS -m 15 -w '\n%{http_code}' \
    "https://api.themoviedb.org/3/configuration?api_key=${TMDB_API_KEY}" 2>&1)
  code=$(printf '%s' "$body" | tail -1)
  case "$code" in
    200) echo "  ✅ TMDB key dùng được" ;;
    401) echo "  ❌ TMDB 401 → key sai. Lấy lại: themoviedb.org → Settings → API"
         echo "     ⚠ phải là \"API Key (v3)\", KHÔNG phải Read Access Token (v4)"
         FAIL=$((FAIL+1)) ;;
    000) echo "  ⚠ TMDB: không kết nối được (mất mạng / bị chặn) — không kết luận được" ;;
    *)   echo "  ❌ TMDB HTTP $code: $(printf '%s' "$body" | head -c 200)"
         FAIL=$((FAIL+1)) ;;
  esac
fi

# ── YouTube ─────────────────────────────────────────────────────────────────
if [ -z "${YOUTUBE_API_KEY:-}" ]; then
  echo "  ⚠ YOUTUBE_API_KEY trống → bỏ qua (job youtube chỉ dùng RSS: 15 video/kênh)"
else
  curl -sS -m 15 \
    "https://www.googleapis.com/youtube/v3/videos?part=id&id=dQw4w9WgXcQ&key=${YOUTUBE_API_KEY}" \
    > /tmp/ytkey.json 2>/dev/null
  if python3 - "$?" <<'PY' >/tmp/ytkey.txt 2>&1
import json, sys
try:
    d = json.load(open("/tmp/ytkey.json"))
except Exception:
    print("NETWORK"); raise SystemExit

if "error" not in d:
    print("OK"); raise SystemExit

e = d["error"]
reason = ((e.get("errors") or [{}])[0].get("reason")) or e.get("status") or "?"
print("ERR", reason)
PY
  then :; fi
  verdict=$(cat /tmp/ytkey.txt 2>/dev/null | head -1)
  case "$verdict" in
    OK) echo "  ✅ YouTube key dùng được" ;;
    NETWORK) echo "  ⚠ YouTube: không kết nối được (mạng) — không kết luận được" ;;
    *keyInvalid*|*API_KEY_INVALID*)
      echo "  ❌ YouTube: KEY SAI → copy lại ở Cloud Console → APIs & Services → Credentials"
      FAIL=$((FAIL+1)) ;;
    *accessNotConfigured*|*SERVICE_DISABLED*)
      echo "  ❌ YouTube: dự án CHƯA BẬT \"YouTube Data API v3\""
      echo "     → console.cloud.google.com → APIs & Services → Library → tìm"
      echo "       \"YouTube Data API v3\" → Enable → đợi ~1 phút → chạy lại"
      FAIL=$((FAIL+1)) ;;
    *quota*)
      echo "  ⚠ YouTube: hết quota hôm nay (reset 00:00 giờ Thái Bình Dương)"
      FAIL=$((FAIL+1)) ;;
    *ipReferer*)
      echo "  ❌ YouTube: key bị giới hạn IP/referrer"
      echo "     → Credentials → chọn key → Application restrictions → None"
      FAIL=$((FAIL+1)) ;;
    *) echo "  ❌ YouTube: $verdict"; FAIL=$((FAIL+1)) ;;
  esac
fi

echo
if [ "$FAIL" -gt 0 ]; then
  echo "❌ $FAIL key CHƯA dùng được → sửa theo gợi ý ở trên rồi chạy lại."
  exit 1
fi
echo "✅ Không có key nào hỏng."
