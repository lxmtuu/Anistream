# 👉 BẮT ĐẦU TỪ ĐÂY — AniStream v0.1.2

Bạn vừa tải về gói dự án **AniStream** — app xem anime hợp pháp miễn phí (Flutter mobile + desktop).
Tài liệu này chỉ để trả lời 1 câu: **làm gì tiếp theo?**

---

## Có 3 cách "thử", chọn theo thời gian bạn có

### ⚡ Cách 1 — 0 phút, không cần cài gì: xem UI trước
Mở file **`UI_PREVIEW.html`** bằng trình duyệt (nhấp đúp).
→ Thấy 3 màn hình chính với **poster thật** từ AniList (ảnh đã nhúng, không cần mạng).

Dùng để: hình dung sản phẩm, góp ý layout trước khi bỏ thời gian cài Flutter.

---

### 🚀 Cách 2 — 10 phút: chạy app Flutter thật (khuyên làm)

Cần: **Flutter ≥ 3.22** ([hướng dẫn cài](https://docs.flutter.dev/get-started/install)) + Chrome hoặc thiết bị Android.

**Tự động (khuyên dùng):**
```bash
# macOS / Linux
bash scripts/setup_app.sh
```
```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\setup_app.ps1
```

**Hoặc làm tay:**
```bash
cd app
flutter pub get
flutter run -d chrome        # nhanh nhất; hoặc -d windows / -d <mã điện thoại>
```

**Đừng chạy `flutter create`.** Gói này đã có sẵn `android/ ios/ web/ windows/ macos/
linux/` với cấu hình chỉnh tay (quyền INTERNET, POST_NOTIFICATIONS, applicationId…).
`flutter create .` sẽ **ghi đè** chúng và làm bản release mất mạng. (Lệnh này chỉ cần
khi repo chưa có thư mục platform — `scripts/setup_app.sh` đã tự xử lý trường hợp đó.)

**Xong khi:** Home có poster thật, bấm ▶ phát được video YouTube, tab Lịch phát có danh sách.

⚠️ **Nếu lỗi:** gửi mình 20 dòng cuối của log + `flutter doctor -v`. Đừng sửa lung tung — phần lớn lỗi là 1–3 dòng.

---

### 🗄️ Cách 3 — 2–3 giờ: chạy cả backend thật (Supabase)

```bash
# 1) Tạo project Supabase (free) → SQL Editor → dán toàn bộ db/schema.sql → Run

# 2) Ingest dữ liệu
cp .env.example .env          # điền SUPABASE_URL + SUPABASE_SERVICE_KEY (service_role)
pip install -r ingest/requirements.txt
python3 -m ingest.main all    # ~2 phút

# 3) Deploy API
npm i -g supabase
supabase login && supabase link --project-ref <ref>
supabase functions deploy home search schedule anime
bash scripts/test_api.sh https://<ref>.supabase.co/functions/v1

# 4) App dùng backend thật
cd app
flutter run --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://<ref>.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=<anon key>
```

Chi tiết: `supabase/README.md` và `ingest/README.md`.

---

## Trong gói có gì

| File / thư mục | Nội dung |
|---|---|
| **`VIEC_CAN_LAM.md`** | ⭐ **Đọc trước** — 4 việc cần làm, đúng thứ tự, có thời gian ước lượng |
| `UI_PREVIEW.html` | Xem UI ngay trong trình duyệt (poster thật, offline) |
| `DECISION.md` | Chốt mô hình 🅒→🅓, phạm vi đóng băng 10 tuần, điều kiện xem lại |
| `README.md` | Bản đồ toàn dự án + trạng thái từng hạng mục |
| `LO_TRINH_ANIME_APP.md` | Lộ trình 14 sprint, kiến trúc, chi phí thật, 8 sai lầm cần tránh |
| `CHON_MO_HINH.md` + `chon_mo_hinh.html` | 5 mô hình + bảng chọn tương tác (tự cân lại trọng số) |
| `anime_sources.md` | 10 nguồn API anime + cách cập nhật tập mới |
| `VI_SAO_CHI_XEM_DUOC_MOT_SO.md` | Vì sao chỉ xem được một số bộ/tập + cách tăng lên hàng nghìn |
| `db/schema.sql` | Postgres schema đầy đủ: 12 bảng, RLS, view, index (chạy 1 lần) |
| `app/` | Flutter app: 20 file Dart, chạy được bằng mock data thật; watchlist lưu bền trên máy |
| `supabase/` | 5 Edge Function: `home` `search` `schedule` `anime` `push` |
| `ingest/` | Worker Python: AniList + RSS YouTube official → Supabase |
| `tools/` | `gen_mock.py` (sinh dữ liệu thật) · `gen_preview.py` (sinh UI preview) |
| `scripts/` | `setup_app.sh/.ps1` (cài đặt) · `test_api.sh` (smoke test API) |
| `BAO_CAO_RA_SOAT.md` | Kết quả rà soát toàn repo 01/11/2026 + danh sách lỗi đã sửa |

## Dữ liệu lấy từ đâu (và vì sao hợp pháp)

```
AniList / Kitsu / TMDB     → metadata: tên, poster, điểm, lịch phát   (không host video)
YouTube RSS kênh official  → video official, đã lọc "cho nhúng" (oEmbed 200)
                             → app nhúng bằng IFrame Player API chính thức
Netflix/Crunchyroll/Bilibili → deep link "xem ở nơi phát hợp pháp"
```

**AniStream không lưu trữ / không trích xuất / không phát lại video của bên thứ ba.**
Đó là điều kiện để app sống được trên App Store & Google Play (và để bạn không vướng
NĐ 131/2013 hay Điều 225 BLHS). Chi tiết: `DECISION.md` §2.

## Lỗi thường gặp khi chạy

| Lỗi | Cách sửa |
|---|---|
| `Target of URI doesn't exist` | Thiếu thư mục platform → chạy `scripts/setup_app.sh` (chỉ sinh phần thiếu) |
| `version solving failed` | `flutter pub upgrade --major-versions && flutter pub get` |
| Player "Video unavailable" | Chủ kênh tắt nhúng sau khi ingest → `python3 -m ingest.main youtube` |
| Ảnh không tải | Cần mạng lần đầu (`cached_network_image`) |
| Muốn tắt push/Firebase | App chạy bình thường nếu chưa `flutterfire configure` (đã bọc try/catch) |

## Bước quan trọng nhất mà đừng bỏ qua

Sau khi app chạy được: **kiểm tra 5 video Muse Việt Nam có phụ đề tiếng Việt không**.
Nếu chỉ có English sub → nguồn video phải đổi (chi tiết trong `VIEC_CAN_LAM.md` việc 3).
