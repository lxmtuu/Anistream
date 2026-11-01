# Báo cáo rà soát repo AniStream — 01/11/2026

Rà soát toàn bộ 198 file đang được track trên nhánh `arena/95786384-anistream`
(gốc `main` @ `6bfb762`). Mục tiêu: tìm cái **sai thật** (không phải góp ý gu),
rồi sửa luôn những cái sửa được mà không cần máy có Flutter SDK.

---

## 1. Đã chạy được những gì (bằng chứng, không phải "chắc là chạy")

| Kiểm tra | Cách chạy | Kết quả |
|---|---|---|
| Unit test ingest | `python3 -m unittest discover -s tests -v` | ✅ **5/5 pass** |
| Cú pháp TypeScript của 5 Edge Function + 6 file `_shared` | `esbuild` parse từng file | ✅ 11/11 sạch |
| Toàn vẹn dữ liệu mock (`app/lib/data/mock_data.dart`) | parse JSON + đối chiếu id | ✅ 52 anime, 4 shelf, 24 slot lịch; **0 id treo**; 16 bộ có video phát được; 0 id trùng |
| Cú pháp toàn bộ Python (`ingest/`, `tools/`) | `python3 -m compileall` | ✅ sạch |
| Import nội bộ trong `ingest/` | AST scan | ✅ không có import trỏ vào file không tồn tại |
| Flutter analyze / test | ❌ **không chạy được trong sandbox** (không có Flutter SDK, pub.dev không truy cập được) | → đã thêm CI `.github/workflows/app.yml` để GitHub chạy hộ |

Nói thẳng: **phần Dart vẫn chưa được biên dịch lần nào trong phiên này.** Tớ đọc và
soát tay từng file, nhưng chỉ `flutter analyze` mới chứng minh được.

---

## 2. Lỗi tìm thấy (theo mức độ)

### 🔴 Nghiêm trọng — bản release sẽ hỏng

**2.1. `AndroidManifest.xml` thiếu quyền `INTERNET` → APK release không có mạng**
Template Flutter chỉ khai báo `INTERNET` trong `android/app/src/debug/` và `profile/`.
Manifest chính (dùng cho release) không có. Hệ quả: bản `flutter build apk --release`
— đúng bản bạn định gửi 10 người dùng ở `VIEC_CAN_LAM.md` việc 4 — **không tải được
poster, không gọi được API, không phát được YouTube**, trong khi bản debug vẫn chạy
ngon. Đây là loại lỗi tệ nhất: chỉ xuất hiện đúng lúc phát hành.
→ **Đã sửa**: thêm `INTERNET` + `POST_NOTIFICATIONS` (Android 13+ không khai báo thì
thông báo "tập mới vừa ra" không bao giờ hiện).

**2.2. `scripts/setup_app.sh` / `.ps1` xoá trắng thư mục platform**
Repo **đã có** `android/ ios/ web/ windows/ macos/ linux/` (ai đó đã chạy
`flutter create` trên máy Windows — xem `app/.flutter-plugins-dependencies`). Nhưng
script cũ vẫn `rm -rf app/android` rồi copy bản mới → **xoá mất** các chỉnh tay trong
manifest (chính là 2 quyền vừa thêm), tên app, `applicationId`, cấu hình iOS…
→ **Đã sửa**: script giờ chỉ sinh platform **còn thiếu**, không bao giờ copy đè.

**2.3. Watchlist mất sạch mỗi lần tắt app**
`watchlistProvider` giữ `Set<int>` trong RAM. Người dùng bấm 🔖 20 bộ, tắt app, mở
lại → trống. Đồng thời `PushService.syncSubscriptions` gửi lên backend danh sách
rỗng mỗi lần khởi động → **push "tập mới" gần như không bao giờ tới đúng người**.
→ **Đã sửa**: thêm `app/lib/data/watchlist_store.dart` (SharedPreferences, có
interface để đổi sang Drift/Supabase sau) + hydrate/ghi tự động. Không thêm
dependency mới, không cần đăng nhập, chạy cả trên web/desktop.

### 🟠 Chức năng sai nhưng không sập app

**2.4. Deep link `/anime/<slug>` báo "Không tìm thấy" với phần lớn anime**
`DetailScreen` tra **chỉ trong feed `/home`** (52 bộ mock, hoặc ~40 bộ thật). Bấm
thông báo "tập N vừa ra" cho một bộ không nằm trong feed → màn hình trắng chữ
"Không tìm thấy anime này". Đúng luồng quan trọng nhất của app bị gãy.
→ **Đã sửa**: thêm `fetchAnime(slug)` vào repository (mock + `/anime?slug=`) và
`animeDetailProvider`: có trong feed thì dùng luôn (0 request), không có thì gọi API.

**2.5. Ô tìm kiếm treo vô hạn khi mất mạng**
`SearchScreen._run` không `try/catch`: `dio` ném lỗi → Future ném ra ngoài,
`_loading` không bao giờ về `false` → spinner quay mãi, chỉ thoát được bằng cách
gõ lại. Người dùng Việt dùng 3G/4G chập chờn sẽ gặp liên tục.
→ **Đã sửa**: bắt lỗi + màn hình "Không tìm được — kiểm tra kết nối" + nút thử lại,
kèm chống race (kết quả của từ khoá cũ không đè lên từ khoá mới).

**2.6. Nút "Tất cả" trên trang chủ dẫn tới tab Lịch phát**
Nhãn nói một đằng, đích đến một nẻo → người dùng bấm xong tưởng app lỗi.
→ **Đã sửa**: đổi nhãn thành "Lịch phát".

### 🟡 Vệ sinh repo / tài liệu sai

**2.7. `app/.flutter-plugins-dependencies` được commit**
File sinh tự động, chứa **đường dẫn tuyệt đối** `C:\Users\ADMIN\...` của máy dev.
Mỗi người clone về là diff loạn, và lộ cấu trúc máy.
→ **Đã sửa**: `git rm --cached` + thêm `.gitignore` gốc và `app/.gitignore`
(che `google-services.json`, `firebase_options.dart`, keystore, `build/`…).

**2.8. Tài liệu bắt chạy `flutter create` — giờ là bước nguy hiểm**
`README.md`, `BAT_DAU_TU_DAY.md`, `app/README.md`, `VIEC_CAN_LAM.md` đều ghi
"chạy `flutter create … .` là bắt buộc". Điều đó chỉ đúng khi repo chưa có platform.
Giờ đã có, lệnh đó sẽ ghi đè cấu hình platform.
→ **Đã sửa**: cập nhật 4 tài liệu; từ nay chỉ cần `cd app && flutter pub get && flutter run`.

**2.9. Không có CI cho app**
`.github/workflows/ingest.yml` lo phần dữ liệu, nhưng phần Dart (4.700 dòng) chưa
từng được kiểm tra tự động.
→ **Đã sửa**: thêm `.github/workflows/app.yml` — `flutter analyze` + `flutter test`
trên mỗi push/PR đụng `app/`.

**2.10. Không có test Dart nào**
→ **Đã thêm** `app/test/watchlist_test.dart` (6 test: lưu/đọc, dữ liệu hỏng, dữ liệu
cũ dạng chuỗi, hydrate, ghi khi toggle, không ghi đè thao tác sớm).

---

## 3. Những gì tớ thấy nhưng **cố ý chưa sửa** (và vì sao)

| Vấn đề | Vì sao chưa làm |
|---|---|
| `firebase_options.dart` / `google-services.json` không có → push im lặng | Cần project Firebase **của bạn** (`flutterfire configure`). Không thể sinh hộ. App vẫn chạy bình thường (đã bọc try/catch). |
| Chưa có đăng nhập (Supabase Auth) | Cần bật provider trên project Supabase của bạn + cấu hình email template. Hạ tầng đã sẵn (`profiles`, RLS trong `db/schema.sql`), chỉ thiếu phía config. |
| `db/schema.sql` chưa được chạy thử trên Postgres thật | Sandbox không có Postgres. Nên chạy trên Supabase và để ý dòng nào báo lỗi. |
| `tools/gen_mock.py` cần mạng tới AniList | Chính sách mạng của sandbox chặn. Dữ liệu mock hiện tại đã kiểm tra toàn vẹn. |
| Chưa có deep link OS-level (`anistream://`) | Cần thêm `intent-filter` + Universal Links, và một hàm parse URI trong router. Nên làm cùng lúc với lúc cấu hình Firebase (đều là cấu hình platform). |
| Desktop dùng webview cho YouTube | Đã ghi rõ trong `player_screen.dart`; cách xử lý hiện tại (mở app/trình duyệt) là chấp nhận được cho v1. |
| `analysis_options.yaml` bật `prefer_single_quotes` nhưng code dùng cả `"` | Chỉ là style, `flutter analyze` không fail vì lint info. Sửa 4.700 dòng để đẹp lint là việc vô nghĩa lúc này. |

---

## 4. Thứ tự làm tiếp (đã cập nhật)

```
1. [x] Rà soát toàn repo + sửa 6 lỗi thật            ← phiên này
2. [~] Watchlist bền trên máy (SharedPreferences)      ← xong; auth + đồng bộ đa thiết bị còn lại
3. [ ] Bật CI: push nhánh này lên GitHub → xem tab Actions
        → nếu `flutter analyze` báo lỗi, đó là lỗi biên dịch thật, sửa ngay
4. [ ] Chạy `flutter run` trên máy bạn (VIEC_CAN_LAM.md việc 1)
5. [ ] Supabase + ingest + deploy (việc 2) — rồi mới tới auth
6. [ ] Kiểm tra phụ đề tiếng Việt (việc 3) — rủi ro sản phẩm lớn nhất
```

Nguyên tắc không đổi: **không thêm feature mới cho tới khi có người dùng thật.**
Việc số 2 ở trên không phải feature — nó là sửa lỗi mất dữ liệu người dùng.
