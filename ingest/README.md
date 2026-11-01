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

## Job C hoạt động thế nào (và vì sao hợp pháp)

```
RSS kênh official  →  parse tiêu đề → (series, số tập)  →  oEmbed check  →  match AniList  →  streaming_links
https://www.youtube.com/feeds/videos.xml?channel_id=UC...   (oEmbed không đảm bảo khả năng nhúng)
```

- Video là do **chủ kênh đăng công khai**; app chỉ **nhúng bằng IFrame Player API chính thức**.
- **Không** trích xuất stream (không `youtube_explode`, không `yt-dlp`) → không vi phạm ToS YouTube.
- oEmbed chỉ là kiểm tra sơ bộ; HTTP 200 không đảm bảo video nhúng được hoặc không bị chặn theo vùng.

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

### Thêm kênh mới
Lấy `channel_id` (không phải `@handle`):
```bash
curl -s "https://www.youtube.com/@TenKenh" | grep -o '"channelId":"UC[^"]*"' | head -1
```
Thêm vào `youtube.py` → `CHANNELS` với `key`, `name`, `channel_id`, `region`.

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
