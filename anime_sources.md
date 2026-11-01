# Nguồn API anime (hợp pháp, ổn định) + cách cập nhật tập mới

> Mình đã test trực tiếp từng endpoint dưới đây (cột "Test" = kết quả gọi thật ngày 01/11/2026).
> Không cần key trừ khi có ghi chú. Tất cả đều là metadata chính thức/community — không phải link stream lậu.

---

## 1. Bảng tổng hợp

| # | Nguồn | Base URL | Auth | Rate limit | Mạnh nhất ở | Test |
|---|-------|----------|------|-----------|-------------|------|
| 1 | **AniList** (GraphQL) | `https://graphql.anilist.co` | Không | ~30–90 req/phút | ⭐ **Lịch phát tập mới theo giờ chính xác nhất**, trending, search, filter | ✅ 200 |
| 2 | **Kitsu** (JSON:API) | `https://kitsu.io/api/edge` | Không | ~60 req/phút | `sort=-updatedAt` → biết cái gì vừa cập nhật, catalog lớn | ✅ 200 |
| 3 | **AnimeSchedule.net v3** | `https://animeschedule.net/api/v3` | Không (basic) | Không rõ, ~1 req/s | Bảng giờ chiếu + đếm ngược, có cả **giờ sub/dub** | ✅ 200 |
| 4 | **Shikimori** | `https://shikimori.one/api` | Không (cần header `User-Agent`) | ~5 req/s | Catalog, lịch chiếu, điểm MAL đồng bộ | ✅ 200 |
| 5 | **Jikan v4** (MyAnimeList) | `https://api.jikan.moe/v4` | Không | **3 req/s**, 60 req/phút | Search MAL, seasonal, top, **MAL ID** để map sang nơi khác | ⚠️ timeout từ sandbox (bị chặn IP datacenter) — vẫn chạy tốt từ máy bạn |
| 6 | **TMDB** | `https://api.themoviedb.org/3` | `api_key` (free) | ~50 req/s | ⭐ **Tên + tóm tắt tiếng Việt** (`language=vi-VN`), poster đẹp | cần key |
| 7 | **AnimeThemes.moe** | `https://api.animethemes.moe` | Không | ~1 req/s | OP/ED, video theme | ✅ 200 |
| 8 | **trace.moe** | `https://api.trace.moe` | Không | ~20 req/phút | Tìm anime từ ảnh cắt màn hình | ✅ 200 |
| 9 | **ANN Encyclopedia** | `https://cdn.animenewsnetwork.com/encyclopedia/reports.xml` | Không | — | Report XML hằng ngày (anime mới, staff, ratings) | ⚠️ 403 (Cloudflare chặn datacenter) |
| 10 | **AniDB HTTP API** | `http://api.anidb.net:9001/httpapi` | Cần đăng ký `client` + `clientver` | 1 req/2s | Dữ liệu file/tập cực chi tiết | cần đăng ký |

---

## 2. Muốn "cập nhật anime thường xuyên" → dùng cái nào?

Có 2 kiểu "cập nhật", đừng lẫn:

### A. Cập nhật **lịch phát sóng** (tập mới ra lúc nào) → **AniList `airingSchedules`**
Đây là thứ chính xác nhất, có timestamp Unix + số tập.

```graphql
query {
  Page(perPage: 50) {
    airingSchedules(
      airingAt_greater: 1762000000   # từ giờ này (unix)
      airingAt_lesser: 1762086400    # đến giờ này
      sort: TIME
    ) {
      airingAt
      episode
      media {
        id
        title { romaji english native }
        coverImage { large }
        siteUrl
        averageScore
        status
      }
    }
  }
}
```
→ Lưu `media.id` làm khóa chính. Gọi 1 lần/giờ là đủ để có feed "tập mới".

### B. Cập nhật **database của bạn** (phim mới thêm, thông tin đổi) → **Kitsu `sort=-updatedAt`**
```
GET https://kitsu.io/api/edge/anime?sort=-updatedAt&page[limit]=20
```
Mỗi lần chạy, lấy 20 bản ghi mới nhất theo `updatedAt` → chỉ upsert phần thay đổi.

### C. Polling bao lâu?
| Việc | Tần suất hợp lý |
|---|---|
| Lịch phát tập (AniList) | 30–60 phút/lần |
| Catalog mới (Kitsu `-updatedAt`) | 6 giờ/lần |
| Mùa mới (seasonal) | 1 lần/ngày |
| Cache về DB của bạn | TTL 12–24h, vì API gốc đổi rất ít |

⚠️ Đừng gọi mỗi request người dùng → API gốc. Luôn có **DB + cron** ở giữa, nếu không sẽ bị 429.

---

## 3. Code mẫu copy-paste được

### Python – AniList (không cần key)
```python
import requests, time

Q = """query($from:Int,$to:Int){
  Page(perPage:50){ airingSchedules(airingAt_greater:$from, airingAt_lesser:$to, sort:TIME){
    airingAt episode media{ id title{romaji english} coverImage{large} siteUrl }
  }} }"""

r = requests.post("https://graphql.anilist.co", json={
    "query": Q,
    "variables": {"from": int(time.time()), "to": int(time.time()) + 86400},
}, timeout=20)
r.raise_for_status()
for s in r.json()["data"]["Page"]["airingSchedules"]:
    print(time.strftime("%H:%M", time.localtime(s["airingAt"])),
          f'ep {s["episode"]}', s["media"]["title"]["romaji"])
```

### JavaScript / Node (fetch, không cần lib)
```js
const res = await fetch("https://graphql.anilist.co", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query: Q, variables: { from: now, to: now + 86400 } })
});
const { data } = await res.json();
```

### Search + lấy chi tiết
```python
# AniList search
POST /  {"query": 'query($q:String){Page(perPage:5){media(search:$q,type:ANIME){id title{romaji english} averageScore}}}',
        "variables": {"q": "frieren"}}

# Kitsu search (REST)
GET https://kitsu.io/api/edge/anime?filter[text]=frieren&page[limit]=5

# Jikan (MAL)
GET https://api.jikan.moe/v4/anime?q=frieren&limit=5
```

### TMDB lấy tên tiếng Việt
```
GET https://api.themoviedb.org/3/search/tv?query=frieren&language=vi-VN&api_key=KEY
```
→ map sang AniList bằng `externalLinks` / `idMal` (AniList có `idMal` = MAL ID; TMDB thì phải match theo tên + năm).

---

## 4. Những cạm bẫy cần biết

1. **Không có ID chung.** AniList ID ≠ MAL ID ≠ Kitsu ID ≠ TMDB ID.
   → Lưu **tất cả** ID vào bảng `anime_external_ids` (anilist_id, mal_id, kitsu_id, tmdb_id, slug). AniList có sẵn `idMal` — dùng làm cầu nối chính.
2. **Jikan chặn IP datacenter** (VPS/Hosting hay bị 403/timeout). AniList & Kitsu thì không. Nếu deploy lên VPS mà Jikan lỗi → proxy hoặc bỏ Jikan.
3. **`averageScore` khác thang điểm**: AniList 0–100, MAL 0–10, Kitsu 0–100 nhưng khác nguồn.
4. **Mùa (season) tính theo UTC**, không theo giờ VN. Anime mùa Đông bắt đầu từ 01/01 UTC.
5. **Đừng hardcode season**: `tháng 1–3 = WINTER, 4–6 = SPRING, 7–9 = SUMMER, 10–12 = FALL`.
6. **Nếu cần "phim đang chiếu ở VN"**: TMDB `watch/providers` region `VN` (Netflix, FPT Play, Galaxy Play…) → cho biết nền tảng hợp pháp nào đang có phim đó. Đây là cách "xem ở đâu" đúng luật.

---

## 5. Nếu bạn cần "xem ở đâu hợp pháp" thay vì link stream

| Việc | API |
|---|---|
| Phim này chiếu nền tảng nào ở VN | TMDB `/tv/{id}/watch/providers` → `results.VN` |
| Link xem chính thức | AniList `externalLinks` (lọc `Crunchyroll`, `Netflix`, `Bilibili`, `Muse Asia`) |
| Nền tảng VN | Muse VN, Bilibili VN, FPT Play, Netflix, Galaxy Play (không có API công khai — phải deep link thủ công) |

---

## 6. Repo "sườn" nên tham khảo
- `AniList APIv2 docs` → https://docs.anilist.co (GraphQL, có playground)
- `jikan.moe` docs → https://docs.api.jikan.moe
- `kitsu` docs → https://kitsu.docs.apiary.io
- `animeschedule.net/api/v3` docs → https://animeschedule.net/api/v3/documentation
