#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_app.sh — chuẩn bị project Flutter mà KHÔNG ghi đè code của bạn.
#
# Cách làm: sinh một project Flutter tạm ở nơi khác, rồi chỉ COPY các thư mục
# platform (android/, ios/, windows/…) vào app/. Nhờ vậy lib/main.dart và
# pubspec.yaml của bạn không bao giờ bị flutter create ghi đè.
#
# Dùng:  bash scripts/setup_app.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$ROOT/app"

if ! command -v flutter >/dev/null 2>&1; then
  echo "❌ Chưa có Flutter trên PATH."
  echo "   Cài: https://docs.flutter.dev/get-started/install"
  echo "   Sau khi cài, MỞ LẠI terminal rồi chạy lại lệnh này."
  exit 1
fi

echo "▶ $(flutter --version | head -1)"

if [ ! -f "$APP/pubspec.yaml" ]; then
  echo "❌ Không thấy app/pubspec.yaml — bạn đang chạy script trong thư mục sai?"
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "▶ Sinh project Flutter tạm (sinh platform folders)…"
flutter create --org com.anistream --project-name anistream \
  --platforms=android,ios,web,windows,macos,linux "$TMP/gen" >/dev/null

echo "▶ Copy platform folders vào app/ (không đụng tới lib/)…"
for d in android ios windows macos linux web; do
  if [ -d "$TMP/gen/$d" ]; then
    rm -rf "$APP/$d"
    cp -R "$TMP/gen/$d" "$APP/$d"
    echo "   + $d/"
  fi
done
[ -f "$TMP/gen/.metadata" ] && cp "$TMP/gen/.metadata" "$APP/.metadata"
[ -f "$TMP/gen/.gitignore" ] && cp -n "$TMP/gen/.gitignore" "$APP/.gitignore" || true

# pubspec của Flutter có thể ghi đè bản của mình → khôi phục từ git/backup nếu cần
if ! grep -q "flutter_riverpod" "$APP/pubspec.yaml"; then
  echo "⚠  pubspec.yaml trông không phải bản của AniStream."
fi

echo "▶ flutter pub get…"
( cd "$APP" && flutter pub get )

cat <<'TXT'

✅ Xong!

Chạy thử (chọn 1):
  cd app && flutter run -d chrome        # nhanh nhất, không cần máy ảo
  cd app && flutter run -d windows       # desktop (cần Visual Studio C++)
  cd app && flutter devices              # xem thiết bị/điện thoại có sẵn

Lần chạy đầu mất 1–3 phút (tải package). Sau đó vài giây.
TXT
