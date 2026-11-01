# AniStream — Lộ trình xây app anime kiểu Netflix (Flutter: mobile + desktop)

**Ngày lập:** 01/11/2026 · **Stack chốt:** Flutter + Supabase + GitHub Actions · **Ngân sách hạ tầng:** 0đ
**Tài liệu kèm theo:** `db/schema.sql` (schema Postgres sẵn chạy được) · `anime_sources.md` (danh sách API) · `anime_api_demo.py`

---

## 0. Trả lời thẳng câu quan trọng nhất

> *"Hãy làm sao miễn là có thể miễn phí và có thể xem đầy đủ anime và cập nhật tập mới nhất."*

Mình phải nói rõ ngay, vì nó quyết định toàn bộ lộ trình — **không phải mình né tránh, mà đây là sai lầm khiến 90% app anime sinh viên chết**:

**Không tồn tại mô hình "miễn phí + đầy đủ + tập mới nhất" mà hợp pháp.** Ba yếu tố đó chỉ có thể có cùng lúc bằng cách phát nội dung bản quyền không được cấp phép. Và với một **startup thật** (bạn đã chọn "sản phẩm thật, có người dùng"), mô hình đó chết ở 5 điểm rất cụ thể:

| Chặn | Thực tế |
|---|---|
| **App Store** | Guideline **5.2.3** – "apps that stream copyrighted content without authorization are rejected". Không lách được bằng cách "app chỉ hiển thị link", nếu link trỏ vào server phát lậu. |
| **Google Play** | Intellectual Property policy: gỡ app + đình chỉ tài khoản dev vĩnh viễn sau 3 lần strike. |
| **Hạ tầng** | Cloudflare, Vercel, Supabase, AWS đều ban khi có DMCA. App của bạn sẽ mất backend trước khi có 1.000 user. |
| **Pháp lý VN** | Phát tán tác phẩm không được phép: xử phạt hành chính theo NĐ 131/2013 (hàng chục triệu đồng + buộc tháo gỡ); nếu **thương mại, thu lợi, quy mô lớn** có thể bị truy cứu TNHS **Điều 225 BLHS** (tội xâm phạm quyền tác giả). |
| **Monetize** | Stripe/PayPal/AdMob từ chối hoặc đóng băng app vi phạm bản quyền. Không có tiền → không phải startup. |

Và một điểm kỹ thuật nữa: các site kiểu animehay đổi domain liên tục, dùng host video thứ ba có token hết hạn, chặn Referer/CORS. Scrape chúng làm nguồn **không bền** — app của bạn hỏng mỗi 2–4 tuần. Tức là **ngay cả khi chấp nhận rủi ro pháp lý, nó vẫn là một sản phẩm tồi.**

### Vậy làm gì để vẫn đạt ~90% mục tiêu, hợp pháp, 0đ?

**Mô hình Discovery + Deep-link + Official Embed** (đúng mô hình của LiveChart, AniList, MyAnimeList — đều là app thật, có tiền, lên store được):

| Mục tiêu của bạn | Cách thoả mãn hợp pháp |
|---|---|
| Catalog **đầy đủ** anime | ✅ **100%** – AniList/Kitsu có ~20.000+ bộ, kể cả mùa mới ra tuần này |
| **Cập nhật tập mới nhất** | ✅ **Chính xác tới giờ** – `airingSchedules` có timestamp từng tập + push notification |
| **Miễn phí hạ tầng** | ✅ Supabase free + Actions free + FCM free = **0đ** |
| Xem phim trong app | ⚠️ Được **nhúng video chính thức** (YouTube channel official, Muse VN, Ani-One) + **deep link** sang Netflix/Crunchyroll/Bilibili/FPT Play. Bấm "Xem" là mở thẳng tập đó trên app kia. |
| Tự host toàn bộ video | ❌ Chỉ khi có license (kênh này mình sẽ **không** hướng dẫn) — **hoặc** dùng catalog public domain / nội dung bạn tự làm (xem §11) |

Nói cách khác: **app của bạn là "cửa ngõ + lịch + cộng đồng" cho anime**, không phải kho phim lậu. Người dùng vẫn "xem đầy đủ anime mới nhất" — chỉ là bấm 1 lần để sang nơi phát hợp pháp (và điều này *tốt hơn* cho UX: họ không phải chịu quảng cáo casino, không bị nhiễm malware — vốn là thứ mọi site lậu đều có).

Phần còn lại của tài liệu này là lộ trình kỹ thuật chi tiết cho mô hình đó.

---

## 1. Kiến trúc hệ thống

```
┌──────────────────────────── NGUỒN DỮ LIỆU (miễn phí, không cần key) ──────────────────────────┐
│  AniList GraphQL        Kitsu JSON:API        TMDB API           AniList externalLinks       │
│  (lịch tập, trending)   (catalog, -updatedAt) (tên+vi-VN,        (link xem chính thức)       │
│                                                 poster, provider)                            │
└──────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                       │  GitHub Actions cron (0đ, 2.000 phút/tháng)
                                       ▼
                    ┌──────────────────────────────────────┐
                    │  INGEST WORKER (Python/TS script)    │
                    │  • dedupe + map ID (anilist↔mal↔tmdb)│
                    │  • chuẩn hoá score, season (UTC)     │
                    │  • upsert, ghi ingest_runs           │
                    └──────────────┬───────────────────────┘
                                   ▼
     ┌──────────────────────────────────────────────────────────────┐
     │                     SUPABASE (free tier)                     │
     │  Postgres  ──  anime / episodes / streaming_links            │
     │            └─  profiles / watchlist / watch_history          │
     │  Auth (email + OAuth) · Row Level Security                   │
     │  Edge Functions (Deno) ── REST layer + rate limit + webhook  │
     │  pg_cron ── sinh thông báo tập mới                           │
     └──────────────┬───────────────────────────────┬───────────────┘
                    │ HTTPS/JSON                    │ FCM (free)
                    ▼                               ▼
     ┌──────────────────────────────┐     ┌─────────────────────────┐
     │  FLUTTER APP (1 codebase)    │     │  Push: "Tập 6 vừa ra"   │
     │  Android · iOS · Windows     │     └─────────────────────────┘
     │  macOS · Linux · Web         │
     │  Riverpod + Drift (offline)  │
     └──────────────┬───────────────┘
                    │ url_launcher / app_links
                    ▼
     Netflix · Crunchyroll · Bilibili · Muse VN · FPT Play · YouTube official
```

**Nguyên tắc thiết kế cốt lõi (đừng phá vỡ):**

1. **App không bao giờ gọi AniList trực tiếp.** Mọi thứ đi qua DB của bạn. Lý do: rate limit, tốc độ, offline, và bạn kiểm soát được dữ liệu hiển thị.
2. **Metadata do bạn sở hữu (bản dịch, sắp xếp, tag VN), video thì không.** Đây là ranh giới pháp lý.
3. **Catalog là read-only với client.** Chỉ service_role mới ghi (Edge Function/cron). RLS lo phần còn lại.
4. **Offline-first cho metadata.** Video cần mạng, nhưng "lịch của tôi", "watchlist", "tập đã xem" phải chạy không cần mạng.

---

## 2. Data pipeline — trái tim của sản phẩm

Đây là phần tạo ra "cảm giác Netflix": **dữ liệu tươi**. Ba job, chạy bằng GitHub Actions (workflow file bên dưới).

### Job A — Lịch phát (`schedule`), mỗi 30 phút
```graphql
# POST https://graphql.anilist.co
query($from:Int,$to:Int){
  Page(perPage:50){
    airingSchedules(airingAt_greater:$from, airingAt_lesser:$to, sort:TIME){
      airingAt episode
      media{ id idMal title{romaji english native} coverImage{large extraLarge}
             siteUrl averageScore episodes status season seasonYear
             genres studios(isMain:true){nodes{name}} nextAiringEpisode{episode airingAt} }
    }
  }
}
# variables: from = now, to = now + 26h  (cửa sổ 26h để không lọt tập khi cron trễ)
```
→ Upsert vào `anime` + `episodes(number, airing_at)`.

### Job B — Catalog (`catalog`), mỗi 6 giờ
```
GET https://kitsu.io/api/edge/anime?sort=-updatedAt&page[limit]=20
```
→ Upsert 20 bản ghi mới nhất. Đây là cách bắt phim mới thêm mà không cần crawl toàn bộ.
Bù lại mỗi **đêm** một job `catalog_full` chạy theo mùa: AniList `season + seasonYear` (vài trăm bộ/mùa) để đảm bảo không thiếu.

### Job C — Làm giàu (`enrich`), mỗi ngày 1 lần
- **TMDB** `language=vi-VN`: lấy `title_vi`, `overview` (synopsis tiếng Việt) → đây là **giá trị độc quyền** của app bạn mà AniList không có.
- **TMDB** `/tv/{id}/watch/providers` → `streaming_links` region `VN` → biết phim chiếu nền tảng nào ở VN.
- **AniList** `externalLinks` → lọc domain `crunchyroll|netflix|bilibili|muse|youtube` → link chính thức theo bộ.
- **Manual curation** (quan trọng): bảng `platform_map` cho Muse VN / Ani-One / Bilibili theo mùa — vì provider data của TMDB ở VN còn thiếu. Đây cũng là chỗ bạn tạo "chất lượng biên tập" mà đối thủ không có.

### Quy tắc map ID (đừng bỏ qua, đây là bug #1 của mọi app anime)
```
AniList.id  ←→  anime.anilist_id      (khóa chính thật)
AniList.idMal →  anime.mal_id         (cầu nối sang Jikan/MAL)
Kitsu.id    →  anime.kitsu_id         (string, vd "46474")
TMDB        →  match bằng (tên romaji chuẩn hoá + năm), KHÔNG match bằng tên Việt
```
Luôn lưu **tất cả** ID. Khi API này chết/đổi, bạn vẫn nối được.

### GitHub Actions: `.github/workflows/ingest.yml`
```yaml
name: ingest
on:
  schedule:
    - cron: "*/30 * * * *"   # A. schedule
    - cron: "0 */6 * * *"    # B. catalog
    - cron: "17 19 * * *"    # C. enrich (02:17 giờ VN)
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r ingest/requirements.txt
      - run: python ingest/main.py "${{ github.event.schedule == '*/30 * * * *' && 'schedule' || 'full' }}"
        env:
          SUPABASE_URL:  ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY:  ${{ secrets.SUPABASE_SERVICE_KEY }}   # service_role, không phải anon
          TMDB_API_KEY:  ${{ secrets.TMDB_API_KEY }}
```
> ⚠️ Cron của GitHub Actions có thể trễ 5–15 phút khi tải cao. Với app anime thì hoàn toàn chấp nhận được (tập phim không "lệch" vì thế). Nếu cần chính xác hơn → Supabase `pg_cron` + `pg_net`.

### Upsert (SQL chuẩn cho ingest)
```sql
insert into anime (anilist_id, mal_id, slug, title_romaji, title_english, title_native,
                   cover_url, year, season, status, episodes_total, score, genres,
                   popularity, last_synced_at)
values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14, now())
on conflict (anilist_id) do update set
  title_english = excluded.title_english,
  cover_url     = excluded.cover_url,
  status        = excluded.status,
  episodes_total= excluded.episodes_total,
  score         = excluded.score,
  popularity    = excluded.popularity,
  last_synced_at= now()
returning id;
```
Với `episodes`: `on conflict (anime_id, number) do update set airing_at = excluded.airing_at` — AniList hay dời giờ chiếu, phải cho phép sửa.

---

## 3. Cơ sở dữ liệu

Đã có sẵn file **`db/schema.sql`** — chạy thẳng vào Supabase SQL Editor. Gồm:

| Bảng | Vai trò |
|---|---|
| `anime` | catalog + tất cả external ID + `title_vi`, `synopsis_vi` |
| `episodes` | từng tập + `airing_at` (nguồn của feed "tập mới") |
| `streaming_links` | deep link hợp pháp, có `is_verified` để tránh link chết |
| `profiles`, `watchlist`, `watch_history` | tài khoản, theo dõi, resume |
| `push_tokens`, `episode_alerts` | thông báo tập mới |
| `ingest_runs` | audit cron (bắt buộc, để debug "sao hôm nay feed trống") |
| `v_anime_card`, `v_new_episodes` | view sẵn cho API, tránh N+1 |

Có sẵn: GIN trigram index (search mờ tiếng Việt không cần gõ dấu), RLS policies, trigger `updated_at`.

---

## 4. API contract (Edge Functions)

Base: `https://<project>.supabase.co/functions/v1/api`

| Method | Endpoint | Trả về |
|---|---|---|
| GET | `/home?locale=vi` | 5 shelf: `trending`, `new_episodes`, `this_season`, `continue_watching`, `top_rated` |
| GET | `/anime/{slug}` | chi tiết + episodes + streaming_links (VN) + related |
| GET | `/search?q=&genre=&year=&season=&sort=&page=` | kết quả + total |
| GET | `/schedule?from=&to=` | lịch phát (feed chính) |
| GET | `/me/watchlist` | cần JWT |
| PUT | `/me/watchlist/{anime_id}` | `{status, progress, score}` |
| POST | `/me/progress` | `{anime_id, episode, position_sec}` |
| POST | `/me/alerts/{anime_id}` | bật/tắt thông báo tập mới |
| POST | `/push/register` | `{token, platform}` |

**Quy ước:**
- Mọi response bọc `{ data, meta }`. Lỗi `{ error: { code, message } }`.
- Cache-Control: `/home` 300s, `/anime/*` 3600s, `/schedule` 600s (CDN của Supabase/Cloudflare free đã lo).
- `/home` phải là **1 request duy nhất** (không bắt app gọi 5 API) → tiết kiệm pin, data, và thời gian mở app dưới 300ms.
- Phân trang bằng cursor (`?cursor=<airing_at,id>`) cho `/schedule`, offset cho `/search`.

Ví dụ `/home`:
```json
{
  "data": {
    "new_episodes": [
      { "anime_id": 154587, "slug": "sousou-no-frieren",
        "title": "Sousou no Frieren", "title_vi": "Frieren: Pháp Sư Tiễn Táng",
        "cover": "https://…/cover.jpg", "episode": 6,
        "airing_at": "2026-11-01T15:30:00Z", "score": 9.1,
        "platforms": ["crunchyroll", "muse_vn"] }
    ],
    "continue_watching": [ { "…": "…", "position_sec": 812, "duration": 1440 } ]
  },
  "meta": { "generated_at": "2026-11-01T08:20:00Z", "ttl": 300 }
}
```

---

## 5. Flutter — cấu trúc dự án & quyết định kỹ thuật

### Packages (đã cân nhắc kỹ, tối thiểu mà đủ)
```yaml
dependencies:
  flutter_riverpod: ^2.6.1        # state management
  go_router: ^14.6.0              # routing + deep link
  dio: ^5.7.0                     # HTTP + interceptor
  drift: ^2.20.0                  # SQLite local (offline catalog, resume)
  sqlite3_flutter_libs: ^0.5.24
  supabase_flutter: ^2.8.0        # auth + realtime
  cached_network_image: ^3.4.1    # poster cache (tiết kiệm data)
  media_kit: ^1.1.11              # VIDEO: tốt nhất cho desktop (HLS/mkv/4K)
  media_kit_video: ^1.2.4
  media_kit_libs_video: ^1.0.4
  video_player: ^2.9.2            # mobile fallback (ExoPlayer/AVPlayer)
  url_launcher: ^6.3.1            # deep link ra nền tảng hợp pháp
  app_links: ^6.3.2               # nhận deep link quay lại app
  flutter_local_notifications: ^18.0.1
  firebase_messaging: ^15.1.5     # push (Android/iOS; desktop → xem §10)
  shared_preferences: ^2.3.3
  flutter_secure_storage: ^9.2.2
  intl: ^0.19.0
  freezed_annotation: ^2.4.4      # model immutable
  json_serializable: ^6.9.0
dev_dependencies:
  build_runner, drift_dev, freezed, json_serializable
```

### Cấu trúc thư mục (feature-first, không phải layer-first)
```
lib/
├── main.dart
├── app/
│   ├── router.dart              # GoRouter + deep links anistream://anime/:slug
│   ├── theme.dart               # dark-first (#0e1117), 2 theme: dark + AMOLED
│   └── env.dart                 # --dart-define=API_BASE=...
├── core/
│   ├── api/  client.dart  endpoints.dart  interceptors.dart
│   ├── db/   app_database.dart  daos/
│   ├── models/ anime.dart episode.dart streaming_link.dart  (freezed)
│   └── widgets/ anime_card.dart  skeleton.dart  error_state.dart
└── features/
    ├── home/       home_screen.dart  home_provider.dart
    ├── search/     search_screen.dart  filter_sheet.dart
    ├── detail/     detail_screen.dart  episode_list.dart
    ├── schedule/   schedule_screen.dart        # lịch tuần, "tập mới"
    ├── player/     player_screen.dart  official_embed_screen.dart
    ├── library/    library_screen.dart  (watchlist)
    ├── profile/    profile_screen.dart  settings_screen.dart
    └── auth/       login_screen.dart  auth_provider.dart
```

### Screen map (đúng UX Netflix, không thừa)
| Screen | Nội dung |
|---|---|
| **Home** | Hero banner (1 bộ trending) + 5 shelf ngang, lazy-load poster |
| **Search** | Search-as-you-type (debounce 350ms) + filter sheet (thể loại/năm/mùa/trạng thái/sắp xếp) |
| **Detail** | Banner mờ + poster + meta + nút **▶ Xem ngay** (deep link) + danh sách nền tảng + grid tập + related + nút "Theo dõi/Thông báo" |
| **Schedule** | Lịch 7 ngày dạng tab ngày, nhóm theo giờ, đếm ngược, badge "sắp chiếu" |
| **Player** | Chỉ dùng cho nguồn hợp pháp (embed YouTube official / tập public domain). Chọn server, phụ đề, tốc độ, PiP, resume |
| **Library** | Watchlist 5 tab trạng thái + "Xem tiếp" |
| **Profile** | Tài khoản, ngôn ngữ, theme, thông báo, giới thiệu pháp lý |

### 3 quyết định kỹ thuật quan trọng nhất

**1. Desktop không dùng `video_player`** — nó không hỗ trợ Windows/Linux. Dùng `media_kit` cho desktop, `video_player` cho mobile (hỗ trợ hardware decode + DRM tốt hơn). Tạo `PlayerFactory` để switch theo `Platform.isAndroid || Platform.isIOS`.

**2. Offline-first bằng Drift, không phải bằng cache HTTP**
```dart
// core/db/app_database.dart (rút gọn)
@DriftDatabase(tables: [AnimeTable, EpisodeTable, WatchlistTable])
class AppDatabase extends _$AppDatabase {
  Future<List<AnimeRow>> library() =>
      (select(animeTable)..orderBy([(t) => OrderingTerm.desc(t.updatedAt)])).get();
}
```
Chiến lược: **read-through** — UI đọc Drift trước (instant, 0ms), gọi API ở background, ghi vào Drift, Drift stream tự cập nhật UI. Người dùng mở app là thấy nội dung ngay cả khi mạng 3G.

**3. Deep link phải "quay lại được"**
```dart
// Bấm "Xem trên Netflix"
final uri = Uri.parse(link.url);
if (await canLaunchUrl(uri)) {
  await launchUrl(uri, mode: LaunchMode.externalApplication);   // mở app Netflix nếu có
  // đồng thời ghi nhận để hiện trong "Continue watching" của mình
  await ref.read(progressRepo).markOpened(animeId, episode);
}
```
→ Đây là điểm ăn tiền: dù xem ở app khác, **AniStream vẫn là nơi họ quản lý tiến độ**. Đó là lý do họ quay lại mỗi ngày.

---

## 6. Lộ trình 14 tuần (sprint 1 tuần)

| Sprint | Tuần | Mục tiêu | Deliverable / Definition of Done |
|---|---|---|---|
| **0. Chuẩn bị** | 1 | Chốt pháp lý + tài khoản | Đăng ký Supabase, TMDB key, Apple Dev ($99), Google Play ($25). Viết 1 trang "Legal & Content Policy" trong app+web. |
| **1. Data** | 2 | Ingest chạy tự động | `anime` ≥ 3.000 bộ, `episodes` có lịch 7 ngày tới, cron 30' chạy xanh 24h liên tục. |
| **2. API** | 3 | Edge Functions + RLS | `/home`, `/anime/{slug}`, `/search` trả < 200ms (p95). Test bằng `curl`, có Postman collection. |
| **3. Flutter shell** | 4 | App chạy được | Home + Detail + Search với dữ liệu thật, dark theme, skeleton loading. Build APK chạy trên máy thật. |
| **4. Auth & Library** | 5 | Tài khoản + watchlist | Đăng nhập email/Google, watchlist 5 trạng thái, RLS đã test (user A không thấy data user B). |
| **5. Schedule & Push** | 6 | ⭐ "Tập mới vừa ra" | Lịch tuần + FCM push khi có tập mới cho bộ đang theo dõi. Notification bấm vào mở đúng tập. |
| **6. Deep link** | 7 | Nút Xem hoạt động | ≥ 60% bộ trong catalog có `streaming_links` VN đã verify. Fallback: "Chưa có nền tảng VN" + gợi ý. |
| **7. Offline** | 8 | Chạy mượt không mạng | Drift cache, mở app offline vẫn xem được Library + Detail. |
| **8. Desktop** | 9 | Windows/macOS/Linux | `flutter build windows`, layout responsive ≥ 1024px, `media_kit` player, build release + installer (MSIX). |
| **9. QA & polish** | 10 | Không crash | 0 crash/100 phiên, animation 60fps, a11y (semantic label), i18n vi/en. |
| **10. CI/CD** | 11 | Build tự động | Actions build APK+AAB mỗi tag, ký số, upload artifact. Codemagic cho iOS (free 500 phút/tháng). |
| **11. Store** | 12 | Submit | Screenshot (5 size), mô tả ASO, privacy policy, **data safety form**, ghi rõ app không host video. |
| **12. Beta** | 13 | 50–200 tester | TestFlight + Play Internal + bản Windows trên GitHub Releases. Thu NPS, fix top 10 bug. |
| **13. Launch** | 14 | Public | Release, landing page, đăng r/anime, group FB anime VN, TikTok clip "app xem lịch anime". |

**Ước lượng thực tế:** một người làm 20–25h/tuần → 14 tuần ra **v1 dùng được**. Nếu full-time một mình → 8–9 tuần. Team 2–5 người → 6–7 tuần (mình khuyên **không** chia việc trước sprint 3, vì data pipeline là điểm nghẽn).

---

## 7. Chi phí (thực tế, không tô hồng)

| Khoản | Free tier | Khi nào phải trả |
|---|---|---|
| Supabase | 500MB DB, 1GB file, 50k MAU, 2 project | > 500MB DB (≈ 200k anime + tập, đủ rất lâu) hoặc cần backup/PITR → $25/th |
| GitHub Actions | 2.000 phút/tháng (private) | Cron 30' ≈ 1.440 run × 30s ≈ 720 phút → **vẫn trong free** |
| Cloudflare (CDN/Worker) | 100k req/ngày | Ở mức nhỏ không bao giờ chạm |
| FCM push | Không giới hạn | — |
| TMDB / AniList / Kitsu | Miễn phí | TMDB thương mại lớn cần thoả thuận |
| Firebase (nếu dùng) | Spark free | Sau này Blaze |
| **Apple Developer** | — | **$99/năm (bắt buộc)** |
| **Google Play** | — | **$25 một lần (bắt buộc)** |
| Code signing Windows | — | Chứng chỉ EV ~$200–400/năm (**có thể bỏ**, dùng MSIX unsigned + hướng dẫn "More info → Run anyway") |

**Tổng kết:** hạ tầng **thật sự 0đ**; chi phí duy nhất để lên store là **$124 năm đầu**. Đây là con số bạn cần chuẩn bị, đừng để phát hiện ở tuần 12.

---

## 8. Chất lượng & vận hành (phần khiến nó "chuyên nghiệp")

- **Observability:** Sentry free (5k event/tháng) cho crash; Supabase logs cho API; `ingest_runs` để biết cron có chạy. Bật 1 alert Telegram khi job fail 2 lần liên tiếp.
- **Feature flag:** bảng `app_config` (1 row JSON) → tắt/bật shelf, đổi min version, force update. Không cần build lại app.
- **Versioning API:** prefix `/v1/`, app cũ vẫn chạy khi bạn đổi backend.
- **Analytics:** PostHog free 1M event/tháng. 5 event cốt lõi: `app_open`, `anime_view`, `watch_click` (kèm platform), `alert_enable`, `search`.
- **KPI tuần 1 sau launch:**
  | Chỉ số | Mục tiêu |
  |---|---|
  | D1 retention | ≥ 35% |
  | `watch_click` / `anime_view` | ≥ 40% (nếu thấp: link chưa đủ/không đúng VN) |
  | Thời gian mở app → thấy Home | < 1.2s (cold start 3G) |
  | Crash-free sessions | ≥ 99.5% |
- **Kiểm tra link chết:** job `link_health` mỗi ngày HEAD các `streaming_links`, sai 3 lần → `is_verified = false`. Đây là loại bug người dùng ghét nhất.
- **Test:** unit test cho ingest (map ID, chuẩn hoá season), widget test cho Home/Detail, integration test 1 luồng: mở app → search → detail → bấm xem → quay lại.

---

## 9. Những sai lầm mình đã thấy (đọc để tránh)

1. **Scrape site lậu làm nguồn** → app chết vì domain đổi + bị store gỡ. (Đã giải thích §0.)
2. **Gọi AniList từ app** → 429 sau vài nghìn user, và bạn không cache được gì.
3. **Không lưu `mal_id`/`kitsu_id`** → sau này muốn đổi nguồn phải làm lại từ đầu.
4. **Dùng `title` làm khóa** → "Frieren" vs "Sousou no Frieren" vs "葬送のフリーレン" tạo ra 3 bộ trùng.
5. **Làm player trước làm data** → bạn có player đẹp nhưng catalog 50 bộ → không ai dùng.
6. **Bỏ qua desktop đến cuối** → layout mobile-only phải refactor toàn bộ. Làm responsive từ sprint 3.
7. **Hứa "xem offline tải về"** khi không có license → không thể làm, đừng đưa vào store description.
8. **Không có trang Legal/Content Policy** → reviewer Apple hỏi ngay câu đầu tiên và reject nếu thiếu.

---

## 10. Ghi chú kỹ thuật nâng cao (khi cần)

- **Push trên desktop:** FCM không chính thức cho Windows/Linux. Cách rẻ: dùng `flutter_local_notifications` + polling khi app chạy, hoặc WebSocket tới Supabase Realtime (free). macOS dùng APNs qua `firebase_messaging` (cần cấu hình riêng).
- **Video chính thức nhúng:** YouTube IFrame/`youtube_player_flutter` cho tập do kênh official đăng (Muse VN, Ani-One) — hoàn toàn hợp pháp, có quảng cáo thuộc về họ, và bạn không tốn băng thông.
- **Khi nào cần DRM/HLS riêng:** chỉ khi bạn có license nội dung. Lúc đó: HLS + fMP4, AES-128 (hoặc Widevine/FairPlay), CDN Cloudflare Stream ($5/1000 phút lưu trữ + $1/1000 phút xem) hoặc Bunny.net (~$0.01/GB). Băng thông video 1080p ≈ 2.5GB/giờ xem → 1.000 lượt xem/tháng ≈ $25. **Đây là lý do mô hình "miễn phí + full" không tồn tại về mặt kinh tế, chứ không chỉ pháp lý.**
- **Nếu vẫn muốn có nội dung để host hợp pháp:** public domain (anime pre-1955 rất ít, nhưng có phim hoạt hình cũ, tác phẩm CC như *Big Buck Bunny*, sinh viên làm animation). Cách hay hơn: mở **"Studio mode"** — cho creator anime indie Việt đăng tác phẩm của họ (bạn có license bằng văn bản). Đây là con đường biến dự án thành startup thật.

---

## 11. Việc cần làm ngay tuần này (checklist)

- [ ] Đọc lại §0, tự trả lời: bạn xây **discovery app** (khả thi, 0đ, lên store) hay **streaming app** (cần license)? — Chọn cái đầu.
- [ ] Tạo project Supabase → chạy `db/schema.sql` → kiểm tra 12 bảng + 2 view.
- [ ] Lấy TMDB API key (free, 2 phút) + tạo `.env`.
- [ ] Chạy `python3 anime_api_demo.py lich 24` để thấy dữ liệu thật chảy vào.
- [ ] Viết `ingest/main.py` (bản đầu chỉ cần Job A: schedule → upsert `episodes`).
- [ ] `flutter create --org com.yourname anistream` → chạy trên Android thật trong ngày đầu.
- [ ] Vẽ wireframe 7 màn hình (Figma free) trước khi code UI.

---

### Tóm 1 câu
Xây **AniStream = LiveChart + AniList + Letterboxd cho anime Việt**: catalog đầy đủ và cập nhật tới giờ từ AniList/Kitsu/TMDB, Flutter chạy cả điện thoại và máy tính, deep link sang nền tảng hợp pháp để xem, push khi tập mới ra — **0đ hạ tầng, lên được store, và là nền móng thật nếu sau này bạn ký được license nội dung.**
