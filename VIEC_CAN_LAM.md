# Nên làm gì bây giờ — kế hoạch 1 tuần

**Ngày:** 01/11/2026 · Bạn hỏi "tớ nên làm gì" → đây là câu trả lời thẳng, có thứ tự.

---

> **Cập nhật 01/11/2026 (sau rà soát):** đã sửa 6 lỗi thật trong repo — trong đó có
> bản release Android **thiếu quyền INTERNET** (APK release sẽ không có mạng) và
> watchlist **mất sạch mỗi lần tắt app**. Chi tiết: `BAO_CAO_RA_SOAT.md`.
> Các bước dưới đây vẫn đúng thứ tự, chỉ bỏ bước `flutter create`.

## Trả lời trong 1 câu

> **Đừng viết thêm code. Chạy thử app ngay tối nay, rồi nối backend thật trong tuần này.**
> Code đã đủ cho v1 — thứ đang thiếu là **bằng chứng nó chạy được** và **10 người dùng thật**.

---

## Vì sao (chẩn đoán thật)

Sau 5 lượt, dự án đã có 6 phần: quyết định, ingest, app Flutter, backend, push, tài liệu. Nhưng:

| Rủi ro | Mức độ | Cách xử lý |
|---|---|---|
| **Chưa ai chạy app lần nào** — có thể sai 5-10 lỗi nhỏ tích lại, sửa một lúc rất mệt | 🔴 cao | Việc 1 (tối nay) |
| **Chưa có DB thật** — mọi thứ mới chỉ test dry-run | 🔴 cao | Việc 2 |
| **Chưa kiểm chứng "nội dung có đủ hấp dẫn không"** — đây là rủi ro sản phẩm, không phải kỹ thuật | 🟡 | Việc 3 |
| Thiếu auth, Drift, desktop build, store | 🟢 thấp | Tuần 2–3, không phải bây giờ |

Nguyên tắc: **học nhanh nhất khi thấy nó chạy**, không phải khi đọc thêm code.

---

## ✅ Việc 1 — Tối nay, 60 phút: chạy app với mock data

Không cần Supabase, không cần mạng backend. Chỉ cần Flutter.

```bash
# 0. cài Flutter nếu chưa: https://docs.flutter.dev/get-started/install
flutter --version        # cần >= 3.22

# 1. vào thư mục app
cd app

# 2. cài package  (repo đã có sẵn android/ios/web/windows/macos/linux → KHÔNG
#    chạy flutter create nữa; nó sẽ ghi đè manifest đã chỉnh tay)
flutter pub get

# 3. chạy
flutter devices
flutter run -d chrome     # nhanh nhất để thấy UI (30 giây)
flutter run -d windows    # hoặc desktop
```

**Nếu lỗi → gửi mình:**
- 20 dòng cuối của log (`flutter run` in ra)
- Kết quả `flutter doctor -v`
- Ảnh chụp màn hình nếu UI hiện ra nhưng sai

**Xong khi:** thấy Home có poster thật, bấm ▶ phát được video YouTube, tab Lịch phát có danh sách.

> Nếu bạn không cài được Flutter (máy yếu/Windows cũ), nói mình biết — mình sẽ chuyển hướng: dựng bản web tĩnh để bạn thấy UI ngay, và mình chạy thử phần Dart bằng test thuần.

---

## ✅ Việc 2 — Cuối tuần, 2–3 giờ: nối backend thật

```bash
# 1. Tạo project Supabase (free) → SQL Editor → dán TOÀN BỘ db/schema.sql → Run

# 2. Cấu hình ingest
cp .env.example .env
#   điền SUPABASE_URL + SUPABASE_SERVICE_KEY (service_role, KHÔNG phải anon)

pip install -r ingest/requirements.txt
bash scripts/preflight.sh       # bắt sớm: nhầm anon key, chưa chạy schema.sql, URL sai
python3 -m ingest.main all      # ~2 phút: lịch phát + catalog + video official

# 3. Deploy API
npm i -g supabase
supabase login && supabase link --project-ref <ref>
supabase functions deploy home search schedule anime
bash scripts/test_api.sh https://<ref>.supabase.co/functions/v1

# 4. Chạy app với backend thật
cd app
flutter run --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://<ref>.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=<anon key>
```

**Xong khi:** `data.anime` trong `/home` khác rỗng và app hiện dữ liệu giống bản mock.

---

## ✅ Việc 3 — 30 phút: kiểm chứng "catalog có đủ không" (rủi ro sản phẩm lớn nhất)

Mình vừa đo thật hôm nay:

| Kênh | Video/ngày | Qua lọc trailer/shorts | **Tập phim đầy đủ/ngày** |
|---|---|---|---|
| Muse Việt Nam | ~8.7 (~3.200/năm) | 87% | **~5.8 (~2.100/năm)** |
| Ani-One Asia | ~7.4 (~2.700/năm) | 53% | **~3.9 (~1.400/năm)** |
| **Cộng** | ~16 | — | **~9.7 tập/ngày** |

→ **Chỉ 2 kênh đã cho ~10 tập official miễn phí mỗi ngày, cộng dồn ~3.500 tập/năm.** Catalog không phải vấn đề. Tin tốt.

### ⚠️ Nhưng có 1 rủi ro mình phát hiện và bạn PHẢI kiểm tra: **phụ đề tiếng Việt**

Tiêu đề video của Muse Việt Nam ghi `[English Sub]` — nghĩa là có thể **không có vietsub**.
Với người dùng Việt, đây là yếu tố sống còn (**quan trọng hơn cả UI đẹp**).

**Việc của bạn (15 phút):** mở 5 video của Muse Việt Nam trên YouTube → xem có phụ đề tiếng Việt không.

| Kết quả | Hành động |
|---|---|
| Có vietsub | ✅ Tuyệt, giữ nguyên kế hoạch |
| Chỉ có English sub | 🔴 Phải tìm kênh có vietsub (Muse VN có playlist riêng, Bilibili VN, FPT Play, hoặc kênh publisher VN) → thêm `channel_id` vào `ingest/youtube.py` |
| Không có phụ đề | 🟡 Chấp nhận: định vị app là "lịch + nơi xem", video chỉ là bonus; hoặc chờ v2 (self-host) |

Đây là loại việc mà **5 phút kiểm tra tiết kiệm 5 tuần code sai hướng**.

---

## ✅ Việc 4 — Tuần sau: 10 người dùng thật (không viết thêm feature)

1. Build APK: `flutter build apk --release` → gửi cho 10 bạn xem anime
2. Cho họ dùng 3 ngày, hỏi đúng 3 câu:
   - *"Bạn có mở lại app ngày mai không? Vì sao?"*
   - *"Bạn xem tập mới ở đâu? App có giúp gì không?"*
   - *"Cái gì khó chịu nhất?"*
3. Đừng hỏi "app có đẹp không" — vô nghĩa.

**Đây là bước quyết định sống còn.** Nếu 10 người không mở lại lần 2 → vấn đề nằm ở sản phẩm (không phải code), sửa code bao nhiêu cũng vô ích.

---

## ❌ Những gì KHÔNG nên làm lúc này

| Đừng | Vì sao |
|---|---|
| Viết thêm feature (auth, review, comment, recommend) | Chưa có 1 người dùng thật nào |
| Làm desktop build / submit store | Cần 2–3 ngày, và Apple $99 — chờ tới khi có 10 người dùng hài lòng |
| Tối ưu animation, theme, icon | Vô nghĩa khi chưa biết người dùng có quay lại |
| Đọc thêm tài liệu kiến trúc | Bạn đã có 4 tài liệu; giờ cần *chạy*, không phải *đọc* |
| Nghĩ tới "kiếm tiền" | Chưa có retention thì không có doanh thu |

---

## Tóm lại: 4 việc, đúng thứ tự

```
[ ] 1. Tối nay    — flutter run với mock data (60')     → gửi mình log
[ ] 2. Cuối tuần  — Supabase + ingest + deploy (2-3h)   → app chạy dữ liệu thật
[ ] 3. Trong tuần — kiểm tra phụ đề tiếng Việt (15')    → có thể đổi hướng nguồn video
[ ] 4. Tuần sau   — 10 người dùng thật (3 ngày)         → quyết định làm tiếp hay xoay
```

**Còn mình:** chờ log của bạn ở việc 1 để sửa lỗi. Không có log thì mình viết thêm code cũng chỉ tăng rủi ro tích lũy.
