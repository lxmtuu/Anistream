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
| 5c | Nhiều tập hơn mỗi bộ (YouTube API) | 5' | ⚙️ nên làm |
| 5d | Sửa danh sách tập trống (chạy lại job D) | 2' | 🔴 nên làm |
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

Job D **không ghi đè** dữ liệu đã có; bộ nào không ghép được tên/năm thì bỏ qua
(in `không tìm được trên TMDB`) chứ không đoán bừa. Chi tiết quy tắc:
`ingest/README.md` § Job D.

### Nếu danh sách tập vẫn trống (bản cũ) — chạy lại một lần

Bản đầu của job D có 2 lỗi khiến **hầu hết bộ không có danh sách tập**, dù
`tmdb_id` đã có:

- bỏ qua mọi phim **nhiều mùa** (Takagi-san có 3 mùa → 0 tập)
- bỏ qua mọi bộ AniList **đã biết tổng số tập** (điều kiện `episodes_total is null`)

Bản mới chọn đúng mùa TMDB (`pick_season`): mùa duy nhất → khớp **năm** → khớp
**số tập** → không chắc thì bỏ. Chạy lại:

```bash
python3 -m ingest.main tmdb --limit-tmdb 200
```

**Kỳ vọng mới** (log có thêm lý do chọn mùa):

```
  [1/104] Teasing Master Takagi-san     tmdb=75865 0.95 ← ...
      + 12 tập (mùa 1, khớp năm 2018)
```

Kiểm nhanh:

```sql
select count(distinct anime_id) from episodes;   -- 34 → ~80+
select a.title_romaji, count(e.number) from anime a
  left join episodes e on e.anime_id = a.id
  where a.slug = 'karakai-jouzu-no-takagi-san' group by 1;  -- phải là 12
```

> Muốn job D chạy tự động hằng ngày: thêm `TMDB_API_KEY` vào GitHub secrets
> (Settings → Secrets → Actions). Không có key thì job D tự bỏ qua kèm cảnh báo.

## Bước 3d — Nhiều tập hơn cho mỗi bộ (YouTube Data API, 5 phút)

Hiện 4/5 bộ "miễn phí" chỉ có **1 tập** (bộ kia có 6). Nguyên nhân: RSS chỉ trả
**15 video mới nhất** mỗi kênh. Có key thì backfill **toàn bộ lịch sử** kênh.

**Lấy key (miễn phí, 10.000 unit/ngày — index được ~150.000 video):**

1. https://console.cloud.google.com → góc trên **New Project** → đặt tên bất kỳ → **Create**
   (đợi ~10 giây cho project được tạo, kiểm tra tên project đã hiện ở thanh trên cùng)
2. Menu ☰ → **APIs & Services** → **Library**
3. Ô tìm kiếm gõ **YouTube Data API v3** → bấm vào → nút **Enable** (đợi ~1 phút)
4. Menu ☰ → **APIs & Services** → **Credentials**
   → **+ Create credentials** → **API key** → key hiện ra (`AIza…`) → **Copy**
5. Dán vào `.env`:

```bash
echo 'YOUTUBE_API_KEY=AIza...' >> .env      # hoặc sửa trực tiếp bằng editor
```

6. Kiểm key trước khi chạy (bắt đúng lỗi: key sai / chưa bật API / hết quota):

```bash
bash scripts/check_keys.sh          # phải thấy: ✅ YouTube key dùng được
```

7. Backfill **một lần**:

```bash
python3 -m ingest.main youtube --deep --limit 200
```

**Kỳ vọng:** log ghi `BACKFILL toàn bộ kênh (YouTube API)` thay vì `RSS`, và số link
tăng lên nhiều.

**Bản mới ghi DB ngay sau MỖI kênh** và lưu cache ghép tên vào
`.cache/match_cache.json` — nên:

- dừng giữa chừng (Ctrl+C, mất mạng) **không mất** link đã ghép của kênh trước
- chạy lại thì **bỏ qua** tên đã biết, chỉ ghép phần còn thiếu
- mỗi kênh in `✓ đã ghi N link … (kênh Muse Việt Nam)` / `· đã lưu cache N tên`
- nếu một kênh lỗi, cuối job **báo lỗi và thoát khác 0** (các kênh khác vẫn đã ghi)

Lần đầu chạy có thể mất **10–30 phút** (AniList giới hạn tốc độ). Xem tiến độ ở
dòng `… ghép tên 50/480`. Muốn chạy từng kênh:

```bash
python3 -m ingest.main youtube --deep --limit 200 --channel muse_vn
python3 -m ingest.main youtube --deep --limit 200 --channel ani_one_asia
```

Kiểm:

```sql
select count(distinct anime_id) from streaming_links where kind='free_legal' and is_verified;
select count(*) from streaming_links where kind='free_legal' and is_verified;
```

**Kiểm xem bộ nào bị gán sai tập** (công cụ mới, không cần key YouTube):

```bash
python3 -m ingest.audit                 # chỉ đọc, in báo cáo theo từng bộ
python3 -m ingest.audit --slug one-punch-man
```

Nó lấy lại **tiêu đề thật** của từng video qua oEmbed công khai, parse lại bằng
`parse_title` mới, rồi xếp mỗi link vào 4 nhóm:

| Nhóm | Nghĩa | `--fix` làm gì |
|---|---|---|
| `xoa` | tiêu đề không nhận dạng được / bản gộp **một phần** | xoá link |
| `gop_ca_bo` | là **bản gộp cả bộ** nhưng đang lưu thành tập N | sửa `episode_number = 0` |
| `sai_so_tap` | tiêu đề nói tập khác | sửa số tập |
| `vuot_tong` | tập > `episodes_total` của AniList → **nghi link thuộc bộ/mùa khác** | báo ra, chỉ xoá khi thêm `--prune-over-total` |

```bash
python3 -m ingest.audit --fix                      # lưu source_title + sửa/xoá
python3 -m ingest.audit --fix --prune-over-total   # xoá luôn link vượt tổng
```

`--fix` cũng lưu `source_title` cho toàn bộ link cũ, nên lần sau audit chạy nhanh
và không cần gọi mạng.

**Sau lần chạy ĐẦU TIÊN bằng bản mới — dọn link cũ bị gán sai tập** (vd video gộp
`Tập 01-24` từng bị lưu thành tập 1). Bản mới lưu `source_title` cho mọi link, nên
dòng **không có** `source_title` chính là dòng do bản cũ tạo ra:

```sql
-- chạy SAU khi đã ingest lại cả 2 kênh thành công
delete from streaming_links where kind = 'free_legal' and source_title is null;
```

Rồi kiểm:

```sql
select count(*) filter (where source_title is null) as con_cu,
       count(*) filter (where episode_number = 0) as ban_gop_ca_bo
from streaming_links where kind = 'free_legal';       -- con_cu phải = 0
```

**3 lỗi hay gặp** (script `check_keys.sh` phân biệt được từng cái):

| Triệu chứng | Nguyên nhân | Sửa |
|---|---|---|
| `keyInvalid` | copy thiếu/thừa ký tự | copy lại ở Credentials |
| `accessNotConfigured` | **quên bấm Enable** ở bước 3 | Library → YouTube Data API v3 → Enable, đợi 1 phút (key cũ vẫn dùng) |
| `quotaExceeded` | hết 10.000 unit hôm nay | chờ reset 00:00 giờ Thái Bình Dương |
| `ipRefererBlocked` | key bị giới hạn IP | Credentials → key → Application restrictions → **None** |

**Lỗi/phàn nàn hay gặp khi backfill:**

| Triệu chứng | Nghĩa | Sửa |
|---|---|---|
| `… AniList rate limit, đợi 38s` lặp nhiều | AniList đang bóp tốc độ | bình thường, cứ để chạy; muốn chậm hơn: `ANILIST_MIN_INTERVAL=3` |
| `khớp được 0/5560 video` | tên series (thường tiếng Trung) chưa có alias | thêm vào `ingest/aliases.json` rồi chạy lại (nhanh, nhờ cache) |
| Chạy lại thấy nhanh bất thường | đang dùng cache | muốn ghép lại từ đầu: `--no-cache` |
| `2/2 kênh không lấy được video` | mạng/key/quota | đọc dòng lỗi phía trên; `bash scripts/check_keys.sh` |

> Không bắt buộc phải có key: bỏ `--deep` thì chỉ dùng RSS như cũ.

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
