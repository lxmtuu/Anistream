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
| 5 | Auth + watchlist persist (Drift + Supabase Auth) | ⏭ |
| 6 | Desktop build + submit store | ⏭ |

## Cấu trúc repo

```
.
├── DECISION.md               ⭐ chốt mô hình + phạm vi đóng băng 10 tuần
├── LO_TRINH_ANIME_APP.md     lộ trình 14 sprint, kiến trúc, chi phí
├── CHON_MO_HINH.md           5 mô hình + bảng chấm điểm
├── chon_mo_hinh.html         bảng chọn tương tác (mở để tự cân lại trọng số)
├── anime_sources.md          10 nguồn API anime + cách cập nhật
├── db/schema.sql             Postgres schema + RLS + view (chạy 1 lần)
├── ingest/                   worker: AniList + YouTube official → Supabase
├── supabase/                 Edge Functions: home · search · schedule · anime · push
├── app/                      Flutter app (lib/ 18 file, 4.484 dòng)
│   └── UI_PREVIEW.html       ⭐ xem trước 3 màn hình (poster thật, offline)
├── tools/                    gen_mock.py · gen_preview.py
└── scripts/test_api.sh       smoke test 4 endpoint
```

## Chạy từ đầu (theo thứ tự)

```bash
# 1. Database
#    → tạo project Supabase → SQL Editor → dán db/schema.sql

# 2. Ingest (cần SUPABASE_URL + SUPABASE_SERVICE_KEY trong .env)
cp .env.example .env
pip install -r ingest/requirements.txt
python3 -m ingest.main all          # hoặc thêm --dry-run để test không ghi DB

# 3. Backend
npm i -g supabase && supabase login && supabase link --project-ref <ref>
supabase functions deploy home search schedule anime
bash scripts/test_api.sh https://<ref>.supabase.co/functions/v1

# 4. App
cd app
cp pubspec.yaml /tmp/pub.yaml
flutter create --org com.anistream --project-name anistream \
  --platforms=android,ios,windows,macos,linux .
cp /tmp/pub.yaml pubspec.yaml
flutter pub get
flutter run                          # dùng mock data (không cần backend)
# hoặc nối backend thật:
flutter run --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://<ref>.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=<anon key>
```

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
| Lộ trình 14 tuần + chi phí + sai lầm cần tránh | `LO_TRINH_ANIME_APP.md` |
| Thêm nguồn dữ liệu anime | `anime_sources.md`, `ingest/README.md` |
| Hợp đồng API giữa app và backend | `supabase/README.md` §3 |
