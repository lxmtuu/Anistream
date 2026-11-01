#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_app.sh — chuẩn bị project Flutter mà KHÔNG ghi đè code của bạn.
#
# Nguyên tắc: CHỈ sinh thư mục platform nào còn THIẾU. Repo đã có sẵn
# android/ ios/ windows/ macos/ linux/ web/ (đã được chỉnh tay: quyền INTERNET,
# POST_NOTIFICATIONS, tên app…). Ghi đè chúng sẽ làm mất các chỉnh sửa đó và
# làm bản release mất mạng → script này không bao giờ copy đè.
#
# Dùng:  bash scripts/setup_app.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APP="$ROOT/app"
PLATFORMS="android ios web windows macos linux"

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

missing=""
for d in $PLATFORMS; do
  [ -d "$APP/$d" ] || missing="$missing $d"
done

if [ -z "$missing" ]; then
  echo "▶ Đã có đủ thư mục platform — bỏ qua bước sinh, không đụng file nào."
else
  echo "▶ Thiếu:$missing → sinh phần còn thiếu vào thư mục tạm…"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT

  flutter create --org com.anistream --project-name anistream \
    --platforms=android,ios,web,windows,macos,linux "$TMP/gen" >/dev/null

  for d in $missing; do
    if [ -d "$TMP/gen/$d" ]; then
      cp -R "$TMP/gen/$d" "$APP/$d"
      echo "   + $d/"
    fi
  done
  [ -f "$APP/.metadata" ] || cp "$TMP/gen/.metadata" "$APP/.metadata" 2>/dev/null || true
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

Muốn bật thông báo "tập mới vừa ra" (tuỳ chọn):
  dart pub global activate flutterfire_cli && flutterfire configure
TXT
