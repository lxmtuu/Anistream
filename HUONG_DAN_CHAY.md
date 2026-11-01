# Hướng dẫn setup & chạy — AniStream

> ⚠️ **Cập nhật 01/11/2026:** repo hiện **đã có sẵn** `android/ ios/ web/ windows/
> macos/ linux/`. Bỏ qua mọi bước `flutter create` trong tài liệu này — chỉ cần
> `cd app && flutter pub get && flutter run`. `flutter create .` sẽ ghi đè cấu hình
> platform (quyền INTERNET, applicationId…) và làm bản release mất mạng.


**Mục tiêu:** từ file zip → thấy app chạy trên máy bạn. Thời gian thực tế **15–25 phút** (lần đầu).

```
Bước 0  Cài Flutter                    ~10 phút (tải nặng nhất)
Bước 1  Giải nén dự án                 ~1 phút
Bước 2  Chạy script setup              ~2 phút (một lệnh)
Bước 3  flutter run -d chrome          ~3 phút (lần đầu tải package)
```

---

## Cần gì trước

| | Yêu cầu |
|---|---|
| ✅ Bắt buộc | **Flutter ≥ 3.22** + **Git** (Flutter cần git) |
| ✅ Bắt buộc | Internet (lần đầu tải package ~200 MB) |
| 👍 Nên có | **Chrome** hoặc **Edge** — chạy web là cách nhanh nhất, không cần máy ảo |
| ⚙️ Tuỳ chọn | **Visual Studio 2022 + "Desktop development with C++"** → chỉ cần nếu muốn chạy bản Windows desktop |
| 📱 Tuỳ chọn | Điện thoại Android + cáp USB + bật USB debugging → chạy trên máy thật |

---

## Bước 0 — Cài Flutter

### 🪟 Windows (phổ biến nhất)

1. **Cài Git** (nếu chưa): https://git-scm.com/download/win → cứ Next hết.
2. **Tải Flutter**: https://docs.flutter.dev/release/archive → chọn **`flutter_windows_x.x.x-stable.zip`**
3. **Giải nén vào `C:\src\flutter`**
   ⚠️ **Đừng** giải nén vào `C:\Program Files` (bị chặn quyền ghi).
   ⚠️ Đường dẫn **không dấu, không khoảng trắng**.
4. **Thêm vào PATH**: mở Start → gõ *"environment variables"* → **Edit the system environment variables** → **Environment Variables…** → mục **User variables** chọn **Path** → **Edit** → **New** → dán:
   ```
   C:\src\flutter\bin
   ```
   → OK hết.
5. **MỞ LẠI terminal** (bắt buộc — terminal cũ không nhận PATH mới), rồi kiểm tra:
   ```powershell
   flutter --version
   flutter doctor
   ```

### 🍎 macOS
```bash
brew install --cask flutter
# hoặc tải zip ở trang trên rồi thêm .../flutter/bin vào PATH
flutter --version && flutter doctor
```

### 🐧 Linux
```bash
sudo snap install flutter --classic
flutter --version && flutter doctor
```

### ✅ Bước 0 xong khi
`flutter --version` in ra `Flutter 3.x.x • channel stable`.

`flutter doctor` có dấu ❌ màu vàng/đỏ cũng **không sao** — cứ đọc phần "không có" đó ở bảng lỗi bên dưới. Ví dụ báo thiếu Android toolchain vẫn chạy web được.

---

## Bước 1 — Giải nén dự án

Giải nén `anistream-v0.1.zip` ra một đường dẫn **ngắn, không dấu**:

```
C:\dev\anistream-v0.1        ← Windows, tốt
D:\code\anistream-v0.1       ← cũng tốt
C:\Users\Tùng Lâm\Tài liệu\… ← ❌ có dấu + khoảng trắng, dễ lỗi build Android
```

Kiểm tra: trong thư mục phải thấy `BAT_DAU_TU_DAY.md`, `app\`, `db\`, `ingest\`…

---

## Bước 2 — Chạy script setup (một lệnh)

Script làm 1 việc duy nhất: sinh các thư mục `android\`, `windows\`… mà **không ghi đè code của bạn**.

### 🪟 Windows
```powershell
cd C:\dev\anistream-v0.1
powershell -ExecutionPolicy Bypass -File scripts\setup_app.ps1
```

### 🍎🐧 macOS / Linux
```bash
cd ~/dev/anistream-v0.1
bash scripts/setup_app.sh
```

### Nếu script lỗi — làm tay
```bash
cd app
flutter pub get          # đủ rồi: thư mục platform đã có sẵn trong repo
flutter run -d chrome
```

Nếu vì lý do nào đó **mất** một thư mục platform, đừng `flutter create .` (ghi đè
cấu hình). Chạy lại `bash scripts/setup_app.sh`: nó chỉ sinh đúng thư mục còn thiếu.

> **Vì sao không chạy `flutter create .` ngay trong `app\`?** Vì lệnh đó có thể ghi đè `lib/main.dart` và `pubspec.yaml` — mất code. Script làm cách an toàn hơn: sinh ở thư mục tạm rồi chỉ copy phần platform.

### ✅ Bước 2 xong khi
Thấy `Got dependencies!` và trong `app\` xuất hiện `android\`, `windows\`, `.dart_tool\`.

---

## Bước 3 — Chạy

```powershell
cd C:\dev\anistream-v0.1\app

flutter devices          # xem có thiết bị gì

flutter run -d chrome    # ⭐ nhanh nhất — mở app trong Chrome
# flutter run -d edge    # nếu không có Chrome
# flutter run -d windows # desktop (cần Visual Studio C++ workload)
```

**Lần đầu chạy:** 1–5 phút (tải + biên dịch). Các lần sau: 5–15 giây.
**Dừng:** bấm `q` trong terminal, hoặc `Ctrl + C`.

### ✅ Bước 3 xong khi bạn thấy
- [ ] Trang chủ có **ảnh bìa lớn** + tiêu đề anime thật (Frieren, FAIRY TAIL, Takagi-san…)
- [ ] Cuộn xuống có **4 hàng poster**: "Xem ngay — miễn phí", "Tập mới hôm nay", "Mùa này", "Điểm cao nhất"
- [ ] Bấm **▶ Xem ngay** → mở **video YouTube** phát được
- [ ] Tab **Lịch phát** (thứ 2) → danh sách theo ngày, có giờ và đếm ngược
- [ ] Tab **Tìm** → gõ `frieren` → ra kết quả sau ~350ms
- [ ] Tab **Thư viện** → trống, có nút "Khám phá anime"

> App đang chạy bằng **dữ liệu thật** (52 anime, 12 bộ có video official) đã nhúng sẵn — **không cần backend**. Ảnh cần internet lần đầu, sau đó được cache.

---

## Bước 4 (tuỳ chọn) — Nối backend thật

Chỉ làm khi app đã chạy được bằng mock. Chi tiết đầy đủ: `supabase/README.md` + `ingest/README.md`.

```bash
# 1. Tạo project Supabase (free) → SQL Editor → dán toàn bộ db/schema.sql → Run
# 2. Điền .env (SUPABASE_URL + SUPABASE_SERVICE_KEY) rồi:
pip install -r ingest/requirements.txt
python3 -m ingest.main all

# 3. Deploy API
npm i -g supabase
supabase login && supabase link --project-ref <ref>
supabase functions deploy home search schedule anime

# 4. Chạy app với backend thật
cd app
flutter run -d chrome --dart-define=USE_MOCK=false ^
  --dart-define=API_BASE=https://<ref>.supabase.co/functions/v1 ^
  --dart-define=ANON_KEY=<anon key>
```

---

## Bảng lỗi thường gặp (Windows hay gặp nhất ở trên)

| Lỗi | Nguyên nhân & cách sửa |
|---|---|
| `'flutter' is not recognized…` | Chưa thêm PATH hoặc **chưa mở lại terminal**. Đóng hết terminal/VS Code → mở lại |
| `Target of URI doesn't exist: package:flutter_riverpod/…` | Chưa chạy Bước 2 hoặc chưa `flutter pub get` |
| `version solving failed` | `cd app` → `flutter pub upgrade --major-versions` → `flutter pub get` |
| `Building with plugins requires symlink support` | Windows: Settings → **For developers** → bật **Developer Mode** |
| `No supported devices connected` | `flutter devices`; hoặc dùng `-d chrome` / `-d edge` |
| `Unable to find suitable Visual Studio toolchain` | Cài **Visual Studio 2022** + workload **Desktop development with C++**, hoặc cứ dùng `-d chrome` |
| `Android license status unknown` | `flutter doctor --android-licenses` → gõ `y` hết |
| Gradle tải chậm / lỗi mạng | Bỏ qua Android, chạy `-d chrome` trước; Android build sau |
| App mở ra **màn hình trắng** | Xem log terminal; thử `flutter clean && flutter pub get && flutter run -d chrome` |
| Ảnh không hiện, chỉ có ô xám | Không có internet, hoặc mạng chặn `s4.anilist.co`. Video cũng cần mạng |
| `This application is not configured to build on the web` | Thiếu thư mục `web/` → chạy `bash scripts/setup_app.sh` (chỉ sinh phần thiếu, không đè) |
| `Can't have a late final field in a class with a const constructor` | Lỗi code đã sửa ở bản v0.1.1 — tải lại zip, hoặc xem mục "Sửa tay" bên dưới |
| Lỗi liên quan `firebase_*` | App đã bọc try/catch nên vẫn chạy. Nếu vẫn chặn build: tạm xoá 3 dòng `firebase_core/firebase_messaging/shared_preferences` trong `pubspec.yaml` (mất tính năng push, không ảnh hưởng phần khác) |

---

## Sửa tay 2 file (nếu không muốn tải lại zip)

**1. `app/lib/core/models/home_feed.dart`** — bỏ `const` ở constructor và đổi `late final` thành getter:

```dart
// TÌM (dòng ~11) và XOÁ chữ const:
const HomeFeed({        →      HomeFeed({

// TÌM dòng ~18 và THAY:
late final Map<int, Anime> byId = {for (final a in anime) a.id: a};

// THÀNH 2 dòng:
Map<int, Anime>? _byIdCache;
Map<int, Anime> get byId => _byIdCache ??= {for (final a in anime) a.id: a};
```

**2. Thêm web support** (nguyên nhân lỗi "not configured to build on the web"):
```powershell
bash scripts/setup_app.sh      # chỉ sinh thư mục web/ còn thiếu
```

**3. Bật Developer Mode** (cần cho plugin dùng symlink: firebase, shared_preferences):
```powershell
start ms-settings:developers
```

## Nếu vẫn không được — gửi mình đúng 3 thứ này

1. **20 dòng cuối** của log lỗi (copy từ terminal)
2. Kết quả `flutter doctor -v`
3. Bạn đang dùng **Windows / macOS / Linux** + chạy bằng `-d chrome` hay điện thoại

Có 3 thứ đó là mình chỉ đúng chỗ trong 1 lượt. Đừng sửa lung tung — phần lớn lỗi cài đặt là 1–2 dòng.
