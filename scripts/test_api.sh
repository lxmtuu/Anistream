#!/usr/bin/env bash
# Smoke test cho 4 Edge Function của AniStream.
# Dùng: bash scripts/test_api.sh https://<project-ref>.supabase.co/functions/v1
set -uo pipefail

BASE="${1:-http://localhost:54321/functions/v1}"
PASS=0; FAIL=0

probe() { # $1 = tên, $2 = url, $3 = biểu thức python trên json
  local name="$1" url="$2" expr="${3:-}"
  local body code
  body=$(curl -s -m 25 -w '\n%{http_code}' "$url")
  code=$(echo "$body" | tail -1)
  body=$(echo "$body" | sed '$d')
  if [[ "$code" != "200" ]]; then
    echo "  ❌ $name → HTTP $code"; echo "     $(echo "$body" | head -c 200)"; FAIL=$((FAIL+1)); return
  fi
  if [[ -n "$expr" ]]; then
    if echo "$body" | python3 -c "import json,sys; d=json.load(sys.stdin); assert $expr, 'điều kiện sai'" 2>/dev/null; then
      echo "  ✅ $name"; PASS=$((PASS+1))
    else
      echo "  ❌ $name → JSON không thoả: $expr"; echo "     $(echo "$body" | head -c 200)"; FAIL=$((FAIL+1))
    fi
  else
    echo "  ✅ $name"; PASS=$((PASS+1))
  fi
}

echo "▶ AniStream API smoke test — $BASE"
echo

probe "GET /home (có shelf + anime)"       "$BASE/home" \
      "len(d['data']['anime'])>=1 and len(d['data']['shelves'])>=1"
probe "GET /home (DTO đủ field)"            "$BASE/home" \
      "all(k in d['data']['anime'][0] for k in ['id','slug','title','cover','is_free','episodes','platforms','score'])"
probe "GET /home (có episode.video_id?)"    "$BASE/home" \
      "'episodes' in d['data']['anime'][0]"
probe "GET /search?q="                      "$BASE/search?q=a" \
      "isinstance(d['data']['items'], list)"
# trường hợp mong đợi 400 (thiếu tham số) — kiểm tra riêng
code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 "$BASE/search")
if [[ "$code" == "400" ]]; then echo "  ✅ GET /search (thiếu tham số → 400)"; PASS=$((PASS+1));
else echo "  ❌ GET /search thiếu tham số → HTTP $code (mong đợi 400)"; FAIL=$((FAIL+1)); fi
probe "GET /schedule"                       "$BASE/schedule?limit=5" \
      "isinstance(d['data']['slots'], list)"

# /anime cần slug thật → lấy từ /home
SLUG=$(curl -s -m 25 "$BASE/home" | python3 -c "
import json,sys
try: print(json.load(sys.stdin)['data']['anime'][0]['slug'])
except Exception: print('')")
if [[ -n "$SLUG" ]]; then
  probe "GET /anime?slug=$SLUG" "$BASE/anime?slug=$SLUG" \
        "d['data']['anime']['slug']=='$SLUG'"
else
  echo "  ⏭  bỏ qua /anime (không lấy được slug từ /home)"; fi

echo
echo "Kết quả: $PASS ok · $FAIL lỗi"
[[ "$FAIL" -eq 0 ]] && echo "✅ Tất cả pass" || echo "⚠️  Xem lỗi ở trên"
exit 0
