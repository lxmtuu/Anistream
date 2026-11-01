# supabase — Backend API cho AniStream (Edge Functions / Deno)

4 endpoint đọc + `/push` cho cron, **chỉ đọc** catalog, cache ở CDN. Không có endpoint ghi (v1 dùng
PostgREST + RLS trực tiếp từ app khi cần watchlist — xem `db/schema.sql` phần RLS).

| Function | Method | Mô tả | Cache |
|---|---|---|---|
| `home` | GET | toàn bộ trang chủ + lịch 7 ngày trong **1 request** | 300s |
| `search` | GET | tìm kiếm + filter (genre/year/season/sort/page) | 600s |
| `schedule` | GET | lịch phát theo khoảng thời gian (`alerts=true` cho cron push) | 300s |
| `anime` | GET | chi tiết theo `slug` hoặc `id` + related | 3600s |
| `push` | POST | cron gửi **"tập N vừa phát"** (FCM v1), chống gửi trùng | không cache |

---

## 1. Deploy (5 phút)

```bash
# cài CLI (1 lần)
npm i -g supabase

supabase login
supabase link --project-ref <project-ref>

# deploy cả 4
supabase functions deploy home search schedule anime

# (tuỳ chọn) kiểm tra secret đã có — Supabase tự inject 2 biến này:
#   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
supabase secrets list
```

Local dev:
```bash
supabase start
supabase functions serve --env-file ./supabase/.env
# → http://localhost:54321/functions/v1/home
```

## 2. Test bằng curl

```bash
BASE="https://<project-ref>.supabase.co/functions/v1"

curl -s "$BASE/home"                          | jq '.data.shelves[] | {title, n: (.ids|length)}'
curl -s "$BASE/search?q=frieren"              | jq '.data.items[0] | {title, score, is_free}'
curl -s "$BASE/anime?slug=sousou-no-frieren"  | jq '.data.anime | {title, n_eps: (.episodes|length)}'
curl -s "$BASE/schedule?limit=5"              | jq '.data.slots[] | {title, episode, airing_at, free}'
curl -s "$BASE/schedule?alerts=true"          | jq '.data.slots | length'
```

Hoặc chạy smoke test có sẵn: `bash scripts/test_api.sh <BASE>`

Kết quả mong đợi của `/home` (rút gọn):
```json
{
  "data": {
    "generated_at": "2026-11-01T09:40:00.000Z",
    "season": { "season": "FALL", "year": 2026 },
    "anime": [ { "id": 154587, "slug": "…", "title": "…", "is_free": true,
                 "episodes": [ { "number": 1, "video_id": "t9JcpC6Ogi0" } ],
                 "platforms": [ { "name": "Crunchyroll" } ] } ],
    "shelves": [ { "title": "Xem ngay — miễn phí, hợp pháp", "kind": "free", "ids": [154587] } ],
    "schedule": [ { "anime_id": 154587, "episode": 6, "airing_at": "2026-11-01T15:30:00+00:00" } ]
  },
  "meta": { "generated_at": "…", "ttl": 300, "count": 42 }
}
```

## 2a. Test (không cần Supabase)

```bash
bash scripts/test_edge.sh     # 13 test: chống spam, chống gửi trùng, nội dung tin
```

Cách làm: esbuild transpile `_shared/push_plan.ts` → JS, rồi `node --test`.
Chạy tự động ở `.github/workflows/edge.yml` mỗi khi sửa `supabase/`.

## 2b. Push "tập mới vừa ra" (`/push`)

Cron gọi mỗi **10–15 phút**. Luồng:

```
episodes (airing_at trong 25' gần nhất)
   → GIÀNH quyền gửi: insert vào sent_episode_pushes với ignoreDuplicates
     (chỉ lần cron nào insert được dòng mới mới gửi → 2 lần cron chồng nhau
      không gửi trùng; nếu gửi thất bại toàn bộ thì nhả quyền để lần sau thử lại)
   → tìm push_subscriptions CÓ bộ đó trong anime_ids (toán tử overlaps, dùng GIN index)
   → mỗi thiết bị chỉ 1 tin/1 bộ, chọn tập SỐ LỚN NHẤT (tránh spam)
   → FCM HTTP v1 (OAuth2 JWT RS256 từ service account)
   → token chết (404/UNREGISTERED) → is_active = false
   → ghi sent_episode_pushes (gửi lại cron cũng không trùng)
```

### Setup (10 phút)
```bash
# 1. Firebase Console → Project settings → Service accounts → Generate new private key
supabase secrets set FCM_SERVICE_ACCOUNT="$(cat service-account.json)"
supabase secrets set PUSH_CRON_SECRET="$(openssl rand -hex 24)"

# 2. deploy
supabase functions deploy push

# 3. thử KHÔNG gửi thật (chỉ báo cáo sẽ gửi gì)
curl -X POST "$BASE/push?dry_run=true" | jq '.data | {new_episodes, devices, messages_to_send, preview}'

# 4. gửi thật
curl -X POST "$BASE/push" -H "x-cron-secret: $PUSH_CRON_SECRET" | jq '.data'
```

Kết quả khi chạy thật:
```json
{ "data": { "window_minutes": 25, "new_episodes": 3, "devices": 128,
            "messages": 154, "sent": 151, "failed": 3, "deactivated_tokens": 2 } }
```

Cron (GitHub Actions, thêm vào `.github/workflows/ingest.yml` hoặc file riêng):
```yaml
- cron: "*/15 * * * *"
  run: |
    curl -s -X POST "${{ secrets.API_BASE }}/push" \
      -H "x-cron-secret: ${{ secrets.PUSH_CRON_SECRET }}"
```

### Bảo mật
- `verify_jwt = false` (cron không có JWT người dùng) nhưng **bắt buộc** header `x-cron-secret`.
- Nếu chưa set `PUSH_CRON_SECRET` → function **chỉ cho `dry_run`** (mặc định an toàn).
- `sent_episode_pushes` không có RLS policy → chỉ service_role truy cập được.

### Ai nhận tin?
`push_subscriptions.anime_ids` — app tự đồng bộ mỗi khi **watchlist** thay đổi.
Người dùng **không cần đăng nhập**: mỗi thiết bị có `device_id` ngẫu nhiên (lưu trong
`shared_preferences`). Khi có auth (bước 4), chỉ cần gắn thêm `user_id`.

## 3. Hợp đồng API (đừng phá)

`_shared/assemble.ts` là **nguồn sự thật duy nhất** về shape DTO. Nó khớp 1-1 với
`app/lib/core/models/anime.dart`:

```
id slug title title_vi title_native cover banner score year season format status
episodes_total genres[] synopsis is_free platforms[{name,url,verified}]
episodes[{number,title,video_id,platform,airing_at}] popularity
```

Quy tắc:
- `score` là **number 0–10** (DB lưu numeric(4,1)); trả `null` nếu chưa có điểm.
- `is_free = true` **chỉ khi** có link `kind='free_legal'` và `is_verified = true`.
- `episodes[].video_id` chỉ khác `null` khi có video **official & cho nhúng** (`oEmbed` 200 lúc ingest).
- `episodes[].number = 0` nghĩa là **link cho cả bộ** (movie/complete series).
- Không bao giờ trả `service_role` key hay nội dung HTML thô.

**Đổi field → phải sửa cả 3 chỗ:** `assemble.ts` → `anime.dart` → chạy `flutter test`.

## 4. Cấu trúc

```
supabase/
├── config.toml                 # verify_jwt = false cho các function công khai
└── functions/
    ├── _shared/
    │   ├── respond.ts          # CORS, json/ok/fail, withGuard (luôn trả JSON)
    │   ├── supabase.ts         # admin client (service_role, server-side)
    │   ├── assemble.ts         # ⭐ DB row → DTO (hợp đồng API với app)
    │   └── query.ts            # season UTC, parse int, chống injection sort/ilike
    │   ├── fcm.ts              # FCM HTTP v1: JWT RS256 → OAuth2 → messages:send
    │   └── push_plan.ts        # logic thuần: ai nhận gì (đã unit-test bằng Node)
    ├── home/index.ts
    ├── search/index.ts
    ├── schedule/index.ts
    ├── anime/index.ts
    └── push/index.ts
```

## 5. Vì sao thiết kế thế này

| Quyết định | Lý do |
|---|---|
| `home` trả **tất cả** trong 1 request | Mở app < 1.2s; 1 lượt mạng thay vì 5; tiết kiệm pin/data |
| Cache 300s ở CDN | 1.000 người dùng đồng thời → chỉ vài query Postgres. Free tier Supabase chịu được |
| Gộp episodes/links bằng `in(...)` + `groupByAnime` | Tránh N+1 (20 anime = 1 query thay vì 20) |
| Sort whitelist (`resolveSort`) | Không cho client truyền tên cột bất kỳ → chống injection |
| `ilike` escape `%_\` | Tránh user gõ `%` làm query full table |
| `verify_jwt = false` cho catalog | Dữ liệu công khai; RLS vẫn bảo vệ bảng người dùng |
| `alerts=true` ở `/schedule` | Cron chỉ push tập của bộ **có người theo dõi** → không spam |

## 6. Lỗi thường gặp

| Triệu chứng | Nguyên nhân / cách sửa |
|---|---|
| `Thiếu SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY` | Chạy local phải có `--env-file`; trên cloud Supabase tự inject |
| `data.anime: []` dù DB có dữ liệu | Chưa chạy ingest (`python3 -m ingest.main all`) hoặc `is_published = false` |
| `is_free` luôn `false` | `streaming_links.is_verified` chưa `true` → chạy `python3 -m ingest.main youtube` |
| 401 khi gọi bằng curl | Function để `verify_jwt = true` → thêm `-H "Authorization: Bearer <anon key>"` |
| App trắng bảng sau khi đổi backend | Shape DTO lệch với `anime.dart` → so lại `assemble.ts` |
| `rate_limited` | Supabase free tier giới hạn request/phút; tăng cache `s-maxage` |

## 7. Việc tiếp theo ở backend

- [x] `push` function: cron 15 phút → FCM v1, chống trùng, tự dọn token chết
- [ ] `me` function (verify_jwt = true): watchlist, progress — thay cho việc app gọi PostgREST trực tiếp
- [ ] `og` function: OG image cho share link (tăng viral)
- [ ] Thêm `Database` type sinh tự động (`supabase gen types typescript`) để bỏ `any`
- [ ] Gộp `/home` thành 1 RPC Postgres (giảm 6 query xuống 1 round-trip)
