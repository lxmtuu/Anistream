# CHECKLIST QA — chạy APK release trên máy thật

**Dành cho:** bước "10 người dùng thật". Mục tiêu là biết **đúng/sai trong ~15 phút**,
không phải "thấy app mở được là xong".

> Tại sao phải là bản **release**, không phải `flutter run`: bản debug có sẵn quyền
> INTERNET và rất nhiều thứ dễ dãi. Manifest release từng thiếu `INTERNET` (đã sửa
> ngày 01/11/2026) — nếu chỉ test bằng `flutter run`, bạn sẽ không bao giờ thấy lỗi đó.

---

## 0. Chuẩn bị (5 phút)

```bash
cd app
flutter --version            # cần >= 3.22
flutter doctor               # không cần xanh hết, chỉ cần không lỗi Android
flutter build apk --release  # ~3-5 phút lần đầu
```
File ra: `app/build/app/outputs/flutter-apk/app-release.apk`

Cài lên máy (chọn 1):
- Cắm cáp: `flutter install --release`
- Hoặc copy file APK sang điện thoại rồi mở (cần bật "Cài từ nguồn không xác định")

**Bản này chạy mock data** (52 bộ) → không cần Supabase, chỉ cần mạng để tải poster
và gọi YouTube. Muốn test với dữ liệu thật, xem mục 7.

---

## 1. Sáu điểm kiểm tra (mỗi điểm ~2 phút)

Ghi lại ✅/❌ cho từng điểm. Điểm nào ❌ thì chụp màn hình + lấy log.

### ① Poster & dữ liệu tải được → chứng minh **quyền INTERNET** có hiệu lực
Mở app, chờ 3 giây.
- **Đúng:** trang chủ có ảnh poster thật, các hàng "Xem ngay — miễn phí", "Tập mới".
- **Sai:** toàn ô xám + dòng lỗi mạng.

### ② Phát video → chứng minh nhúng YouTube hoạt động trên máy thật
Bấm nút **▶ Xem ngay** ở banner đầu trang.
- **Đúng:** player YouTube hiện ra, video official chạy (có thể có quảng cáo của chủ kênh — bình thường, đừng chặn).
- **Sai:** "Video unavailable" → chủ kênh đã tắt nhúng, cần chạy lại `python3 -m ingest.main youtube`.
- Bấm back: phải về đúng trang trước, app không bị treo.

### ③ Theo dõi (🔖) và **thư viện phải còn sau khi tắt app** → chứng minh watchlist lưu bền
1. Vào 3 bộ bất kỳ → bấm 🔖 (biểu tượng bookmark ở góc phải trên).
2. Vào tab **Thư viện** → thấy đúng 3 bộ, góc phải có chữ "3 bộ".
3. **Tắt hẳn app** (đừng chỉ bấm back — dùng nút điều hướng gần đây → vuốt bỏ app).
4. Mở lại → vào Thư viện.
- **Đúng:** vẫn 3 bộ.
- **Sai:** trống → bug lưu trữ quay lại, gửi tớ ngay.

### ④ Mất mạng ở tab Tìm → chứng minh không treo vô hạn
1. Bật **chế độ máy bay**.
2. Vào tab **Tìm**, gõ `frieren`.
- **Đúng:** sau ~2 giây hiện "Không tìm được — kiểm tra kết nối mạng" + nút **Thử lại**.
- **Sai:** vòng xoay chạy mãi không dừng, hoặc app trắng.
3. Tắt máy bay → bấm **Thử lại** → ra kết quả (không cần gõ lại).

### ⑤ Deep link từ thông báo → chứng minh mở đúng bộ, kể cả bộ **không** có trong trang chủ
Cách nhanh nhất (không cần chờ thông báo thật):
```bash
adb shell am start -a android.intent.action.VIEW \
  -d "anistream://anime/sousou-no-frieren" com.anistream.anistream
```
- **Đúng:** mở thẳng trang chi tiết bộ đó.
- **Ứng dụng chưa cài intent-filter** → lệnh trên có thể báo lỗi "no Activity found".
  Khi đó kiểm tra bằng cách khác: bấm thông báo thật sau khi cấu hình Firebase (mục 6).
- Bộ **không** nằm trong 52 bộ mock: với `USE_MOCK=true` sẽ báo "Không tìm thấy" (đúng,
  vì mock chỉ có 52 bộ). Với backend thật (mục 7) thì phải mở được.

### ⑥ Vòng đời cơ bản → chứng minh không crash khi dùng bình thường
- Xoay ngang/dọc ở trang chi tiết → không mất nội dung.
- Chuyển qua lại 4 tab 5 lần → mỗi tab giữ vị trí cuộn (IndexedStack), không reload.
- Bấm back ở trang chủ → **thoát app**, không kẹt màn hình trắng.
- Kéo xuống để refresh trang chủ → có vòng xoay rồi dữ liệu về.

---

## 2. Bảng ghi kết quả (copy ra để điền)

| # | Điểm kiểm tra | Kết quả | Ghi chú |
|---|---|---|---|
| ① | Poster tải được (INTERNET) | ⬜ | |
| ② | Video official phát được | ⬜ | |
| ③ | 🔖 còn sau khi tắt app | ⬜ | |
| ④ | Mất mạng ở Tìm → lỗi + Thử lại | ⬜ | |
| ⑤ | Deep link mở đúng bộ | ⬜ | |
| ⑥ | Xoay/chuyển tab/refresh/back | ⬜ | |

**Nếu tất cả ✅:** gửi APK cho 10 người, hỏi đúng 3 câu trong `VIEC_CAN_LAM.md` việc 4.
**Nếu có ❌:** gửi tớ (1) số thứ tự điểm sai, (2) ảnh chụp, (3) log:
```bash
adb logcat -d | grep -iE "flutter|anistream|E/" | tail -80
```

---

## 3. Lấy log khi cần

```bash
# app đang chạy, lấy log Flutter
adb logcat -s flutter:V

# lỗi crash
adb logcat -b crash -d | tail -60
```

---

## 4. Bản release có ký chưa?

`flutter build apk --release` chưa có keystore sẽ ký bằng **debug key**. Cài lên máy
vẫn chạy, nhưng **không được đưa lên Google Play**. Khi cần phát hành thật:

```bash
keytool -genkey -v -keystore ~/anistream-upload.jks -keyalg RSA \
  -keysize 2048 -validity 10000 -alias upload
```
Rồi tạo `app/android/key.properties` (đã nằm trong `.gitignore`, **không commit**):
```properties
storePassword=...
keyPassword=...
keyAlias=upload
storeFile=/duong/dan/anistream-upload.jks
```

---

## 5. Những gì bản mock **không** kiểm tra được

Đừng kết luận "app ổn" chỉ dựa trên bản mock:

| Không kiểm tra được | Kiểm ở đâu |
|---|---|
| Dữ liệu thật, số tập official thật | mục 7 (Supabase + ingest) |
| Tìm kiếm qua 20.000 bộ | mục 7 |
| Lịch phát đúng giờ thật | mục 7 |
| Thông báo "tập mới vừa ra" | mục 6 (Firebase) |
| Đồng bộ thư viện giữa 2 máy | chưa có (cần Auth — mục 8) |

---

## 6. Bật thông báo thật (tuỳ chọn, ~20 phút)

```bash
dart pub global activate flutterfire_cli
flutterfire configure        # chọn project Firebase (miễn phí)
```
File sinh ra: `app/lib/firebase_options.dart` + `android/app/google-services.json`
(**đã gitignore**, không commit). Sau đó `flutter build apk --release` lại.

Kiểm tra:
1. Bấm theo dõi 1 bộ **đang chiếu**.
2. Mở Supabase → Table Editor → `push_subscriptions`: phải có 1 dòng với `device_id`,
   `token`, `anime_ids` chứa anime_id đó, `is_active = true`.
   - Không có dòng nào → RLS từ chối (thiếu header `x-device-id`) hoặc thiếu API_BASE/ANON_KEY.
3. Chạy cron push (thủ công):
```bash
curl -X POST "$BASE/push?dry_run=true" -H "x-cron-secret: $PUSH_CRON_SECRET"
```
`dry_run=true` không gửi tin, chỉ in danh sách người sẽ nhận → kiểm tra logic trước
khi bật thật.

---

## 7. Chạy với backend thật (trước khi gửi cho 10 người)

```bash
# DB + 5 Edge Function đã deploy sẵn (xem supabase/README.md §0).
# Ở đây chỉ còn: nạp dữ liệu thật + build app trỏ vào backend thật.
bash scripts/preflight.sh
python3 -m ingest.main all

# kiểm nhanh API sau khi ingest (0 → phải có số > 0)
BASE=https://snpzrblwiamqtrnifdis.supabase.co/functions/v1
curl -s "$BASE/home" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(len(d['anime']), 'anime /', len(d['shelves']), 'shelf')"
curl -s "$BASE/search?q=a&page=2" | head -c 120   # phải là 200 + items:[] (KHÔNG được 500)

# build app trỏ vào backend thật
cd app
flutter build apk --release \
  --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://snpzrblwiamqtrnifdis.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNucHpyYmx3aWFtcXRybmlmZGlzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM1MjQyOTEsImV4cCI6MjEwOTEwMDI5MX0.TJIm0tDjXk82ZCIQbVgKk4EMq30vmdA-LmsaTWaIkZY
```
⚠️ Chỉ dùng **anon key** trong app. Không bao giờ nhúng `service_role`.

Sau đó chạy lại 6 điểm ở mục 1: điểm ① phải thấy dữ liệu thật (nhiều hơn 52 bộ),
điểm ② xem được video của bộ bất kỳ, điểm ⑤ deep link mở được cả bộ ngoài trang chủ.

---

## 8. Còn thiếu gì để "thư viện đồng bộ 2 máy"

Cần: Supabase Auth (magic link hoặc Google) + đọc/ghi bảng `watchlist`.
Hạ tầng DB đã sẵn: `profiles` + RLS + trigger tạo profile khi đăng ký
(`db/migrations/20261101_auth_profile_trigger.sql`).
Chưa làm vì cần bạn bật Auth provider trong project Supabase — và vì đúng thứ tự là
"có người dùng thật trước, đồng bộ sau".
