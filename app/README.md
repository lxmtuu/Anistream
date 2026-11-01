# AniStream — App Flutter (v0.1.0)

> Xem anime hợp pháp miễn phí + lịch phát + thư viện của bạn. Mobile & desktop từ 1 codebase.

**Trạng thái:** slice v1 chạy được với **dữ liệu thật** (52 anime, 12 bộ có video official) — chưa cần backend.
**Model:** 🅒 Free Legal Streaming (xem `../DECISION.md`)

---

## Chạy lần đầu (5 phút)

Repo đã có sẵn thư mục platform (`android/ ios/ web/ windows/ macos/ linux/`) với
cấu hình chỉnh tay — nên **không cần và không nên chạy `flutter create`** (lệnh đó
ghi đè manifest, làm bản release mất quyền INTERNET).

```bash
cd app
flutter pub get
flutter run                       # dùng dữ liệu mẫu (mặc định, không cần mạng backend)
```

Chạy trên máy cụ thể:
```bash
flutter devices
flutter run -d windows            # desktop
flutter run -d chrome             # web (nhanh để xem UI)
```

Nối backend thật (khi Supabase đã sẵn):
```bash
flutter run \
  --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://<project>.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=<anon key>
```
> ⚠️ Chỉ dùng **anon key** trong app. `service_role` chỉ nằm ở worker/cron (`.env`), không bao giờ nhúng vào app.

## Kiến trúc thư mục

```
lib/
├── main.dart                     # ProviderScope + MaterialApp.router
├── app/
│   ├── env.dart                  # --dart-define (USE_MOCK / API_BASE / ANON_KEY)
│   ├── theme.dart                # dark-first, AppTheme + VnTime (format giờ VN)
│   └── router.dart               # GoRouter: /, /anime/:slug, /watch, /schedule…
├── core/
│   ├── models/anime.dart         # Anime, Episode, PlatformLink, Shelf, ScheduleSlot
│   ├── models/home_feed.dart     # payload /home + index byId/bySlug
│   └── widgets/                  # NetImage, AnimeCard, AnimeShelf, ShelfSkeleton
├── data/
│   ├── anime_repository.dart     # interface + Mock/Remote impl + providers
│   └── mock_data.dart            # AUTO-GENERATED từ tools/gen_mock.py (dữ liệu thật)
└── features/
    ├── root/root_screen.dart     # 4 tab (IndexedStack, giữ state)
    ├── home/home_screen.dart     # hero + shelf, skeleton, pull-to-refresh
    ├── schedule/schedule_screen.dart  # lịch phát nhóm theo ngày + đếm ngược
    ├── search/search_screen.dart      # debounce 350ms, gợi ý
    ├── detail/detail_screen.dart      # banner, nút Xem, nền tảng chính thức, grid tập
    ├── player/player_screen.dart      # IFrame Player API chính thức của YouTube
    └── library/library_screen.dart    # watchlist (RAM ở v1, Drift ở v1.1)
```

## Dữ liệu mẫu là THẬT

`lib/data/mock_data.dart` sinh bằng:
```bash
python3 ../tools/gen_mock.py
```
Script gọi AniList (catalog, score, banner) + RSS YouTube của **Muse Việt Nam** và **Ani-One Asia** (video ID thật, đã kiểm tra `oEmbed` = cho nhúng) → nên bấm ▶ ở màn hình player **phát được video thật**.

## Đã có gì / chưa có gì

| Có | Chưa (kế hoạch) |
|---|---|
| 4 tab + routing + deep link `anistar://anime/<slug>` | Deep link hệ thống (Universal Links / App Links) |
| Home hero + 4 shelf, skeleton loading, pull-to-refresh | Recommendation cá nhân hoá |
| Lịch phát nhóm theo ngày + đếm ngược | Push notification (FCM) — v1.1 |
| Tìm kiếm debounce | Filter theo thể loại/năm/mùa |
| Chi tiết + nền tảng chính thức (deep link ra ngoài) | Rating/review, comment |
| Player IFrame official (mobile) | Player desktop (đang mở bằng trình duyệt) |
| Watchlist (RAM) | Persist bằng Drift + auth + đồng bộ đa thiết bị |
| Push FCM "tập mới vừa ra" (client + deep link vào đúng tập) | Channel tuỳ biến, tuỳ chọn nhận theo từng bộ |

## Bật thông báo "tập mới vừa ra" (tuỳ chọn)

App chạy được **không cần** bước này. Muốn có push:

```bash
dart pub global activate flutterfire_cli
flutterfire configure          # sinh firebase_options.dart + google-services.json
```

⚠️ Nếu `flutterfire configure` sinh `lib/firebase_options.dart`, sửa 1 dòng trong
`lib/core/push/push_service.dart`:
```dart
await Firebase.initializeApp();                       // trước
await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform); // sau
```

Cơ chế (không cần đăng nhập):
1. App sinh `device_id` ngẫu nhiên → lưu `shared_preferences` (chỉ trên máy, không phải PII)
2. Lấy FCM token → POST vào `push_subscriptions` (RLS chỉ cho ghi dòng `user_id = null`)
3. Mỗi lần **watchlist** thay đổi → `ref.listen` trong `root_screen.dart` tự đồng bộ `anime_ids`
4. Backend cron 15 phút → gửi "Tập N vừa phát" → bấm vào mở đúng `/anime/<slug>`

Android: nếu muốn channel riêng tên "Tập mới", thêm `flutter_local_notifications`
và tạo channel id `new_episode` (v1.1). Hiện FCM dùng channel mặc định.

## Ghi chú kỹ thuật

- **Player:** `youtube_player_iframe` dùng **IFrame Player API chính thức** → hợp pháp, không trích xuất stream, không chặn ads của chủ kênh. Nếu `flutter pub get` báo lỗi API, hạ về v4 và đổi `YoutubePlayer` → `YoutubePlayerIFrame`.
- **Desktop:** webview cho YouTube chưa ổn định trên Windows/Linux → màn player hiện nút "Mở video official" (vẫn hợp pháp). v1.1 sẽ nhúng webview.
- **không dùng `freezed`/`build_runner`** ở v1: `flutter pub get` là chạy, không cần codegen.
- **Không có secret trong repo.** `mock_data.dart` chỉ chứa dữ liệu công khai.
- **Ảnh:** `cached_network_image` → tiết kiệm data (quan trọng với người dùng 3G/4G ở VN).

## Lỗi thường gặp

| Lỗi | Cách sửa |
|---|---|
| `Target of URI doesn't exist` khi mở project | Chưa `flutter pub get` (thiếu `.dart_tool/`) → chạy `cd app && flutter pub get`; nếu thiếu cả thư mục platform thì chạy `bash ../scripts/setup_app.sh` |
| `Because anistream depends on ... version solving failed` | `flutter pub upgrade --major-versions` rồi `flutter pub get` |
| Player báo "Video unavailable" | Video bị chủ kênh tắt nhúng sau khi ingest → chạy lại `python3 -m ingest.main youtube` |
| Ảnh không tải | Kiểm tra mạng; `cached_network_image` cần internet cho lần đầu |
| Lỗi `FontFeature isn't defined` | Đã import `dart:ui show FontFeature` trong `schedule_screen.dart`; nếu bản Flutter cũ hơn 3.16, xoá `fontFeatures` |

## Test

```bash
cd app
flutter analyze            # bắt lỗi biên dịch + lint
flutter test               # unit test (hiện có: watchlist lưu bền trên máy)
```
CI chạy 2 lệnh này tự động ở `.github/workflows/app.yml` mỗi khi sửa `app/`.

## Thư viện (watchlist) lưu ở đâu

`lib/data/watchlist_store.dart` — mặc định `PrefsWatchlistStore` (SharedPreferences),
không cần đăng nhập, bền qua lần mở app, chạy cả web/desktop. Muốn đổi sang Drift
(SQLite) hoặc đồng bộ Supabase: viết một class khác implement `WatchlistStore` rồi
override `watchlistStoreProvider` — không phải sửa UI.
