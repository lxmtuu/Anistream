# Bạn làm gì tiếp theo — 6 bước, ~25 phút

> **Đã xong rồi (mình làm sẵn, không cần bạn chạm vào):**
> database + RLS + trigger, **5 Edge Function** đã deploy và đã test thật trên
> project `snpzrblwiamqtrnifdis` (bằng chứng ở `supabase/README.md` §0).
> DB đang **trống có chủ ý** — chờ bước 3 nạp dữ liệu thật.
>
> Còn lại chỉ là những việc **bắt buộc phải chạy trên máy bạn**: sandbox của mình
> bị chặn `graphql.anilist.co` và `youtube.com`, nên mình không nạp dữ liệu hộ được.

| Bước | Việc | Thời gian | Bắt buộc? |
|---|---|---|---|
| 1 | Tạo `.env` trên máy bạn | 3' | ✅ |
| 2 | `bash scripts/preflight.sh` | 1' | ✅ |
| 3 | Nạp dữ liệu thật (`ingest`) | 5' | ✅ |
| 4 | Kiểm chứng bằng số | 2' | ✅ |
| 5 | Chạy app với dữ liệu thật | 10' | ✅ |
| 5b | Tiếng Việt + danh sách tập (TMDB) | 5' | ⚙️ nên làm |
| 6 | Bật thông báo đẩy + tự động hoá | 20' | ⚙️ tuỳ chọn |

---

## Bước 1 — Lấy code mới + tạo `.env` (3 phút)

```bash
git pull                     # nhánh arena/81e58d49-anistream
```

`.env` **không có trong git** (đúng luật: không commit key), nên bạn tạo 1 lần:

```bash
cp .env.example .env
```

Mở `.env` và điền **2 dòng bắt buộc**:

```ini
SUPABASE_URL=https://snpzrblwiamqtrnifdis.supabase.co
SUPABASE_SERVICE_KEY=<dán service_role key>
```

Lấy key ở đâu: **Supabase Dashboard → project `anistream` → Project Settings → API
Keys → mục `service_role` → Reveal → Copy**.
⚠️ Phải là `service_role` (**không phải** `anon`). Dán nhầm `anon` thì mọi lệnh ghi
sẽ bị RLS chặn — preflight ở bước 2 sẽ bắt lỗi này trước khi bạn mất 5 phút chạy ingest.

Hai dòng còn lại để trống vẫn chạy được:
- `TMDB_API_KEY` — **cứ để trống**: ingest hiện CHƯA dùng biến này (chưa có bước dịch
  nào trong code), đặt key cũng không ra `title_vi`/`synopsis_vi`. Tóm tắt phim lấy
  từ AniList (`anime.synopsis_original`), không cần key nào.
- `YOUTUBE_API_KEY` — có thì lấy được **toàn bộ** video cũ của kênh official
  (deep backfill), không có thì chỉ ~15 video mới nhất/kênh.

---

## Bước 2 — Kiểm tra trước khi chạy (1 phút)

```bash
pip install -r ingest/requirements.txt     # chỉ "requests", rất nhẹ
bash scripts/preflight.sh
```

**Kỳ vọng:** toàn ✅, kết thúc bằng `Sẵn sàng. Chạy ingest thật:`

```
  ✅ python3 3.12
  ✅ đã cài package requests
  ✅ đọc .env
  ✅ SUPABASE_URL hợp lệ (https://snpzrblwiamqtrnifdis.supabase.co)
  ✅ key là service_role (đúng — chỉ dùng ở worker/cron)
  ✅ bảng anime tồn tại
  ✅ bảng episodes tồn tại
  ✅ bảng streaming_links tồn tại
  ✅ bảng ingest_runs tồn tại
  ✅ Edge Function /home đã deploy và trả 200
```

**Gặp ❌ thì sửa đúng như dòng gợi ý, đừng chạy tiếp.** Preflight sinh ra để bạn
không phải chờ 5 phút rồi mới chết ở bước ghi DB.

---

## Bước 3 — Nạp dữ liệu thật (5 phút)

```bash
python3 -m ingest.main all
```

Chạy 3 job nối tiếp: **A** lịch phát 26h tới · **B** catalog theo mùa · **C** video
official → `streaming_links`. Lần đầu ~2–5 phút (gọi AniList + YouTube nhiều lần).

**Kỳ vọng** (con số sẽ khác, miễn là > 0):

```
▶ Job A — lịch phát 26h tới
  · 180 tập từ AniList
  ✓ 120 anime · 180 episodes
▶ Job B — catalog mùa FALL 2026
  ✓ ...
▶ Job C — video official
  ✓ ... streaming_links
```

Muốn xem trước mà **không ghi gì vào DB**:

```bash
python3 -m ingest.main all --dry-run
```

---

## Bước 3b — Nạp lại để có mô tả phim (30 giây)

Bản vá 2026-11-01 thêm cột `anime.synopsis_original` (mô tả lấy từ AniList). Dữ liệu
cũ chưa có cột này → chạy lại một lần:

```bash
python3 -m ingest.main schedule
```

**Kỳ vọng:** job A chạy xong. Kiểm trong SQL Editor:

```sql
select count(*) from anime where synopsis_original is not null;   -- phải > 0
```

Trước bản vá, `synopsis` trong API **luôn rỗng** nên trang chi tiết trống phần giới thiệu.

## Bước 3c — (Tuỳ chọn nhưng nên làm) Tiếng Việt + danh sách tập

Hiện app hiện tên romaji/english (`Kusuriya no Hitorigoto`) vì **AniList không có
tiếng Việt**, và chỉ 5/104 bộ có link xem. Job D lấy từ TMDB: `title_vi`,
`synopsis_vi`, `episodes_total` và danh sách tập.

```bash
# 1. Lấy key miễn phí (1 phút): themoviedb.org → Settings → API → "API Key (v3)"
#    (KHÔNG dùng Read Access Token v4 — code gọi bằng api_key)
# 2. Thêm vào .env:
#    TMDB_API_KEY=xxxxxxxx
bash scripts/preflight.sh            # phải thấy: ✅ có TMDB_API_KEY
python3 -m ingest.main tmdb          # ~2-4 phút cho 60 bộ
```

**Kỳ vọng:**

```
▶ Job D — TMDB: tên + tóm tắt tiếng Việt, danh sách tập
  · 60 anime cần làm giàu
  [1/60] The Apothecary Diaries      tmdb=237162 0.91 ← title_vi=Dược Sư Tự Sự, episodes_total=24
      + 24 tập
  ✓ 42 anime được bổ sung · 310 tập
```

Kiểm trong SQL Editor:

```sql
select count(*) filter (where title_vi is not null) as co_ten_viet,
       count(*) filter (where synopsis_vi is not null) as co_tom_tat,
       count(*) filter (where episodes_total is not null) as co_so_tap
from anime;                                   -- cả 3 phải > 0

select count(distinct anime_id) from episodes; -- phải tăng so với trước
```

Job D **không ghi đè** dữ liệu đã có, **không** lấy số tập của phim nhiều mùa, và
bộ nào không ghép được tên/năm thì bỏ qua (in `không tìm được trên TMDB`) chứ
không đoán bừa. Chi tiết quy tắc: `ingest/README.md` § Job D.

> Muốn job D chạy tự động hằng ngày: thêm `TMDB_API_KEY` vào GitHub secrets
> (Settings → Secrets → Actions). Không có key thì job D tự bỏ qua kèm cảnh báo.

## Bước 4 — Kiểm chứng bằng số (2 phút)

**a) Kiểm API thật** (5 function đang để `verify_jwt=false` nên không cần key):

```bash
BASE=https://snpzrblwiamqtrnifdis.supabase.co/functions/v1

curl -s "$BASE/home" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(len(d['anime']),'anime ·',len(d['shelves']),'shelf ·',len(d['schedule']),'slot')"
curl -s "$BASE/search?q=frieren" | python3 -c "import json,sys; print('search total =', json.load(sys.stdin)['data']['total'])"
curl -s "$BASE/schedule?days=7"  | python3 -c "import json,sys; print('slot 7 ngày =', len(json.load(sys.stdin)['data']['slots']))"
```

Hoặc chạy cả bộ smoke test có sẵn:

```bash
bash scripts/test_api.sh $BASE
```

**b) Kiểm DB** — Dashboard → **SQL Editor** → dán:

```sql
select 'anime' t, count(*) from anime
union all select 'episodes', count(*) from episodes
union all select 'link video official', count(*) from streaming_links where is_verified
union all select 'free & hợp pháp', count(*) from streaming_links where kind='free_legal' and is_verified;
```

Cả 4 dòng phải > 0. Nếu `anime` = 0 nhưng ingest báo ✓ → xem `ingest_runs`:

```sql
select * from ingest_runs order by started_at desc limit 5;
```

---

## Bước 5 — Chạy app với dữ liệu thật (10 phút)

```bash
cd app
flutter pub get
flutter run -d chrome \
  --dart-define=USE_MOCK=false \
  --dart-define=API_BASE=https://snpzrblwiamqtrnifdis.supabase.co/functions/v1 \
  --dart-define=ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNucHpyYmx3aWFtcXRybmlmZGlzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTM1MjQyOTEsImV4cCI6MjEwOTEwMDI5MX0.TJIm0tDjXk82ZCIQbVgKk4EMq30vmdA-LmsaTWaIkZY
```

Anon key ở trên là **key công khai** (thiết kế để nhúng vào app, RLS mới là thứ bảo
vệ dữ liệu) — dán thẳng vào lệnh build cũng được, đừng dán `service_role`.

Muốn APK cho điện thoại: đổi `flutter run -d chrome` → `flutter build apk --release`
(giữ nguyên 3 dòng `--dart-define`).

**Kỳ vọng:** trang chủ có shelf *"Xem ngay — miễn phí, hợp pháp"*, *"Tập mới hôm nay"*,
*"Mùa FALL 2026"*, bấm 1 bộ → thấy tập + nút xem. Bấm vào tập có video YouTube official
thì player nhúng phát được (IFrame Player API, không host video).

---

## Bước 6 — Tuỳ chọn: thông báo đẩy + tự động hoá

### 6a. Reset mật khẩu Postgres (2 phút, nên làm)

Lúc tạo project mình truyền sai mật khẩu (chuỗi literal), nên:
**Dashboard → Project Settings → Database → Reset database password**.

App **không** dùng mật khẩu này (chỉ dùng API key) → không chặn gì, nhưng để vậy thì
sau này bạn không kết nối `psql`/GUI được.

### 6b. Để lịch tự cập nhật mỗi 30 phút (5 phút)

`.github/workflows/ingest.yml` đã có sẵn, chỉ thiếu secret. Repo → **Settings →
Secrets and variables → Actions → New repository secret**:

| Tên | Giá trị |
|---|---|
| `SUPABASE_URL` | `https://snpzrblwiamqtrnifdis.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service_role key (như trong `.env`) |
| `TMDB_API_KEY` | nếu có |

Sau đó **Actions → ingest → Run workflow** để chạy thử 1 lần (đừng đợi cron).

⚠️ **Đừng tin cron chỉ vì bảng Actions trông đã bật.** Ngày 01/11/2026 kiểm tra
thật: `event=schedule` có **0 run** dù cron 30 phút, workflow `state=active`.
Kiểm bằng lệnh có sẵn:

```bash
bash scripts/check_cron.sh          # exit 0 = cron chạy thật · exit 1 = cron chết
```

Nếu `exit 1` sau vài giờ: dùng cron ngoài (cron-job.org) gọi
`POST /repos/<owner>/<repo>/actions/workflows/ingest.yml/dispatches` với body
`{"ref":"main"}` — script in sẵn câu lệnh mẫu.

### 6c. Bật thông báo "tập mới vừa ra" (15 phút)

Cần Firebase (miễn phí). Chưa làm bước này thì `/push` **chỉ chạy `dry_run`** —
gọi thật sẽ báo lỗi rõ ràng chứ không im lặng.

1. **Firebase Console** → tạo project → ⚙️ *Project settings* → tab **Service accounts**
   → *Generate new private key* → tải `service-account.json`.
2. Set secret trong Supabase: **Dashboard → Edge Functions → Secrets** (hoặc CLI
   `supabase secrets set FCM_SERVICE_ACCOUNT="$(cat service-account.json)"`).
3. Sinh mật khẩu cron:
   ```bash
   openssl rand -hex 24        # Windows: python -c "import secrets;print(secrets.token_hex(24))"
   ```
   Set tiếp secret `PUSH_CRON_SECRET` = chuỗi vừa sinh.
4. Thêm 3 GitHub secret nữa: `SUPABASE_ANON_KEY`, `PUSH_CRON_SECRET` (đã có
   `SUPABASE_URL` ở 6b).
5. `.github/workflows/push.yml` đã viết sẵn nhưng **cron đang comment** — mở file,
   bỏ comment khối `schedule:` để bật `*/15 * * * *`. Muốn thử trước thì
   **Actions → push → Run workflow** với `dry_run = true` (chỉ in ra sẽ gửi gì).

Thứ tự đúng: `dry_run = true` → kiểm `messages_to_send` > 0 → đổi `dry_run = false`.

---

## Nếu có gì sai

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| preflight ❌ `key là ANON` | dán nhầm anon key vào `SUPABASE_SERVICE_KEY` |
| preflight ❌ `bảng anime KHÔNG có` | chưa chạy `db/schema.sql` (nhưng DB này đã có sẵn — chắc bạn đang trỏ URL khác) |
| ingest báo ✓ mà `/home` vẫn `anime: []` | ghi vào project khác (kiểm `SUPABASE_URL`), hoặc dữ liệu bị `is_published=false` |
| `/home` trả `{"code":"UNAUTHORIZED_NO_AUTH_HEADER"}` | bạn đang gọi project khác, hoặc ai đó bật lại `verify_jwt` |
| App trắng dữ liệu, không báo lỗi | thiếu `--dart-define=USE_MOCK=false` → app đang dùng mock |
| App 401 khi gọi API | dán nhầm/thiếu `ANON_KEY` |

Gửi mình **nguyên văn log** ở bước nào lỗi là mình sửa tiếp — đừng gửi "nó không chạy",
log mới chỉ ra được chỗ sai.
