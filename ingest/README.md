> Bắt đầu không cần Google Cloud: xem `HUONG_DAN_MUSE_MIEN_PHI.md` ở thư mục gốc.

# ingest — Worker dữ liệu cho AniStream

4 job, chạy bằng cron (GitHub Actions), **0đ**. Chỉ job D cần API key (TMDB, miễn phí).

| Job | Nguồn | Tần suất | Ghi vào |
|---|---|---|---|
| `schedule` | AniList `airingSchedules` | 30 phút | `anime`, `episodes` |
| `catalog` | AniList `seasonal` | 1 lần/đêm | `anime` |
| `youtube` | RSS kênh official + oEmbed sơ bộ | 6 giờ | `anime`, `streaming_links` (kind=`free_legal`) |
| `tmdb` | TMDB `search/tv` + `translations` + `season` | 1 lần/ngày | `anime` (title_vi, synopsis_vi, episodes_total), `episodes` |

## Cài & chạy

```bash
pip install -r ingest/requirements.txt
cp .env.example .env          # điền SUPABASE_URL + SUPABASE_SERVICE_KEY

# TEST không cần Supabase (không ghi gì):
python3 -m ingest.main youtube --dry-run --limit 12
python3 -m ingest.main schedule --dry-run

# CHẠY THẬT:
python3 -m ingest.main schedule
python3 -m ingest.main catalog --pages 2
python3 -m ingest.main youtube --limit 25
python3 -m ingest.main tmdb                # cần TMDB_API_KEY (miễn phí)
python3 -m ingest.main all
```

Cờ: `--dry-run` (không ghi DB) · `--no-embed-check` (bỏ kiểm tra oEmbed, nhanh hơn) ·
`--hours N` (cửa sổ lịch phát) · `--pages N` (số trang catalog) · `--limit N` (video/kênh)

## Job D — tiếng Việt + danh sách tập (TMDB)

AniList không có tiếng Việt, và trước bản vá này chỉ 22/104 anime có `episodes`:
app hiện `Kusuriya no Hitorigoto` thay vì *Dược Sư Tự Sự*, và mở 79 bộ khác thì
trang chi tiết trống. Job D lấp 2 chỗ đó.

```
/search/tv (english → romaji → native, kèm năm)  →  /tv/{id}?append_to_response=alternative_titles,translations
                                                 →  /tv/{id}/season/1  (chỉ khi đúng 1 mùa)
```

Quy tắc **thà thiếu còn hơn sai**:

| Tình huống | Hành vi |
|---|---|
| Không ghép được tên/năm | Bỏ qua, in `không tìm được trên TMDB` — **không đoán bừa** |
| `title_vi`/`synopsis_vi` đã có | **Không ghi đè** (dữ liệu biên tập tay được giữ) |
| Phim nhiều mùa | **Chọn đúng mùa** rồi mới lấy tập: (1) TMDB chỉ có 1 mùa → mùa đó; (2) đúng 1 mùa có NĂM = năm AniList → mùa đó (Takagi-san 2018 → S1, không phải S3); (3) đúng 1 mùa có SỐ TẬP = số tập AniList; (4) còn lại → **bỏ**, không lấy tập |
| TMDB trả nhiều tập hơn AniList | Không ghi (`episodes_plausible`, dư ≤ 2 tập thì bỏ qua) — vd Fool Night: AniList 3, TMDB 12 |
| Bản dịch `vi` rỗng | Thử `alternative_titles` VN; trùng y tên gốc thì coi là chưa có |
| `TMDB_API_KEY` sai (401) | Nổ ngay `TmdbError`, không nuốt |
| Chạy `all` mà không có key | In cảnh báo rõ + ghi `ingest_runs(ok=false)`, các job khác vẫn chạy |

Lấy key (miễn phí, 1 phút): themoviedb.org → Settings → API → **API Key (v3)**.
⚠️ Không dùng "Read Access Token (v4)" — code gọi bằng `api_key`.

## 9 job ingest

| Job | Lệnh | Nguồn | Chạy |
|---|---|---|---|
| A | `schedule` | AniList lịch phát | 30 phút |
| B | `catalog` | AniList theo mùa | hằng đêm |
| C | `youtube` | Muse VN (YouTube) → `streaming_links` | 6 giờ |
| C' | `episodes` | **link official → `episodes`** | 6 giờ + hằng ngày |
| D | `tmdb` | TMDB: tiếng Việt + tập | hằng ngày |
| D' | `tmdb --refresh` | TMDB: **tập MỚI** của bộ đang chiếu | hằng ngày |
| E | `seasons` | AniList `relations` → **mùa thiếu** (SEQUEL + PREQUEL) | hằng ngày |
| F | `jikan` | Jikan/MAL → lấp tập còn thiếu (`--fill-gaps`: cả bộ thiếu vài tập) | hằng ngày |
| G | `check` | **kiểm bất biến dữ liệu**, vi phạm cứng → job ĐỎ | hằng ngày |

`all` = A + B + C + C' + D + D' + E + F + G.

### Vì sao cần D' và E (2 lỗi cũ)

- **D'** — chế độ bổ sung chỉ chọn bộ `or=(title_vi.is.null, …)` và chỉ lấy tập khi
  bảng **trống** → bộ đang chiếu đã có 5 tập thì KHÔNG BAO GIỜ nhận tập 6. `--refresh`
  quét mọi bộ `status=RELEASING` và `upsert` tập mới (in `+ K tập MỚI`).
- **E** — AniList tách mỗi mùa thành entry riêng, entry mùa 1 không có tập của mùa 2.
  Job E đi theo quan hệ `SEQUEL` để thêm mùa mới (`+ mùa mới: … ← bộ gốc`).
- **C'** — trước đây `episodes` CHỈ đến từ TMDB. Đo 01/11/2026: **23/27** bộ có
  `streaming_links` nhưng bảng tập TRỐNG (`dandadan` 12 link/0 tập, `noblesse`
  13/0) → trang chi tiết hiện "0 tập" dù có video. C' tạo tập từ chính link
  `episode_number > 0`, **không** tạo tập vượt `episodes_total` (phần vượt được in
  ra cảnh báo vì nghi link thuộc mùa khác), và không ghi đè tập đã có từ TMDB/Jikan.
- **E** (chiều ngược) — Muse đăng mùa mới TRƯỚC, nên DB có "Ao no Hako Season 2"
  mà thiếu hẳn mùa 1 (đo 01/11: 9/10 bộ có tên mùa đều thiếu mùa gốc). Bộ nào tên
  có `Season N`/`Nnd Season`/`Mùa N`/`Part N` sẽ được đi thêm quan hệ `PREQUEL`.
- **F** — AniList chỉ có tổng số tập, TMDB hay thiếu bản dịch. Jikan miễn phí, không
  cần key, tra theo `mal_id` (bảng `anime` đã lưu từ `idMal`) → lấp `title` + `aired`.
  Bỏ tập `filler` và tập vượt `episodes_total`.

### Vì sao có Job G (và 3 lỗi "âm thầm" khác đã vá 02/11/2026)

Rà lại toàn pipeline thấy 4 chỗ hỏng mà **không chỗ nào báo lỗi**:

| Lỗi | Hậu quả thật trên DB | Bản vá |
|---|---|---|
| `to_anime_row` gửi khoá `None` khi AniList trả rỗng | upsert merge-duplicates ghi NULL đè `episodes_total`/`cover_url`/`score` mỗi 30 phút. Đo 02/11: **3 bộ có 12–13 tập đầy đủ (từ TMDB) mà `episodes_total` = NULL** — khớp với việc bị ghi đè; và **126/126 bộ `last_synced_at` = NULL** (chắc chắn, cột không có default) | Bỏ khoá rỗng khỏi payload + tự set `last_synced_at` |
| `to_episode_row` gửi `title: None` | job A xoá tên tập TMDB/Jikan đã điền | Bỏ khoá khi rỗng (cả ở `tmdb.episode_rows`, `jikan.episode_rows`) |
| Không phân trang khi đọc PostgREST | Supabase cắt ở **1000 dòng**; `limit=20000` vẫn chỉ 1000 → job C' coi bộ sau dòng 1000 là "chưa có tập", job E báo nhầm "mùa mới" | `DB.select_all()` tự limit+offset, dùng ở C'/E/audit |
| `jikan` bỏ qua mọi bộ đã có ≥1 tập | 33 bộ thiếu vài tập không bao giờ được lấp | cờ `--fill-gaps` (chỉ thêm số tập còn thiếu) |

Job G kiểm: tập vượt tổng, tập đánh số ≤ 0, slug trùng, một URL gắn 2 bộ, dòng mồ
côi (cứng) và link vượt tổng / bộ có link mà 0 tập / bộ không rõ tổng (mềm).

### Edge Function: 3 chỗ cắt dữ liệu ở 1000 dòng (vá 02/11/2026)

PostgREST của Supabase có "Max Rows" = **1000**: `.limit(1200)` vẫn chỉ trả 1000
dòng. Ba API đang dựa vào limit cứng nên khi dữ liệu lớn lên sẽ **thiếu tập một
cách âm thầm** (bộ nằm sau dòng 1000 hiện "0 tập"):

| API | Trước | Sau |
|---|---|---|
| `/home` | `episodes` `.limit(1200)`, `links` `.limit(1200)`, `free_legal` `.limit(300)` | `selectAll()` đọc hết trang; shelf "Xem ngay" không còn mất bộ (DB đã có **485** link free) |
| `/anime` | `episodes`/`links` `.limit(600)` | `selectAll()` theo `order` ổn định |
| `/search` | `episodes`/`links` `.limit(600)` cho tới 48 bộ | `selectAll()` |

Kèm 2 lỗi nữa cùng đợt:
- **Chọn video theo region**: một tập có cả bản VN và bản Asia thì ai "thắng" là
  ngẫu nhiên (thứ tự PostgREST không đảm bảo) → nay ưu tiên `VN`, rồi `AS`.
- **`push` nhả reservation sai**: xoá bằng 2 lần `.in()` = AND → xoá tích chéo
  `(A,3)`, `(B,5)` của những tập CHƯA gửi ⇒ cron sau gửi trùng. Nay xoá từng cặp.
- **Số tập trên app** đếm cả entry 0 ("bản gộp cả bộ") → bộ 12 tập hiện
  "Tập phim (13)". Nay đếm bằng `realEpisodeCount()`.

⚠️ Sau khi `git pull`, phải deploy lại edge function thì thay đổi mới có hiệu lực:

```bash
supabase functions deploy home search schedule anime push
```

### PGRST102 "All object keys must match" (lỗi thật 02/11/2026)

Job E chạy 6 phút, in ra ~50 mùa mới, rồi **chết ở bước ghi**:

```
RuntimeError: upsert anime lỗi 400: {"code":"PGRST102", "message":"All object keys must match"}
```

Nguyên nhân: PostgREST bắt **mọi object trong một mảng JSON phải có CÙNG bộ khoá**.
Ta cố ý bỏ khoá rỗng khỏi payload (để `merge-duplicates` không ghi NULL đè
`episodes_total`/`cover_url`/`title`), nên trong 1 lô có row 17 khoá lẫn row 15
khoá → cả request bị từ chối. Job A (`episodes`) cũng dính y hệt (tập có
`airing_at` vs tập không).

Hai bản vá:
1. `db._group_by_keys()` — chia lô thành các nhóm **đồng nhất bộ khoá**, gửi
   nhiều request. KHÔNG san phẳng bằng cách điền `None` (làm vậy là quay lại đúng
   lỗi ghi NULL đè).
2. `job_seasons` ghi **theo lô 25** thay vì gom hết rồi ghi một lần → lỗi giữa
   đường chỉ mất phần còn lại, không mất trắng 6 phút công.

### Job F hỏng mạng: phải ĐỎ, và phải dừng sớm

Đo 02/11/2026 trên máy Windows của chủ dự án: **39/39** bộ Jikan `ConnectTimeout`,
job in 39 dòng lỗi rồi **exit 0** (mất 856 giây). Hai bản vá:

1. **Nổ khi không lấp được bộ nào** (`filled == 0 and errors > 0`) → exit ≠ 0.
2. **Cầu dao**: 5 bộ liên tiếp không kết nối được → dừng ngay, không chờ hết.
3. `ingest/net.py`: khi request ĐẦU TIÊN lỗi kết nối, **ép IPv4** rồi thử lại —
   nguyên nhân phổ biến nhất của ConnectTimeout hàng loạt trên Windows là máy ưu
   tiên IPv6 nhưng đường ra IPv6 không thông.

Chẩn đoán tay (Git Bash):

```bash
curl -4 -sS -m 20 -o /dev/null -w '%{http_code}\n' https://api.jikan.moe/v4/anime/30276/episodes
```

`200` → mạng ổn. `000` → ISP/proxy chặn: đặt `HTTPS_PROXY=http://host:port` trong `.env`.

### Cron: GitHub không đủ tin cậy

Đo thật ngày 01/11/2026: workflow "active" nhưng `event=schedule` = **0 run/10h**.
Hai cách thay thế (đều kèm trong repo):

```bash
bash scripts/trigger_ingest.sh lxmtuu/Anistream all   # cần GH_TOKEN (Actions: write)
```

- **cron-job.org** — POST tới `…/dispatches` (xem bảng trong `BAN_LAM_TIEP.md` §6b)
- **pg_cron trong Supabase** — chạy `supabase/CRON.sql` (không cần dịch vụ ngoài)

## Job C hoạt động thế nào (và vì sao hợp pháp)

```
RSS kênh official  →  parse tiêu đề → (series, số tập)  →  oEmbed check  →  match AniList  →  streaming_links
https://www.youtube.com/feeds/videos.xml?channel_id=UC...   (oEmbed không đảm bảo khả năng nhúng)
```

- Video là do **chủ kênh đăng công khai**; app chỉ **nhúng bằng IFrame Player API chính thức**.
- **Không** trích xuất stream (không `youtube_explode`, không `yt-dlp`) → không vi phạm ToS YouTube.
- oEmbed chỉ là kiểm tra sơ bộ; HTTP 200 không đảm bảo video nhúng được hoặc không bị chặn theo vùng.

### Chỉ dùng kênh Muse Việt Nam

Mặc định ingest **chỉ lấy Muse Việt Nam** (kênh có bản Việt sub/lồng tiếng):

```bash
# .env — muốn bật thêm kênh khác thì liệt kê, cách nhau bằng dấu phẩy
YOUTUBE_CHANNELS=muse_vn
# YOUTUBE_CHANNELS=muse_vn,ani_one_asia
```

Tên kênh sai chính tả → nổ ngay kèm danh sách hợp lệ (không "chạy xong mà không
lấy được gì").

### Xếp đúng BỘ và MÙA cho Muse VN

Muse đăng theo mùa: `One Punch Man - Mùa 2 - Tập 5`, `Fairy Tail (S3) - Tập 51`.
AniList tách mỗi mùa thành entry riêng, nên phải chọn đúng entry:

| Luật | Ví dụ |
|---|---|
| `parse_title` đọc mùa từ `Mùa 2` / `Season 2` / `Phần 2` / `(S2)` | `series_base` = tên không kèm mùa |
| Đọc **năm** trong tiêu đề (`(2011)`, `2014`) | `Hunter x Hunter (2011)` → `year_hint=2011` |
| Có mùa > 1 → **chỉ** nhận entry có ghi mùa đó | `One Punch Man 2nd Season` |
| Chưa có entry mùa đó → **không** gán vào mùa 1 | báo "chưa có entry mùa 2 (AniList)" |
| Loại entry không đủ chỗ cho tập | `Hunter x Hunter` 1999 (62 tập) bị loại khi có tập 148 |
| Tập > tổng số tập của bộ → **không ghi** | in `⚠ series có tập VƯỢT tổng số tập` |

Nhờ vậy 2 lỗi thật đã hết: 86 link tập 63–148 bị nhét vào entry 62 tập, và 102 link
tập 176–277 bị nhét vào entry 175 tập.

### Backfill toàn bộ lịch sử kênh (quan trọng!)

RSS chỉ trả **15 video mới nhất/kênh** → mỗi bộ chỉ có 1–4 tập. Một lựa chọn khác cần Google Cloud/API key (không đảm bảo số lượng tập):

```bash
# 1. Tạo key free (2 phút): console.cloud.google.com → enable "YouTube Data API v3"
#    → Credentials → Create credentials → API key
#    Kiểm key trước khi chạy:  bash scripts/check_keys.sh
# 2. Thêm vào .env
YOUTUBE_API_KEY=AIza...

# 3. Chạy backfill MỘT LẦN (lấy tối đa 5000 video/kênh)
python3 -m ingest.main youtube --deep --max-videos 5000
```

Chi phí quota (miễn phí 10.000 unit/ngày):

| Gọi API | Unit | Dùng cho |
|---|---|---|
| `channels.list` | 1 | 1 lần/kênh |
| `playlistItems.list` | 1 / 50 video | 5.000 video = 100 unit |
| `videos.list` | 1 / 50 video | kiểm tra `embeddable` + thời lượng |

→ 2 kênh × 5.000 video ≈ **400 unit**. Quota phụ thuộc cả các tác vụ khác trong cùng dự án.

Lợi ích phụ: `videos.list` cho biết `status.embeddable` và **thời lượng** →
tự động loại shorts/clip (< 4 phút) chính xác hơn nhiều so với đoán qua tiêu đề.

Sau lần backfill đầu, cron 6h chỉ cần chạy `youtube` (không `--deep`) để bắt tập mới.

### Backfill an toàn: ghi theo từng kênh + cache ra đĩa

Bản đầu gom video **cả 2 kênh** rồi mới ghép tên và ghi DB một lần. Hệ quả thật
gặp phải: 5.560 video được tải về, tới khâu ghép tên thì AniList trả 429 liên tục
(`… AniList rate limit, đợi 38s` lặp mãi) → **không ghi được dòng nào**, và
`ingest_runs` không có dấu vết. Nay:

| Cơ chế | Chi tiết |
|---|---|
| Ghi theo từng kênh | Xong kênh nào ghi kênh đó → hỏng kênh 2 không mất kênh 1 |
| Cache ghép tên | `.cache/match_cache.json` (tự sinh, đã gitignore). Chạy lại **không** search lại tên đã biết |
| Cache âm | Tên từng không khớp cũng được nhớ → không tốn 4 request lại |
| Sửa `aliases.json` | Cache phát hiện file đổi (`aliases_mtime`) → **bỏ mục âm**, thử lại tên vừa thêm alias |
| Giãn nhịp AniList | `MIN_INTERVAL` 1.0s/request; gặp 429 thì tăng ×1.5 (trần 6s) và ngủ theo `Retry-After` |
| Lỗi → **đỏ** | Kênh nào lỗi thì cuối job **ném lỗi** (exit ≠ 0) + `ingest_runs(ok=false, error=…)`, không "xanh mà không chạy" |

Chạy tiếp / chạy từng kênh:

```bash
python3 -m ingest.main youtube --deep --limit 200 --channel muse_vn   # 1 kênh
python3 -m ingest.main youtube --deep --limit 200                     # chạy tiếp cả 2
python3 -m ingest.main youtube --deep --limit 200 --no-cache          # ghép lại từ đầu
ANILIST_MIN_INTERVAL=2 python3 -m ingest.main youtube --deep          # chậm hơn, ít bị 429
rm -rf .cache                                                         # xoá cache hoàn toàn
```

Lần đầu: tên chưa có trong cache → mỗi tên tốn 1–4 request × ~1–6s. Vài trăm tên
là **10–30 phút**; nhìn `… ghép tên 50/480` để biết đang chạy. Muốn nhanh hơn
nhiều thì thêm alias tay: mỗi alias trong `aliases.json` là **0 request**.

### Thêm kênh mới
Lấy `channel_id` (không phải `@handle`):
```bash
curl -s "https://www.youtube.com/@TenKenh" | grep -o '"channelId":"UC[^"]*"' | head -1
```
Thêm vào `youtube.py` → `CHANNELS` với `key`, `name`, `channel_id`, `region`.

### Bản gộp nhiều tập (quan trọng)

Muse/Ani-One hay đăng **1 video chứa cả bộ** hoặc **một dải tập**:

| Tiêu đề | Trước đây | Bây giờ |
|---|---|---|
| `[Bản Lồng Tiếng] One Punch Man - Tập 01-24` | `episode=1` ❌ (app ghi "Tập 1", bấm vào ra video 24 tập, còn **ghi đè** link tập 1 thật) | `episode=0` → hiện thành ô **CẢ BỘ**, đứng cuối danh sách |
| `鬼滅の刃 第01-26話` | không parse được → mất | `episode=0` |
| `Crayon Shin-chan Tập 1000-1099` | `episode=1000` ❌ | **bỏ** (bản gộp một phần: không có số tập nào đúng) |
| `One Punch Man Tập 5-8` | `episode=5` ❌ | **bỏ** |

Nguyên tắc: chỉ nhận dải tập khi nó **bắt đầu từ tập 1** (cả bộ). Dải bắt đầu từ giữa
thì gán số nào cũng sai → bỏ, thà thiếu còn hơn sai.

Để truy ngược khi số tập bị parse sai, mỗi link lưu thêm `source_title` = tiêu đề
YouTube gốc. Kiểm:

```sql
select a.slug, l.episode_number, left(l.source_title, 50) as tieu_de
from streaming_links l join anime a on a.id = l.anime_id
where l.source_title ilike '%tập%' and l.episode_number = 0;
```

### Khi log báo "chưa khớp"
Tên tiếng Trung không search được trên AniList → thêm vào `aliases.json`:
```json
{"aliases": {"擅长捉弄人的高木同学": 99468}}
```
Đây là **phần biên tập tạo giá trị riêng** của app (không đối thủ nào có danh mục này bằng tiếng Việt).
Mẹo tìm ID: `python3 -m ingest.main` chỉ log tên, tìm trên https://anilist.co rồi lấy số trong URL.

## Cấu trúc

```
ingest/
├── main.py        # CLI + 3 job
├── config.py      # đọc .env
├── db.py          # upsert qua PostgREST (Supabase), có dry-run
├── anilist.py     # GraphQL: airingSchedules / seasonal / search
├── youtube.py     # RSS + parse tiêu đề + oEmbed embeddable check
├── match.py       # ghép tên series → AniList (alias → search → giản thể → rút gọn)
├── aliases.json   # map tay tên tiếng Trung → AniList ID
└── requirements.txt
```

## Debug nhanh

```bash
# Xem 1 job có chạy đúng không (ghi audit vào ingest_runs)
select * from ingest_runs order by started_at desc limit 10;

# Đếm kho phim free hiện có
select count(*) from v_free_catalog;

# Link chết (kiểm tra định kỳ)
select * from streaming_links where is_verified = false;
```
