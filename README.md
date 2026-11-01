# AniStream 🎬

> **Xem anime hợp pháp miễn phí. Và thư viện của riêng bạn.**
> App Flutter (Android · iOS · Windows · macOS · Linux) + Supabase + ingest worker.
> Hạ tầng **0đ** · catalog **20.000+ bộ** từ AniList/Kitsu/TMDB · lịch phát chính xác tới **giờ**.

---

## Trạng thái dự án

| # | Hạng mục | Trạng thái |
|---|---|---|
| 0 | Chọn mô hình (5 lựa chọn, chấm điểm có trọng số) | ✅ |
| 1 | Ingest worker (3 job, chạy thật: 16/16 video khớp) | ✅ |
| 2 | App Flutter v0.1 (4 tab + detail + player, mock data thật) | ✅ |
| 3 | Backend Edge Functions (4 endpoint, typecheck sạch) | ✅ |
| 4 | Push FCM "tập mới vừa ra" (backend + client + deep link) | ✅ |
| 5 | Watchlist persist trên máy (SharedPreferences) | ✅ |
| 5b | Auth + đồng bộ watchlist đa thiết bị (Supabase Auth) | ⏭ |
| 6 | Desktop build + submit store | ⏭ |
| 7 | CI `flutter analyze` + test cho app | ✅ |
| 8 | Bản web trên GitHub Pages (xem app không cần cài Flutter) | ✅ live |
| 9 | CI cho Edge Functions (`bash scripts/test_edge.sh`, 13 test) | ✅ |

> Rà soát toàn repo 01/11/2026: xem **`BAO_CAO_RA_SOAT.md`** (6 lỗi thật đã sửa,
> 5 lỗi TypeScript/Python đã kiểm tra sạch, phần còn tồn đọng + lý do).

## Cấu trúc repo

```
.
├── DECISION.md               ⭐ chốt mô hình + phạm vi đóng băng 10 tuần
├── LO_TRINH_ANIME_APP.md     lộ trình 14 sprint, kiến trúc, chi phí
├── CHON_MO_HINH.md           5 mô hình + bảng chấm điểm
├── chon_mo_hinh.html         bảng chọn tương tác (mở để tự cân lại trọng số)
├── anime_sources.md          10 nguồn API anime + cách cập nhật
├── db/schema.sql             Postgres schema + RLS + view + trigger auth (chạy 1 lần)
├── db/migrations/            bản vá idempotent cho DB đã tạo trước đó
├── CHECKLIST_QA.md           ⭐ 6 điểm kiểm tra APK release trên máy thật
├── ingest/                   worker: AniList + YouTube official → Supabase
│   └── audit.py              `python3 -m ingest.audit` — soi link gán sai số tập
├── supabase/                 Edge Functions: home · search · schedule · anime · push
├── app/                      Flutter app (lib/ 20 file) + platform folders đã sẵn
│   ├── UI_PREVIEW.html       ⭐ xem trước 3 màn hình (poster thật, offline)
│   └── test/                 unit test watchlist (flutter test)
├── tools/                    gen_mock.py · gen_preview.py
└── scripts/
    ├── preflight.sh          kiểm tra .env + schema + key (anon hay service_role) trước khi ingest
    ├── test_edge.sh          test logic push bằng Node (không cần Deno)
    ├── check_cron.sh         cron GitHub có THẬT SỰ chạy? (exit 1 = chết)
    ├── check_keys.sh         kiểm TMDB/YouTube key (nói rõ sai ở đâu)
    ├── test_api.sh           smoke test các endpoint
    └── setup_app.sh/.ps1     sinh thư mục platform còn thiếu
```

## Chạy từ đầu (theo thứ tự)

> 👉 **Nếu backend đã dựng xong và bạn chỉ cần nạp dữ liệu + chạy app:**
> đọc [`BAN_LAM_TIEP.md`](BAN_LAM_TIEP.md) — 6 bước, ~25 phút, có cả cách kiểm chứng.

```bash
# ✅ BƯỚC 1 + 3 ĐÃ LÀM SẴN trên project thật:
#    https://snpzrblwiamqtrnifdis.supabase.co  (Singapore, free)
#    · schema + RLS + view + trigger đã áp; DB đang TRỐNG (chờ ingest)
#    · 5 Edge Function đã deploy: home · search · schedule · anime · push
#    · .env ở gốc repo đã điền sẵn URL + service_role key (file bị gitignore)
#    Chi tiết + bằng chứng test: supabase/README.md §0

# 1+2. Ingest — chạy TỪ MÁY BẠN (sandbox chặn AniList/YouTube), cần mạng thật
pip install -r ingest/requirements.txt
bash scripts/preflight.sh           # ← kiểm tra key/schema trước, ~5 giây
python3 -m ingest.main all          # hoặc thêm --dry-run để test không ghi DB

# 3. Backend — chỉ chạy lại khi sửa code Edge Function
npm i -g supabase && supabase login && supabase link --project-ref snpzrblwiamqtrnifdis
supabase functions deploy home search schedule anime push
bash scripts/test_api.sh https://snpzrblwiamqtrnifdis.supabase.co/functions/v1

# 4. App  (repo ĐÃ có android/ios/web/windows/macos/linux → KHÔNG chạy flutter create)
cd app
flutter pub get
flutter run                          # dùng mock data (không cần backend)
# hoặc nối backend thật:
flutter run --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://<ref>.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=<anon key>
```

## Xem app mà không cần cài Flutter

Bản web của app (mock data — dữ liệu thật sinh từ AniList/YouTube, không cần Supabase)
được build tự động bằng `.github/workflows/pages.yml` và deploy lên GitHub Pages.

**Bật 1 lần** (~10 giây, chỉ chủ repo làm được):

1. **Settings → Pages → Build and deployment → Source: `GitHub Actions`**
   (repo đang để `Deploy from a branch` → workflow chỉ *build*, không deploy được)
2. **Actions → pages → Re-run all jobs**

Xong: mở `https://<user>.github.io/Anistream/` là thấy app chạy thật trên trình duyệt.
Trang xem trước tĩnh vẫn còn ở `/previews/` (UI preview, bảng chọn mô hình, báo cáo nguồn).

> Workflow tự kiểm tra chế độ Pages trước khi deploy: nếu còn `legacy` thì nó chỉ build
> (để chứng minh code web biên dịch được) và ghi nhắc vào job summary — không báo đỏ.

## Dữ liệu đến từ đâu (và vì sao hợp pháp)

```
AniList / Kitsu / TMDB     → metadata (tên, poster, điểm, lịch phát)   ⚠️ không host video
YouTube RSS kênh official  → video official, đã lọc "cho nhúng" (oEmbed 200)
                             → app nhúng bằng IFrame Player API chính thức
Netflix/Crunchyroll/...    → deep link "xem ở nơi phát hợp pháp"
```

**AniStream không lưu trữ, không trích xuất, không phát lại video của bên thứ ba.**
Đây không chỉ là nguyên tắc — đó là điều kiện để app sống được trên App Store/Google Play
và để bạn không vướng NĐ 131/2013 hay Điều 225 BLHS. Chi tiết: `DECISION.md` §2.

## Đọc gì trước

| Bạn muốn | Đọc |
|---|---|
| Hiểu vì sao chọn mô hình này | `DECISION.md` |
| Tự cân lại lựa chọn theo ưu tiên của mình | `chon_mo_hinh.html` |
| Xem UI trước khi build | `app/UI_PREVIEW.html` |
| Kiểm tra bản release đúng/sai trong 15 phút | `CHECKLIST_QA.md` |
| Lộ trình 14 tuần + chi phí + sai lầm cần tránh | `LO_TRINH_ANIME_APP.md` |
| Thêm nguồn dữ liệu anime | `anime_sources.md`, `ingest/README.md` |
| Hợp đồng API giữa app và backend | `supabase/README.md` §3 |
