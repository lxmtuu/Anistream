#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# preflight.sh — kiểm tra mọi thứ TRƯỚC khi chạy ingest thật.
#
# Vì sao cần: `python3 -m ingest.main all` mất vài phút và gọi AniList/YouTube
# nhiều lần, rồi mới chết ở bước ghi DB nếu bạn nhầm key hoặc quên chạy
# schema.sql. Script này bắt 6 lỗi phổ biến đó trong ~5 giây.
#
# Dùng:  bash scripts/preflight.sh
#        bash scripts/preflight.sh <supabase-url> <key>     # không dùng .env
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PASS=0; WARN=0; FAIL=0
ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
warn() { echo "  ⚠️  $1"; WARN=$((WARN+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }

echo "▶ AniStream preflight"
echo

# ── 1. Python + thư viện ────────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  ok "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
else
  bad "không có python3 trên PATH"
fi
if python3 -c 'import requests' 2>/dev/null; then
  ok "đã cài package requests"
else
  bad "thiếu requests → pip install -r ingest/requirements.txt"
fi

# ── 2. Biến môi trường ─────────────────────────────────────────────────────
if [ "${1:-}" != "" ]; then
  SUPABASE_URL="${1%/}"; SUPABASE_SERVICE_KEY="${2:-}"
  echo "  (dùng URL/key truyền qua tham số)"
elif [ -f .env ]; then
  # đọc .env không ghi đè biến đã có
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac
    k="$(echo "$k" | tr -d ' ')"; v="$(echo "$v" | sed -e 's/^["'\'']//' -e 's/["'\'']$//')"
    [ -z "${!k:-}" ] && export "$k=$v"
  done < .env
  SUPABASE_URL="${SUPABASE_URL:-}"; SUPABASE_SERVICE_KEY="${SUPABASE_SERVICE_KEY:-}"
  ok "đọc .env"
else
  SUPABASE_URL=""; SUPABASE_SERVICE_KEY=""
  warn "không có .env → chạy được --dry-run, nhưng KHÔNG ghi được DB"
fi

SUPABASE_URL="${SUPABASE_URL%/}"

# ── 3. URL ─────────────────────────────────────────────────────────────────
if [[ "$SUPABASE_URL" =~ ^https://[a-z0-9]+\.supabase\.co$ ]]; then
  ok "SUPABASE_URL hợp lệ ($SUPABASE_URL)"
elif [ -z "$SUPABASE_URL" ]; then
  bad "thiếu SUPABASE_URL (xem .env.example)"
else
  bad "SUPABASE_URL trông sai: '$SUPABASE_URL' (phải là https://<ref>.supabase.co, KHÔNG có /rest/v1)"
fi

# ── 4. Key: phải là service_role, không phải anon ──────────────────────────
# Đọc payload của JWT (không verify) để biết "role". Nhầm anon key là lỗi phổ
# biến nhất: mọi lệnh ghi sẽ fail với lỗi RLS rất khó hiểu.
KEY_ROLE=""
if [ -n "$SUPABASE_SERVICE_KEY" ]; then
  KEY_ROLE=$(printf '%s' "$SUPABASE_SERVICE_KEY" | python3 -c '
import sys, json, base64
tok = sys.stdin.read().strip()
try:
    part = tok.split(".")[1]
    part += "=" * (-len(part) % 4)
    print(json.loads(base64.urlsafe_b64decode(part)).get("role", ""))
except Exception:
    print("")
' 2>/dev/null)
  case "$KEY_ROLE" in
    service_role) ok "key là service_role (đúng — chỉ dùng ở worker/cron)" ;;
    anon)         bad "key là ANON → RLS sẽ chặn mọi lệnh ghi. Lấy key service_role trong Project Settings → API" ;;
    "")           warn "không đọc được role từ key (không phải JWT?) — bỏ qua kiểm tra này" ;;
    *)            warn "key có role '$KEY_ROLE' (thường là service_role mới đúng)" ;;
  esac
else
  bad "thiếu SUPABASE_SERVICE_KEY"
fi

# ── 5. Bảng đã có chưa (schema.sql đã chạy chưa) ───────────────────────────
if [ -n "$SUPABASE_URL" ] && [ -n "$SUPABASE_SERVICE_KEY" ]; then
  check_table() { # $1 = bảng, $2 = gợi ý
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 \
      -H "apikey: $SUPABASE_SERVICE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
      "$SUPABASE_URL/rest/v1/$1?select=*&limit=1")
    case "$code" in
      200|206) ok "bảng $1 tồn tại" ;;
      404)     bad "bảng $1 KHÔNG có → dán toàn bộ db/schema.sql vào SQL Editor rồi Run" ;;
      401|403) bad "không có quyền đọc $1 (HTTP $code) → key sai hoặc RLS chặn" ;;
      000)     bad "không kết nối được tới $SUPABASE_URL (mất mạng? URL sai?)" ;;
      *)       warn "bảng $1 trả HTTP $code ($2)" ;;
    esac
  }
  check_table anime        "catalog"
  check_table episodes     "lịch phát"
  check_table streaming_links "link video official"
  check_table ingest_runs  "audit của cron"
else
  warn "bỏ qua kiểm tra bảng (thiếu URL/key)"
fi

# ── 6. Tuỳ chọn (không chặn) ───────────────────────────────────────────────
[ -n "${TMDB_API_KEY:-}" ]    && ok "có TMDB_API_KEY (tên + tóm tắt tiếng Việt)" \
                              || warn "không có TMDB_API_KEY → thiếu title_vi/synopsis_vi"
[ -n "${YOUTUBE_API_KEY:-}" ] && ok "có YOUTUBE_API_KEY (deep backfill)" \
                              || warn "không có YOUTUBE_API_KEY → chỉ lấy ~15 video mới nhất/kênh"

# ── 7. Edge Functions đã deploy chưa ──────────────────────────────────────
if [ -n "$SUPABASE_URL" ] && [ -n "$SUPABASE_SERVICE_KEY" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 \
    -H "apikey: $SUPABASE_SERVICE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
    "$SUPABASE_URL/functions/v1/home")
  case "$code" in
    200) ok "Edge Function /home đã deploy và trả 200" ;;
    404) warn "/home chưa deploy → chạy: supabase functions deploy home search schedule anime" ;;
    *)   warn "/home trả HTTP $code" ;;
  esac
fi

# ── Kết luận ─────────────────────────────────────────────────────────────
echo
echo "─────────────────────────────────────────────"
echo "  ✅ $PASS   ⚠️  $WARN   ❌ $FAIL"
if [ "$FAIL" -gt 0 ]; then
  cat <<'TXT'

  Có lỗi chặn → ĐỪNG chạy ingest thật. Sửa các mục ❌ ở trên trước.
  Muốn thử logic mà không cần DB:
      python3 -m ingest.main youtube --dry-run --limit 12
TXT
  exit 1
fi
cat <<'TXT'

  Sẵn sàng. Chạy ingest thật:
      python3 -m ingest.main all
  Sau đó kiểm tra app dùng dữ liệu thật:
      cd app && flutter run --dart-define=USE_MOCK=false \
        --dart-define=API_BASE=<url>/functions/v1 --dart-define=ANON_KEY=<anon key>
TXT
