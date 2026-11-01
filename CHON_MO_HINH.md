# Xem lại mô hình & 5 lựa chọn — AniStream (anime app, Flutter, 0đ)

**Ngày:** 01/11/2026 · Ràng buộc của bạn: Flutter (mobile + desktop) · muốn là **startup thật** · ngân sách hạ tầng **0đ** · muốn **xem đầy đủ anime, cập nhật tập mới nhất, miễn phí**

---

## PHẦN 1 — Xem lại mô hình mình đã đề xuất (tự phê bình)

Mô hình ở `LO_TRINH_ANIME_APP.md` là **Discovery + Deep-link** (giống LiveChart/AniList). Nó đúng về pháp lý và đúng về chi phí, nhưng **nếu bạn muốn làm startup thì nó có 5 điểm yếu chí mạng** — mình phải nói rõ để bạn không mất 3 tháng:

| # | Điểm yếu | Vì sao chết |
|---|---|---|
| 1 | **Không có "wow"** | Người dùng mở app, bấm Xem → **bị đá sang app khác**. Cảm giác: "vậy tôi cần app này làm gì?" Tỉ lệ giữ chân D30 thường < 10%. |
| 2 | **Không có hào cạnh tranh** | AniList, MyAnimeList, LiveChart, AniChart đã có, miễn phí, 10 năm dữ liệu. Bạn chỉ thêm "tiếng Việt + link VN" — bản copy được trong 1 tháng. |
| 3 | **Không kiếm được tiền** | Không ai trả tiền cho "lịch phát + link". Ads trên app 20k MAU ở VN ≈ **$30–80/tháng**. Affiliate Crunchyroll ở VN gần như không có. |
| 4 | **Sai thị trường** | Ở VN, đa số người xem anime **không trả tiền cho nền tảng hợp pháp** (catalog VN mỏng, cần thẻ quốc tế). Bạn đang làm sản phẩm cho nhóm "đã trả tiền" — nhóm nhỏ nhất. |
| 5 | **Phụ thuộc 100% API người khác** | AniList đổi rate limit / Kitsu chết → app bạn trắng bảng. Bạn không sở hữu tài sản nào ngoài vài bảng cache. |

**Kết luận:** mô hình cũ = **dự án portfolio tốt, startup tồi.** Nó là *lớp 1* của sản phẩm, không phải cả sản phẩm.

**Điều mình giữ nguyên từ bản cũ (vẫn đúng 100%):**
- Vẫn **không** host/stream nội dung lậu — không phải vì đạo đức suông, mà vì nó **phá huỷ khả năng tồn tại của startup** (store gỡ, DMCA, không monetize được).
- Vẫn dùng AniList/Kitsu/TMDB làm nguồn metadata, vẫn Flutter 1 codebase, vẫn Supabase free, vẫn `db/schema.sql` dùng lại được cho **mọi** lựa chọn dưới đây.

---

## PHẦN 2 — 5 lựa chọn (đã cân nhắc cả cái khó nói)

### 🅐 Discovery + Deep-link — *"LiveChart tiếng Việt"*
Catalog đầy đủ, lịch phát tới giờ, push tập mới, bấm Xem → mở Netflix/Crunchyroll/Bilibili.
- **Pháp lý:** 🟢 an toàn tuyệt đối · **Hạ tầng:** 0đ · **MVP:** 4–6 tuần
- **Doanh thu:** rất thấp (ads + affiliate) · **Cold start:** dễ (SEO, group anime)
- **Hào:** ✗ · **Rủi ro:** người dùng cài rồi xoá
- **Phù hợp:** portfolio, đồ án, side-project học kiến trúc. **Không** phải startup.

### 🅑 Tracker + Social — *"Letterboxd của anime Việt"*
Watchlist, tiến độ, chấm điểm, review, list, feed bạn bè, share card đẹp.
- **Pháp lý:** 🟢 (metadata + nội dung do user tạo) · **Hạ tầng:** 0đ · **MVP:** 6–8 tuần
- **Doanh thu:** premium (theme, thống kê nâng cao, không ads) + ads
- **Cold start:** 🔴 rất khó — **cần mạng xã hội mới có giá trị**, mà mạng xã hội cần user. Classic chicken-and-egg.
- **Hào:** ✓ mạnh *nếu* sống sót (dữ liệu chấm điểm + bạn bè) · **Rủi ro:** 90% app social chết vì không đủ user
- **Phù hợp:** người có kênh TikTok/Facebook anime > 50k follow sẵn. Không có audience → đừng chọn.

### 🅒 Free Legal Streaming — *"Netflix anime miễn phí, hợp pháp"* ⭐
**Đây là lựa chọn duy nhất vừa hợp pháp, vừa 0đ, vừa XEM ĐƯỢC TRONG APP.**
- Nguồn video: **nhúng YouTube official** (Muse VN, Ani-One Asia, kênh publisher) qua *IFrame Player API chính thức* + catalog **public domain** + trailer chính thức.
- Catalog: vài trăm → 1.500+ tập xem được ngay trong app, **0đ băng thông** (YouTube chịu), **0đ bản quyền** (chủ kênh đã trả).
- Pháp lý: 🟢 hợp pháp **với điều kiện** dùng đúng IFrame player của YouTube, **không** trích xuất stream (`youtube_explode`, `yt-dlp`-style = vi phạm ToS YouTube + bản quyền), không chặn quảng cáo của họ.
- **MVP:** 6–8 tuần · **Cold start:** 🟡 trung bình ("xem anime free hợp pháp, không quảng cáo casino" là thông điệp bán được ở VN)
- **Hào:** ✓ "danh mục anime free chính thống đã tuyển chọn + vietsub" — đối thủ không copy nhanh vì phải tuyển chọn thủ công
- **Doanh thu:** ads của YouTube (họ giữ) + **premium riêng** (đồng bộ, không quảng cáo của *bạn*, tải danh sách offline, theme) + affiliate
- **Rủi ro:** catalog mỏng hơn phim lậu; một số video tắt embed; phải kiểm tra `embeddable` định kỳ

### 🅓 Self-host Media Client — *"Trình phát cho thư viện anime CỦA BẠN"*
App kết nối **file/ thư mục của chính người dùng**: WebDAV, Google Drive, OneDrive, SMB, Emby/Jellyfin server. App lo metadata (AniList), phụ đề, đồng bộ, UI đẹp. Giống **Infuse / VidHub / nPlayer** — các app này **bán được tiền thật**.
- Pháp lý: 🟢 hoàn toàn (như VLC — bạn chỉ là *cái đầu đĩa*, nội dung do user tự cung cấp)
- **Hạ tầng: 0đ vĩnh viễn** (bạn không host 1 byte video nào — điểm này cực quan trọng)
- **Doanh thu:** 💰 **cao nhất trong 5 lựa chọn** — IAP một lần $4.99–9.99 hoặc $1.99/tháng. Infuse có hàng triệu user trả phí → đã chứng minh.
- **Cold start:** 🟡 người dùng "có file sẵn" đã quen dùng app nước ngoài → cần lý do đổi (tiếng Việt, metadata AniList, nhẹ, miễn phí tier)
- **Hào:** ✓ kỹ thuật thật (decode, phụ đề ASS, đồng bộ vị trí, mạng nội bộ) — khó copy hơn app catalog
- **Rủi ro:** Apple soi kỹ app dạng này (phải không có nguồn phim sẵn trong app); cần subtitle engine tốt (đây là 60% giá trị)
- **Phù hợp:** ⭐ nếu bạn muốn **có doanh thu** mà vẫn 0đ hạ tầng.

### 🅔 Indie Studio Platform — *"Vimeo cho anime Việt"*
Creator anime Việt tự đăng tác phẩm, bạn có **license bằng văn bản** → bạn thật sự sở hữu quyền phát.
- Pháp lý: 🟢 · **Hào:** ✓✓ mạnh nhất (bạn sở hữu nội dung độc quyền) · **Scale:** ✓ cao nhất
- **Hạ tầng:** 🔴 **phá vỡ ngân sách 0đ** — video storage + CDN tính theo GB (1.000 giờ xem 1080p ≈ $25/tháng)
- **Cold start:** 🔴 rất khó — phải thuyết phục creator trước khi có viewer
- **Doanh thu:** subscription + tip + rev share
- **Phù hợp:** khi bạn có quan hệ với cộng đồng animator VN. **Không** phải v1.

---

## PHẦN 3 — Bảng chấm điểm (thang 1–5, có trọng số theo mục tiêu "startup 0đ")

| Tiêu chí (trọng số) | 🅐 Discovery | 🅑 Social | 🅒 Free Legal Stream | 🅓 Self-host | 🅔 Studio |
|---|---|---|---|---|---|
| Hợp pháp (×3) | 5 | 5 | 4 | 5 | 5 |
| Chi phí 0đ bền vững (×3) | 5 | 5 | 5 | 5 | 1 |
| **Xem được trong app** (×3) | 1 | 1 | **5** | 5 | 4 |
| Doanh thu khả thi (×2) | 1 | 2 | 3 | **5** | 4 |
| Hào cạnh tranh (×2) | 1 | 4 | 3 | 4 | 5 |
| Dễ cold-start ở VN (×2) | 4 | 1 | 4 | 3 | 2 |
| Thời gian ra MVP (×1) | 5 | 3 | 3 | 2 | 1 |
| Rủi ro store/policy (×2) | 5 | 5 | 3 | 3 | 4 |
| **TỔNG (max 90)** | **63** | **62** | **74** | **77** | **63** |

Hai lựa chọn dẫn đầu: **🅓 Self-host (77)** và **🅒 Free legal stream (74)**. Chúng **bổ trợ nhau**, không loại nhau.

---

## PHẦN 4 — Khuyến nghị của mình: chọn **🅒 trước, 🅓 sau** (một sản phẩm, 2 lớp)

### Sản phẩm: **AniStream — "Xem anime hợp pháp, miễn phí. Và thư viện của riêng bạn."**

**Lớp 1 (v1, tuần 1–10): Kho phim free hợp pháp + lịch + push**
- Home: shelf "Xem ngay miễn phí" (video YouTube official nhúng trong app), "Tập mới hôm nay", "Mùa này", "Top rating"
- Schedule + push "Tập 6 vừa ra"
- Bấm xem → **player trong app** (IFrame chính thức) → đây là điểm ăn tiền so với LiveChart/AniList
- Bộ nào không có bản free official → nút "Xem trên Netflix/Crunchyroll/Bilibili" (deep link)
- **Lợi ích:** người dùng thấy app "xem được thật", 0đ hạ tầng, không rủi ro pháp lý

**Lớp 2 (v2, tuần 11–18): "Thư viện của tôi" (🅓)**
- Kết nối WebDAV / Google Drive / SMB / Jellyfin → phát file của chính người dùng
- Metadata tự nhận từ AniList, phụ đề ASS/SRT, resume, đồng bộ giữa điện thoại ↔ máy tính
- **Đây là tính năng bán tiền:** Premium $3.99/tháng hoặc $24.99 lifetime (đồng bộ đa thiết bị, phụ đề nâng cao, theme)
- **Lợi ích:** biến power-user thành khách trả tiền, và tạo hào kỹ thuật thật

### Vì sao thứ tự này?
1. **v1 chứng minh "xem được"** → giữ chân, có review 5 sao, có traffic → dễ lên store.
2. **v2 kiếm tiền** từ nhóm user khó tính nhất (đã có file sẵn) → họ sẵn sàng trả tiền cho *chất lượng phát*, không phải cho nội dung.
3. Cả 2 lớp **không cần 1 đồng băng thông video nào** → ngân sách 0đ vẫn đúng.
4. Nếu sau này bạn ký được license (🅔), bạn đã có app + user + player sẵn → chỉ cần thêm nguồn.

### Nếu bạn muốn nhanh hơn (chỉ 1 lớp): chọn **🅓 Self-host**
Lý do: doanh thu rõ nhất, hào kỹ thuật thật, không lo catalog. Nhược điểm: khó marketing hơn ở VN (phải giải thích "app này để xem file của bạn"), và cần subtitle engine tốt.

### Nếu mục tiêu chỉ là portfolio/đồ án: chọn **🅐**
Ít rủi ro nhất, 4–6 tuần, đủ đẹp để trình bày. Đừng kỳ vọng user.

### ❌ Đừng chọn
- **Stream phim lậu** (chết ở store/DMCA/Điều 225 BLHS — đã phân tích kỹ ở file lộ trình).
- **🅑 Social làm v1** khi chưa có audience — chicken-and-egg giết 90% dự án.
- **🅔 Studio** với 0đ — băng thông sẽ ăn hết tiền trước khi có doanh thu.

---

## PHẦN 5 — Kế hoạch 90 ngày cho khuyến nghị (🅒 + 🅓)

| Tuần | Việc | Kết quả kiểm chứng được |
|---|---|---|
| 1 | Supabase + `db/schema.sql`, ingest Job A/B/C, TMDB `vi-VN` | `anime` ≥ 3.000 bộ, lịch 7 ngày tới đầy đủ |
| 2 | **Tuyển chọn 300–800 tập free official** (Muse VN, Ani-One, publisher), lưu `streaming_links(kind='free_legal')` + kiểm tra `embeddable` tự động | Bảng `v_free_catalog` có ≥ 300 tập phát được |
| 3 | Edge Functions: `/home`, `/anime/{slug}`, `/search`, `/schedule` | p95 < 200ms |
| 4 | Flutter: Home + Detail + Search + Schedule (dữ liệu thật, Drift offline) | APK chạy trên máy thật |
| 5 | **Player IFrame chính thức** + resume + "Continue watching" | Bấm xem là phát được trong app |
| 6 | Auth + watchlist + push FCM tập mới | Notification bấm → mở đúng tập |
| 7 | Trang Legal/Content Policy (**nói rõ: nội dung do chủ kênh YouTube cung cấp, phát qua player chính thức**) + giới thiệu nguồn | Reviewer Apple/Google không có lý do từ chối |
| 8 | Desktop build (Windows/macOS) + `media_kit` + responsive | Bản Windows trên GitHub Releases |
| 9 | QA, Sentry, PostHog, feature flag, link health job | Crash-free ≥ 99.5% |
| 10 | Submit store + beta 100 người | Có app trên TestFlight/Play Internal |
| 11–12 | **v2 bắt đầu:** WebDAV/Drive connector + subtitle engine + sync | Phát được file của chính bạn từ Drive |
| 13–14 | Premium IAP + paywall + thử nghiệm giá | ≥ 1% user trả tiền (đo thật) |

---

## PHẦN 6 — Con số thực tế (để bạn không ảo tưởng)

| Kịch bản | 12 tháng | Doanh thu/tháng (ước) |
|---|---|---|
| App VN, 0 marketing | 3.000–10.000 install | $0–20 (ads) |
| Có TikTok/SEO tốt | 30.000–80.000 install, 5.000 MAU | $80–250 (ads) + $50–150 (premium 1–2%) |
| 🅓 Self-host tốt, có review EN | 20.000 user, 2% trả phí | **$300–800** (IAP/subscription) |
| Muốn VC-scale | Phải mở SEA/global hoặc B2B | — |

**Nói thẳng:** một mình + 0đ + thị trường VN → mục tiêu thực tế là **indie app có lãi nhỏ (vài trăm đô/tháng)**, không phải unicorn. Nếu bạn cần "startup gọi vốn", mô hình phải là 🅔 (sở hữu nội dung) và cần vốn — hai điều kiện đó không thoả với 0đ ngay từ đầu. Biết trước để chọn đúng kỳ vọng.

---

## PHẦN 7 — Quyết định trong 1 phút

Trả lời 2 câu này là chốt được:

1. **Bạn muốn người dùng bấm ▶ và video phát ngay trong app?**
   - Có → **🅒 (+🅓)**. Không → 🅐.
2. **Bạn cần app có doanh thu, hay chỉ cần đẹp để học/portfolio?**
   - Doanh thu → **🅓** (hoặc 🅒+🅓). Portfolio → 🅐.

Mặc định mình khuyên: **🅒 v1 → 🅓 v2**, dùng lại toàn bộ `db/schema.sql`, `anime_sources.md`, ingest pipeline đã có.
