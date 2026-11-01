# DECISION — Chốt mô hình (01/11/2026)

**Trạng thái:** ✅ ĐÃ CHỐT · **Người quyết định:** bạn (uỷ quyền cho agent chọn) · **Áp dụng từ:** hôm nay

---

## 1. Quyết định

> # 🅒 Free Legal Streaming (v1) → 🅓 Self-host Media Client (v2)
>
> Tên sản phẩm: **AniStream — Xem anime hợp pháp miễn phí. Và thư viện của riêng bạn.**

Một app Flutter (Android · iOS · Windows · macOS · Linux), backend Supabase, hạ tầng **0đ**.

| Giai đoạn | Thời gian | Nội dung | Mục tiêu đo được |
|---|---|---|---|
| **v1** | Tuần 1–10 | Catalog đầy đủ + lịch phát + push tập mới + **video official phát ngay trong app** (nhúng YouTube IFrame chính thức) + deep link sang nền tảng hợp pháp | 300+ tập phát được trong app, D30 ≥ 15% |
| **v2** | Tuần 11–18 | "Thư viện của tôi": WebDAV / Google Drive / SMB / Jellyfin + phụ đề ASS/SRT + đồng bộ đa thiết bị → **Premium IAP** | ≥ 1% user trả phí |

---

## 2. Vì sao chọn cái này (bám đúng tiêu chí "phù hợp với người dùng")

Người dùng anime Việt muốn 3 thứ, theo đúng thứ tự:
1. **Mở app là xem được ngay** — không phải "bấm Xem rồi bị đá sang app khác"
2. **Miễn phí** — không cần thẻ quốc tế, không bị đòi đăng ký
3. **Biết tập mới ra lúc nào** — và xem được đúng tập đó

🅒 đáp ứng **cả 3**. 🅓 đáp ứng (1)+(2) nhưng chỉ với người đã có file. 🅐 chỉ đáp ứng (3).
→ Với trọng số "phù hợp người dùng", **🅒 thắng rõ**. Điểm tổng của 🅓 cao hơn nhờ *doanh thu* — nhưng bạn nói ưu tiên là **người dùng**, nên mình đặt 🅒 làm v1 và **giữ 🅓 làm v2 để kiếm tiền**. Đây không phải chọn một trong hai, mà là **thứ tự đúng**.

Và 🅒 giải quyết được mâu thuẫn gốc của cả dự án:
- **"Miễn phí"** ✅ — bạn không trả đồng nào cho băng thông hay bản quyền
- **"Đầy đủ + tập mới nhất"** ✅ — catalog 20.000+ bộ từ AniList/Kitsu/TMDB, lịch phát chính xác tới giờ
- **"Xem trong app"** ✅ — video do chủ kênh official đăng công khai, nhúng qua **IFrame Player API chính thức**
- **"Hợp pháp + sống được trên store"** ✅ — không host, không trích xuất stream, không chặn ads

## 3. Phạm vi ĐÓNG BĂNG (không đổi trong 10 tuần)

✅ **Làm:** catalog, tìm kiếm, lịch phát, push, player nhúng official, watchlist, deep link, desktop build
❌ **KHÔNG làm (v1):** upload video, tải offline, comment/review, social feed, đa ngôn ngữ ngoài vi/en, recommendation AI
❌ **KHÔNG BAO GIỜ làm:** scrape/stream nội dung bản quyền không có phép từ bất kỳ site nào

Lý do đóng băng: 90% dự án một người chết vì mở rộng phạm vi giữa đường, không phải vì thiếu tính năng.

## 4. Những gì đã xong trong phiên này

| Hạng mục | Trạng thái | File |
|---|---|---|
| Chấm điểm 5 mô hình, bảng chọn tương tác | ✅ | `chon_mo_hinh.html` (đã verify: tổng trọng số 18 → max 90; D=77, C=71) |
| Schema DB đầy đủ + RLS + view `v_free_catalog` | ✅ | `db/schema.sql` |
| **Ingest worker chạy thật** (3 job) | ✅ | `ingest/` |
| — Job A: lịch phát → `anime` + `episodes` | ✅ test dry-run: 22 tập/26h | `ingest/main.py schedule` |
| — Job B: catalog theo mùa | ✅ test dry-run: 50 bộ | `ingest/main.py catalog` |
| — Job C: **video official → `streaming_links`** | ✅ test: **16/16 video khớp anime** | `ingest/main.py youtube` |
| Cron GitHub Actions | ✅ | `.github/workflows/ingest.yml` |
| **Flutter app v0.1 (slice v1)** | ✅ 18 file · 4.484 dòng | `app/` |
| — 4 tab: Home / Lịch phát / Tìm / Thư viện + Detail + Player | ✅ | `app/lib/features/` |
| — Mock data **thật** (52 anime, 12 bộ có video official) | ✅ | `tools/gen_mock.py` → `app/lib/data/mock_data.dart` |
| — UI Preview duyệt trước khi build | ✅ | `app/UI_PREVIEW.html` |
| **Backend Edge Functions (4 endpoint)** | ✅ typecheck sạch (tsc strict) | `supabase/` |
| — `home` 1 request cho cả trang chủ + lịch 7 ngày | ✅ cache 300s | `supabase/functions/home/` |
| — `search` / `schedule` / `anime` + chống injection sort/ilike | ✅ | `supabase/functions/*/` |
| — DTO khớp 1-1 với `anime.dart` (đã test bằng Node) | ✅ | `supabase/functions/_shared/assemble.ts` |
| — Smoke test 4 endpoint | ✅ | `scripts/test_api.sh` |
| **Push "tập mới vừa ra" (FCM v1)** | ✅ logic đã unit-test 6/6 assert | `supabase/functions/push/` |
| — Chống gửi trùng (`sent_episode_pushes`) + tự dọn token chết | ✅ | `db/schema.sql` |
| — Client: đăng ký thiết bị không cần login + deep link vào đúng tập | ✅ | `app/lib/core/push/push_service.dart` |

**Bằng chứng Job C (dữ liệu thật, chạy hôm nay):**
```
· Muse Việt Nam: 12 video mới      · Ani-One Asia: 12 video mới
· 16 video dùng được → 16/16 khớp được với AniList (0 bộ chưa khớp)
  ep  6  1.00  A Certain Scientific Railgun   → Toaru Kagaku no Railgun
  ep 46  1.00  Fairy Tail                     → FAIRY TAIL
  ep  0  1.00  A Returner's Magic Should be S → Kikansha no Mahou wa Tokubetsu desu
  ep  4  1.00  朱色假面 (phồn thể, qua alias)     → Shuiro no Kamen
  ep 24  1.00  相反的你和我 第二季                   → Seihantai na Kimi to Boku 2nd Season
```

## 5. Việc tiếp theo (thứ tự cố định)

1. ✅ Ingest worker — **xong**
2. ✅ **Flutter scaffold v1** — đã có (Home/Detail/Search/Schedule/Player/Watchlist, chạy bằng mock data thật)
3. ✅ **Edge Functions `/home` `/anime` `/search` `/schedule`** — đã có, chỉ cần deploy + `USE_MOCK=false`
4. ⏭ Auth + watchlist persist (Drift + Supabase Auth; RLS đã sẵn trong schema)
5. ✅ Push FCM tập mới — đã có (cần `flutterfire configure` để chạy thật)
6. Desktop build (media_kit) + submit store

## 6. Điều kiện để quyết định này còn đúng

- Nếu sau 8 tuần mà **số video official khớp < 150 tập** → catalog quá mỏng, phải thêm kênh (Muse Asia, Ani-One China, kênh publisher Nhật) hoặc chuyển trọng tâm sang 🅓.
- Nếu Apple/Google từ chối app vì "nội dung bên thứ ba" → bổ sung trang Legal rõ hơn + chỉ dùng IFrame API (không tự phát HLS) là đủ điều kiện.
- Nếu chi phí vượt 0đ > $5/tháng → xem lại hạ tầng trước khi tăng trưởng.
