#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# check_net.sh — chẩn đoán "vì sao ingest không gọi được API?"
#
# Vì sao cần: log thật 02/11/2026 cho thấy 39/39 bộ Jikan `ConnectTimeout`, trong
# khi TMDB vẫn lấy được dữ liệu (63/126 bộ có tmdb_id). Không có công cụ nào trả
# lời được câu "host nào tới được, host nào bị chặn, chặn ở DNS hay ở 443?" nên
# phải đoán mò. Script này đo từng tầng rồi in KẾT LUẬN.
#
# Dùng:  bash scripts/check_net.sh
# Exit:  0 = tất cả host cần thiết đều tới được
#        1 = có host bị chặn (in rõ bị chặn ở đâu)
#        2 = thiếu curl
#
# Chỉ dùng curl (+ nslookup/python nếu có) — chạy được trên Git Bash Windows,
# macOS, Linux. Không cần quyền admin, không đổi cấu hình máy.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

command -v curl >/dev/null 2>&1 || { echo "❌ cần curl" >&2; exit 2; }

TIMEOUT="${TIMEOUT:-10}"
FAIL=0

# host|nhãn|có bắt buộc không
HOSTS=(
  "graphql.anilist.co|AniList (job A/B/E)|bat_buoc"
  "api.jikan.moe|Jikan/MAL (job F)|tuy_chon"
  "api.themoviedb.org|TMDB (job D)|bat_buoc"
  "www.googleapis.com|YouTube Data API (job C)|bat_buoc"
  "snpzrblwiamqtrnifdis.supabase.co|Supabase (ghi dữ liệu)|bat_buoc"
)

echo "▶ Kiểm mạng cho ingest  (timeout ${TIMEOUT}s mỗi lần)"
echo

# ── 1. DNS ───────────────────────────────────────────────────────────────────
dns_lookup() { # $1=host → in IP (cách nhau dấu cách) hoặc rỗng
  local h="$1" out=""
  if command -v getent >/dev/null 2>&1; then
    out="$(getent ahosts "$h" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')"
  fi
  if [ -z "$out" ] && command -v nslookup >/dev/null 2>&1; then
    out="$(nslookup "$h" 2>/dev/null \
      | awk '/^Address: *[0-9]/{print $2} /^Addresses:/{for(i=2;i<=NF;i++) print $i}' \
      | tr -d ',' | grep -E '^[0-9]' | sort -u | tr '\n' ' ')"
  fi
  if [ -z "$out" ] && command -v python3 >/dev/null 2>&1; then
    out="$(python3 - "$h" <<'PY' 2>/dev/null
import socket, sys
try:
    print(" ".join(sorted({r[4][0] for r in socket.getaddrinfo(sys.argv[1], 443)})))
except Exception:
    pass
PY
)"
  fi
  printf '%s' "$out"
}

# ── 2. TCP/TLS 443 qua IPv4 và IPv6 ──────────────────────────────────────────
probe() { # $1=v4|v6  $2=url  → in mã HTTP (000 = không kết nối được)
  curl "-$1" -sS -m "$TIMEOUT" -o /dev/null -w '%{http_code}' "$2" 2>/dev/null || true
}

print_row() { printf '  %-46s %s\n' "$1" "$2"; }

echo "── DNS ──"
declare -A IPS
for row in "${HOSTS[@]}"; do
  IFS='|' read -r host label must <<< "$row"
  ips="$(dns_lookup "$host")"
  IPS["$host"]="$ips"
  if [ -z "$ips" ]; then
    print_row "$label" "❌ KHÔNG phân giải được tên (DNS chặn / sai DNS)"
    FAIL=1
  else
    print_row "$label" "✓ $(echo "$ips" | tr ' ' '\n' | head -3 | tr '\n' ' ')"
  fi
done

echo
echo "── Kết nối HTTPS (IPv4 / IPv6) ──"
declare -A VERDICT
for row in "${HOSTS[@]}"; do
  IFS='|' read -r host label must <<< "$row"
  url="https://$host/"
  case "$host" in
    "graphql.anilist.co") url="https://graphql.anilist.co/" ;;
    "www.googleapis.com") url="https://www.googleapis.com/discovery/v1/apis" ;;
    "snpzrblwiamqtrnifdis.supabase.co") url="https://snpzrblwiamqtrnifdis.supabase.co/rest/v1/" ;;
    "api.themoviedb.org") url="https://api.themoviedb.org/3/configuration" ;;
    "api.jikan.moe") url="https://api.jikan.moe/v4/anime/30276/episodes" ;;
  esac

  v4="$(probe 4 "$url")"
  v6="$(probe 6 "$url")"
  # 000 = không tới được; 000/401/404/4xx/5xx đều là ĐÃ tới server
  ok4=1; [ "$v4" = "000" ] && ok4=0
  ok6=1; [ "$v6" = "000" ] && ok6=0

  if [ "$ok4" = "1" ] && [ "$ok6" = "1" ]; then
    print_row "$label" "✓ v4=$v4  v6=$v6"
    VERDICT["$host"]=ok
  elif [ "$ok4" = "1" ]; then
    print_row "$label" "⚠ v4=$v4 (OK)  v6=$v6 → CHỈ IPv6 lỗi"
    VERDICT["$host"]=ipv4_only
  elif [ "$ok6" = "1" ]; then
    print_row "$label" "⚠ v4=$v4  v6=$v6 (OK) → CHỈ IPv4 lỗi"
    VERDICT["$host"]=ipv6_only
  else
    print_row "$label" "❌ v4=$v4  v6=$v6 → KHÔNG kết nối được (firewall/ISP)"
    VERDICT["$host"]=blocked
  fi
done

# ── 3. Kết luận ──────────────────────────────────────────────────────────────
echo
echo "── Kết luận ──"
for row in "${HOSTS[@]}"; do
  IFS='|' read -r host label must <<< "$row"
  v="${VERDICT[$host]:-blocked}"
  case "$v" in
    ok) ;;
    ipv4_only)
      echo "  · $label: chặn IPv6 → ingest/net.py sẽ tự ép IPv4, KHÔNG cần sửa gì."
      ;;
    ipv6_only)
      echo "  · $label: chỉ IPv6 tới được (hiếm) → kiểm cấu hình mạng."
      ;;
    blocked)
      if [ "$must" = "bat_buoc" ]; then
        echo "  ✗ $label: BỊ CHẶN — job dùng host này sẽ không chạy được trên máy bạn."
        FAIL=1
      else
        echo "  ⚠ $label: BỊ CHẶN — job này sẽ fail (đúng như thiết kế, exit ≠ 0)."
        echo "      Cách xử lý: (a) thêm HTTPS_PROXY vào .env, (b) chạy job trên"
        echo "      GitHub Actions, (c) đổi DNS sang 1.1.1.1 nếu chỉ DNS bị chặn."
      fi
      ;;
  esac
done

echo
if [ -z "$(dns_lookup api.jikan.moe)" ]; then
  echo "  Gợi ý: DNS không trả IP cho api.jikan.moe → thử đổi DNS (1.1.1.1 / 8.8.8.8)"
  echo "         hoặc chạy: nslookup api.jikan.moe 1.1.1.1"
fi
echo "  Proxy (nếu công ty/ISP cần): thêm vào .env dòng  HTTPS_PROXY=http://host:port"
echo "  Chạy job Jikan trên CI (không qua mạng của bạn):"
echo "    GH_TOKEN=xxx bash scripts/trigger_ingest.sh lxmtuu/Anistream jikan --fill-gaps"

exit "$FAIL"
