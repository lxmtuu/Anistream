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

## 10 job ingest

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
| G | `add --anilist <id>` | **thêm đúng 1 bộ** từ AniList (bộ job khác không gặp) | chạy tay |
| G' | `check` | **kiểm bất biến dữ liệu**, vi phạm cứng → job ĐỎ | hằng ngày |
| H | `reassign` | chuyển link bị gán **sai mùa** sang đúng mùa · `--move-all` dời cả playlist | chạy tay |

`all` = A + B + C + C' + D + D' + E + F + G. (`reassign` chạy tay — xem dưới.)

### Job D: đọc MÙA từ tên bộ (`season_from_title`)

AniList tách mỗi mùa thành entry riêng ("Kusuriya no Hitorigoto 2nd Season"), TMDB
gộp cả series vào một id. `pick_season` cũ chỉ dựa **năm** hoặc **số tập** — với
series mà các mùa giống nhau (12–13 tập) và năm lệch, nó trả `None` → **không lấy
được tập nào**. Đo 02/11/2026: **30 bộ FINISHED đã chiếu xong mà 0 tập**
(`one-punch-man-2`, `mob-psycho-100-ii`, `dandadan-2nd-season`, `ao-no-hako`,
`kusuriya-no-hitorigoto-2nd-season`, …).

Nay `tmdb.season_from_title()` đọc `2nd Season` / `Second Season` (viết bằng chữ)
/ `Season 2` / `Mùa 2` từ
`title_romaji`/`title_english`/`title_native` và truyền xuống `pick_season` như
lựa chọn **đáng tin nhất**. Hai chốt an toàn:

- **không** đọc `Part 2` — đó là phần trong cùng một mùa TMDB, không phải mùa mới;
- tên ghi mùa N mà TMDB **không** có mùa N → trả `None` (không rơi xuống đoán mò,
  tránh gán tập mùa 1 cho entry mùa 2) — **trừ** trường hợp TMDB có entry **riêng
  cho từng mùa** (vd id 220542 = "Apothecary Diaries Season 2" chỉ có Season 1):
  khi đó mùa duy nhất được nhận nếu số tập của nó lệch ≤ 2 so với AniList. Đo
  02/11/2026: 5 bộ FINISHED đã có `tmdb_id` mà vẫn 0 tập vì thiếu luật này;
- tên có `":"` thì **bỏ qua** phần số ở cuối — `Girls und Panzer: Saishuushou 5` là
  phim lẻ phần 5, không phải mùa 5.

Ngoài ra AniList hay dùng **dạng ngắn** cho mùa sau (`One Punch Man 2`,
`Mob Psycho 100 II`, `Karakai Jouzu no Takagi-san 2`). Từ 02/11/2026
`season_from_title` đọc cả số Ả Rập lẫn số La Mã ở **cuối tên**, chỉ nhận 2–9
(số lớn hơn là số trong tên, ví dụ `Mob Psycho 100`).

**Lọc năm trong `match_anime`** (cùng ngày): đây là tầng sâu hơn của cùng lỗi.
AniList ghi **năm của mùa** (`One Punch Man 2` → 2019) còn TMDB ghi **năm mùa 1**
(2015) → lệch 4 năm > `YEAR_TOLERANCE=2` ⇒ loại sạch kết quả ⇒ không có `tmdb_id`
⇒ **25/53 bộ 0 tập chưa từng khớp được TMDB**. Nay nếu tên cho biết mùa ≥ 2 thì
`match_anime` **bỏ lọc năm** (vẫn giữ ngưỡng tên 0.80), bộ không ghi mùa vẫn lọc
năm như cũ.

### Job D — hai lỗi làm job "chạy mà không ghi được gì" (02/11/2026)

Đo trên một lần chạy `tmdb --limit-tmdb 200` (505 giây):

| Hiện tượng | Nguyên nhân | Vá |
|---|---|---|
| 13 bộ báo `patch anime lỗi 409: duplicate key "anime_tmdb_id_key" (Key (tmdb_id)=…)` **và mất luôn danh sách tập** | `anime.tmdb_id` có ràng buộc **UNIQUE**, nhưng TMDB gộp cả series vào 1 id còn AniList tách mỗi mùa 1 entry ⇒ "One-Punch Man" và "One Punch Man 2" **buộc phải** cùng `tmdb_id` | bỏ UNIQUE (`db/migrations/20261102_tmdb_id_khong_duy_nhat.sql`), giữ index thường; lỗi ghi hồ sơ không còn chặn phần tập |
| **56 bộ "không tìm được trên TMDB"** dù TMDB có | TMDB đặt tên series **gộp cả bộ** ("One-Punch Man"), tên AniList của mùa 2 có hậu tố ("One-Punch Man Season 2") ⇒ tìm nguyên chuỗi ra 0 kết quả | `tmdb.base_title()` bỏ hậu tố mùa và **thử lại** với tên gốc |

`base_title` cắt: `… 2nd Season`, `… Season 2`, `… Mùa 2`, `… II`, `… 2` (số cuối).
Không cắt gì thì trả `None` (không đoán: `Naruto` vẫn là `Naruto`).

### Job D — "TMDB nhiều tập hơn AniList" thì cắt phần dư (02/11/2026)

Lần chạy 13:20: **24 bộ được bổ sung · 137 tập**, còn 9 bộ bị bỏ với lý do
`TMDB 37 tập > AniList 25`. Nguyên nhân: TMDB gộp 2 mùa / 2 cour vào **một**
mùa, còn AniList tách entry. Với entry **mùa đầu** thì tập 1..N của TMDB đúng là
tập 1..N của AniList → cắt phần dư là an toàn.

`tmdb.first_season_cut()` chỉ cho phép cắt khi **cả 4 điều** đúng:

1. tên bộ **không** ghi mùa (`hint` = None hoặc 1);
2. `season_no` là mùa **nhỏ nhất** của series TMDB;
3. năm chiếu của mùa đó **trùng** năm AniList;
4. TMDB nhiều hơn **tối đa 2 lần** (2 mùa/2 cour gộp). Nhiều hơn hẳn — `Fool
   Night`: AniList 3 vs TMDB 12 = 4× — là **nghi lấy nhầm series** → vẫn từ chối.

Không thoả điều nào → hành vi cũ: **không ghi** và báo ra danh sách "KHÔNG hợp".

### Job D — TMDB gộp nhiều mùa vào MỘT season → trừ offset (02/11/2026)

`python3 -m ingest.tmdb --slug dandadan-2nd-season` cho thấy job **tìm thấy** TMDB
(240411, điểm 1.000) nhưng bộ vẫn 0 tập: TMDB chỉ có **một** season 24 tập (mùa 1 +
mùa 2 gộp), `pick_season` từ chối vì 12 ≠ 24 — và **không in ra dòng nào**, nên
`check` cũng im lặng.

Nay `tmdb.split_season_offset()` xử lý: TMDB chỉ có 1 mùa **và** số tập của nó
≈ `season_hint × episodes_total` (lệch ≤ 2) → lấy nửa thứ `hint`, **trừ offset**
`(hint−1) × tổng` rồi đánh số lại 1..N (giữ nguyên tên + ngày chiếu thật của TMDB).

Kèm theo: bộ nào không xác định được mùa thì **luôn** được liệt kê (trước đây chỉ
báo khi TMDB có nhiều hơn 1 mùa — đó là lý do ca DAN DA DAN không xuất hiện ở đâu).

### Job D — thử ỨNG VIÊN KẾ TIẾP khi TMDB trả nhiều series (02/11/2026)

`python3 -m ingest.tmdb --slug kusuriya-no-hitorigoto-2nd-season` in ra **hai**
series cùng khớp: `220542 'Dược Sư Tự Sự'` và `333686 '薬屋のひとりごと'`. Job cũ chỉ
thử kết quả điểm cao nhất (220542, chỉ có mùa 1) → không chọn được mùa 2 → bộ **0
tập** dù ứng viên kia có thể có mùa 2.

Nay `tmdb.pick_all()` trả **nhiều** ứng viên đạt ngưỡng (khử trùng theo id, điểm
giảm dần) và `match_anime(row, accept=…)` gọi `accept(ứng_viên)` để biết ứng viên
đó có mùa cần tìm hay không; tối đa 3 ứng viên mỗi chuỗi tìm. Job truyền
`season_for()` (pick_season → split_season_offset) làm `accept`.

### Job D — TMDB dồn nhiều mùa vào 1 season: tách theo NĂM (02/11/2026)

`python3 -m ingest.tmdb --slug kusuriya-no-hitorigoto-2nd-season` in ra:

```
    ✓ 0.800  220542  'Dược Sư Tự Sự' (2023-10-22)
        ↳ mùa 1: 60 tập (2023-10-22)
        ✗ TỪ CHỐI: tên ghi mùa 2 nhưng TMDB chỉ có mùa 1
```

TMDB **dồn mùa 1 (24) + mùa 2 (24) + mùa 3 (12) = 60 tập** vào một season. Luật
`split_season_offset` đòi `60 ≈ 2 × 24` (lệch ≤ 2) nên trượt.

Nay có luật thứ ba, dùng **ngày chiếu** thay vì số học:

1. `tmdb.merged_year_candidate(detail, hint, year, total)` — chỉ khi tên ghi mùa
   ≥ 2, TMDB **đúng một** mùa, và số tập của nó **nhiều hơn hẳn** `total`.
2. `tmdb.episode_rows_by_year(…, year, total)` — lấy các tập có năm chiếu **đúng
   năm của entry AniList**, đánh số lại `1..N`; số tập phải ≈ `total` (lệch ≤ 2),
   nếu không trả rỗng (mùa vắt qua 2 năm 12+12 sẽ bị loại thay vì ghép bừa).

Luật này cũng chạy như **fallback cuối** khi season đã chọn có số tập nhiều hơn hẳn
`episodes_total` mà `first_season_cut` không áp dụng được (tên ghi mùa 2/3). Ca thật
02/11/2026: `yozakura-san-chi-no-daisakusen-2nd-season` (12 tập, năm 2026),
`tougen-anki-nikko-kegon-no-taki-hen` (12 tập, 2026), `petitcure-…-season-3` (27 tập,
2026), `tensei-kizoku-…-2nd-season` (12 tập, 2024) — TMDB trả 24/24/37/12 tập.

`explain` cũng đi qua luật này nên chẩn đoán và job luôn khớp nhau.

### Job D — `delete` trả 204 nhưng khớp 0 dòng (02/11/2026)

Lần chạy 17:42 in `dọn 12 tập trùng` nhưng DB **vẫn còn** 12 dòng trùng
(`tensei-…-3rd-season` giữ 24 dòng). Nguyên nhân: `requests.delete` với
`Prefer: return=minimal` trả **204 kể cả khi không khớp dòng nào**, nên
`DB.delete` luôn trả 1 = "thành công" và lọc theo cột `number` không ăn cũng
không ai biết.

Nay:
* `DB.delete` dùng `Prefer: return=representation` và **trả số dòng thật bị xoá**
  (0 nếu không khớp) — mọi chỗ gọi đều cộng đúng con số này;
* dọn tập trùng xoá theo **khoá chính `id`** (không phụ thuộc cột `number`);
* nếu xoá 0 dòng thì in cảnh báo ngay tại chỗ, không im lặng.

### Job D — "đã có tập" không có nghĩa là tập ĐÚNG (02/11/2026)

Lần chạy 17:34 xử lý `tensei-…-3rd-season` nhưng không ghi gì: bộ còn 24 dòng,
dòng đầu là 2026 (trùng năm của entry) ⇒ `wrong_start` sai, và `have` khác rỗng
⇒ bỏ qua. Bản vá xoá-trùng ở PR #27 vì thế **không có cơ hội chạy**.

Nay view `anime_thieu_tap` định nghĩa lại "danh sách tập SAI":
`không có tập nào` **hoặc** `có 2 tập trùng NGÀY CHIẾU`. Bộ nào trong view được
gắn cờ khi đưa vào hàng đợi và **luôn được xử lý lại**, kể cả khi đã có tập.

Lưu ý: trùng ngày chiếu *có thể* là double-episode thật (đo 02/11/2026:
`tensei-goblin-dakedo-shitsumon-aru` tập 5/6 khác giờ — giữ nguyên). Việc xử lý
lại là vô hại: chỉ xoá khi số tập **vượt** số vừa ghi *và* trùng ngày chiếu.

### Job D — đánh số lại thì phải xoá bản TRÙNG (02/11/2026)

Lần chạy 17:21 dọn đúng 24 tập cũ nhưng `tensei-kizoku-…-3rd-season` còn **24
dòng**: 1..12 (đúng) và 25..36 (**cùng ngày chiếu** — dư từ lần đánh số trước).
Dọn theo "ngoài khoảng chiếu" không bắt được vì chúng nằm TRONG khoảng.

Nay `_prune_duplicate_numbers` xoá tập có **số > số tập vừa ghi** *và* **ngày
chiếu trùng** một tập vừa ghi. Tập tương lai khác ngày chiếu được giữ nguyên.

### Job D — `delete` phải nhận toán tử PostgREST như `patch` (02/11/2026)

Lần chạy 16:44 đã lấp đúng 63 tập (petitcure 27/27, tensei 2nd 12/12, yozakura
12/12) nhưng mỗi bộ in:

```
! …: RuntimeError: delete episodes lỗi 400: {"code":"22007", … "invalid input
   syntax for type timestamp with time zone: "lt.…
```

Vì `patch()` đã hỗ trợ toán tử (`lt.`/`gt.`) còn `delete()` thì chỉ ghép `eq.`
→ gửi `airing_at=eq.lt.2026-07-06`, Postgres hiểu `lt.…` là giá trị timestamp.
Hai hàm lệch nhau vì sửa một chỗ.

Nay dùng chung `_FILTER_OPS` cho cả hai, có test gọi `requests.delete` giả và
kiểm tham số gửi đi (`tests/test_db_filters.py`). Bước dọn cũng được bọc
try/except: lỗi dọn **không** làm mất tập vừa ghi, nhưng vẫn in cảnh báo.

### Job D — `gql()` đã bóc `data`, đừng bóc lần nữa (02/11/2026)

Lần chạy 16:26 vẫn 0 tập. `airing_window` viết `data["data"]["Media"]` trong khi
`anilist.gql()` **đã trả** `payload["data"]` ⇒ luôn nhận `{}` — không lỗi, không
cảnh báo, mọi luật cắt-theo-khoảng-chiếu im lặng không chạy (job chạy 220s rồi
báo xong).

Nay `airing_window` đọc thẳng `data["Media"]`, có test riêng
(`tests/test_anilist_window.py`) dùng `gql` giả trả đúng hình dạng thật. Thêm
nữa: khi không lấy được `startDate`, job **in cảnh báo** kèm slug thay vì lặng
lẽ bỏ qua.

### Job D — bộ "0 tập mãi" và lỗi cột thiếu (02/11/2026)

Lần chạy `--refresh` 16:09 in "thành công" mà **không ghi gì**. Hai lỗi:

1. **`TMDB_COLS` thiếu `anilist_id`** ⇒ `_airing_window()` luôn trả `{}` ⇒ mọi
   luật cắt-theo-khoảng-chiếu im lặng không chạy. Test cũ vẫn xanh vì chúng
   patch thẳng `_airing_window`. Nay test patch `anilist.airing_window` (đi qua
   helper thật) và có test chặn cứng: `anilist_id` phải nằm trong `TMDB_COLS`.
2. **Bộ 0 tập không nằm trong hàng đợi nào**: chế độ thường chỉ lấy bộ thiếu
   `title_vi/synopsis_vi/episodes_total`, chế độ `--refresh` chỉ lấy `RELEASING`.
   Bộ đã có tên VI + tổng tập nhưng bảng `episodes` trống thì **không bao giờ**
   được thử lại.

Nay có **view `anime_thieu_tap`** (`db/migrations/20261102_view_anime_thieu_tap.sql`):
`episodes_total > 0`, không phải `NOT_YET_RELEASED`, và chưa có tập nào. Job đọc
view này ở **cả hai chế độ**, hoãn 1 ngày (thay vì 7) — bộ nào lấp được tập thì
tự rời view nên không tốn thời gian lâu dài. Nếu view chưa được áp, job in cảnh
báo kèm đường dẫn migration (không im lặng).

### Job D — cắt tập theo KHOẢNG CHIẾU của AniList (02/11/2026)

Lần chạy 15:46 vẫn bỏ 3 bộ. Truy ra hai sự thật **khác nhau**, và cả hai đều chỉ
giải được bằng ngày chiếu của chính entry AniList:

| bộ | TMDB | AniList |
|---|---|---|
| `yozakura-…-2nd-season` | 216467 **mùa 2 = 24 tập** (12/04/2026 →) | tách "2nd Season" 12 tập + **"2nd Season Part 2"** 12 tập |
| `tensei-kizoku-…-3rd-season` | 237150 **một season 36 tập** (07/04/2024 →) | mùa 3 chiếu từ 10/2026 |

Luật theo NĂM không tách được (cả hai cour đều 2026; còn tensei thì tập mùa 1+2
nằm lẫn trong "mùa 3"). Vì vậy job **hỏi AniList `startDate`/`endDate`** của
đúng entry đó (`anilist.airing_window`) rồi cắt
(`tmdb.episode_rows_in_window`):

* có `endDate` → lấy tập trong khoảng, số tập phải ≈ `episodes_total` (lệch ≤ 2);
* chưa có `endDate` (đang chiếu) → lấy các tập **đầu tiên** kể từ `startDate`;
* không có `startDate` → **trả rỗng**, không ghi gì.

Thêm hai bảo vệ:

* **Phát hiện dữ liệu cũ sai**: tập đã có mà bắt đầu ở năm khác năm của entry
  (tensei-3rd: tập từ 2024 trong một bộ 2026) thì **vẫn xử lý lại**, không coi
  là "đã có tập".
* **Dọn tập sai**: sau khi ghi theo khoảng chiếu, xoá tập có ngày chiếu nằm
  ngoài khoảng đó (chừa 90 ngày mỗi đầu để không xoá nhầm mùa đông chiếu từ
  tháng 12 năm trước). `db.delete` nay nhận toán tử PostgREST (`lt.`/`gt.`).

### Job D — `seasons[].episode_count` của TMDB hay LỆCH (02/11/2026)

Lần chạy 15:30 còn 3 bộ bị bỏ. Một trong số đó lộ ra lỗi này: detail TMDB báo
`episode_count = 12` nhưng `GET /tv/{id}/season/1` trả **24 tập**. Luật "gộp mùa"
(`24 ≈ 2 × 12`) dùng số trong detail nên bị bỏ qua.

Nay trong nhánh "không hợp", job **thử lại** `split_season_offset(...)` với
`season_count = n_season` (số tập THẬT đọc được), rồi mới đến tách-theo-năm.

`explain` cũng in thêm **phân bố ngày chiếu** để biết vì sao tách theo năm trượt:

```
        ↳ mùa 1: 24 tập (2024-04-07)
        ↳ ngày chiếu: 2025: 24 tập
```

(0 tập ở năm 2026 ⇒ năm của entry AniList không có tập nào — dữ liệu TMDB khác
giả định, không phải lỗi code.)

### Job D — không quét lại bộ vừa hỏi TMDB (02/11/2026)

Một lần chạy quét đủ **161 bộ trong 792 giây** và ghi được **0 bản ghi**. Nguyên
nhân: điều kiện chọn bộ là `or=(title_vi.is.null, synopsis_vi.is.null,
episodes_total.is.null)` — bộ mà TMDB **không có** (44 bộ) hoặc **không có bản dịch
vi** (13 bộ) luôn thoả điều kiện đó, nên lần nào cũng bị chọn lại.

Nay có cột `anime.tmdb_checked_at` (migration
`db/migrations/20261102_tmdb_checked_at.sql`) ghi "lần cuối đã hỏi TMDB":

| Trạng thái | Hỏi lại sau |
|---|---|
| `RELEASING` (đang chiếu) | **1 ngày** — cần bắt tập mới |
| còn lại | **7 ngày** |

Bộ chưa từng hỏi (`NULL`) thì luôn được xử lý. Lọc ở Python (không nhồi vào query
string) vì PostgREST không nhận hai tham số `or=` cùng lúc.

### Job D — soi một bộ: `python3 -m ingest.tmdb`

Khi log ghi "không tìm được trên TMDB" mà bạn tin là TMDB có, chạy:

```bash
python3 -m ingest.tmdb --slug the-ramparts-of-ice-season-2
python3 -m ingest.tmdb --title "Dandadan 2nd Season" --year 2025 --total 12
```

Nó in **mọi** chuỗi đã tìm, số kết quả, và từng kết quả kèm `✓/✗` + điểm; với
ứng viên đạt ngưỡng thì in tiếp **từng mùa** (số tập + ngày chiếu) và kết luận
`✓ CHỌN mùa N` / `✗ TỪ CHỐI: <lý do>`. Đủ để biết bị loại vì lệch tên, lệch năm,
TMDB không có mùa đó, hay số tập không khớp.

### Job H — `reassign`: link bị gán sai mùa

Muse đánh số tập **tiếp nối qua các mùa**: FAIRY TAIL đăng liên tục tập 1–277,
nhưng AniList tách "FAIRY TAIL" (175) và "FAIRY TAIL (2014)" (102). Ingest gán cả
277 video vào entry mùa 1 → 102 link vượt tổng bị chốt chặn loại ⇒ **102 video
không ai xem được** (mùa 1 hiện 66 tập trong khi Muse có 277).

Có **hai** kiểu lệch, job xử lý cả hai:

| kiểu | ví dụ thật (02/11/2026) | cách sửa |
|---|---|---|
| link thuộc **mùa sau** | `shangri-la-frontier` giữ tập 26, 41 (bộ chỉ 25) | chuyển sang `shangri-la-frontier-2nd-season`, số − 25 |
| số tập **tiếp nối nhưng entry đã đúng mùa** | `seihantai-na-kimi-to-boku-2nd-season` (13 tập) giữ tập 24 | dời số **trong cùng entry**: 24 − 12 = 12 |

Luật dời số chỉ chạy khi tìm được entry mùa trước **theo slug** (`…-2nd-season`
→ `…`), mọi số sau khi dời nằm trong `[1, episodes_total]`, và **không trùng** số
tập đang có (trùng = bộ bị khai thiếu tổng, không phải đánh số tiếp nối → bỏ).

```bash
python3 -m ingest.reassign                 # chỉ in kế hoạch
python3 -m ingest.reassign --apply --only-exact   # an toàn nhất
python3 -m ingest.reassign --apply         # gồm cả ca "probable"
```

Quy tắc rất bảo thủ: offset = `episodes_total` của bộ cũ; đích phải là mùa sau
theo slug và **chưa có link/tập nào**; mọi link phải ánh xạ vào `[1, tổng của
đích]`; `exact` khi dãy số liên tục và khớp đúng tổng của đích. Ca không có entry
mùa sau thì **để nguyên và báo**, còn hơn gán bừa sang bộ khác.

### Job H' — `--move-all`: cả playlist thuộc về bộ KHÁC

Ca HUNTER×HUNTER (02/11/2026): Muse VN đăng bản **2011 — 148 tập** (AniList
11061), nhưng DB chỉ có bản **1999 — 62 tập** (AniList 136). Hai bản là quan hệ
**Alternative** (không phải Sequel) nên `catalog`/`schedule`/`seasons` **không bao
giờ** thêm được bản 2011. Kết quả: 148 link nằm ở entry 1999, 86 link vượt tổng
bị loại → video nằm im.

Muse đánh số theo đúng bộ 2011, nên dời sang entry 2011 **không đổi số**:

```bash
python3 -m ingest.main add --anilist 11061          # in ra slug của bộ 2011
python3 -m ingest.reassign --move-all --from hunter-hunter \
        --to-anilist 11061                          # xem trước
python3 -m ingest.reassign --move-all --from hunter-hunter \
        --to-anilist 11061 --apply
python3 -m ingest.main check
```

### Job H'' — `--move-over`: chỉ phần VƯỢT TỔNG là bộ khác (OVA/OAD)

Ca `uq-holder-mahou-sensei-negima-2` (02/11/2026): TV **12 tập**, nhưng Muse đánh
số tiếp 13–15 cho **3 OAD** ("Amor Primus", "Eternal First Kiss", "Karin-senpai no
Ienai Himitsu"). AniList để OAD ở entry riêng "UQ HOLDER! OVA" (AniList 98999,
3 tập) ⇒ 3 video vượt tổng, không ai xem được.

```bash
python3 -m ingest.main add --anilist 98999        # "UQ HOLDER! OVA", 3 tập
python3 -m ingest.reassign --move-over --from uq-holder-mahou-sensei-negima-2 \
        --to-anilist 98999 --apply
```

Ở đây **có** đánh số lại: `offset = episodes_total` của nguồn (13−12 = 1 … 15−12 = 3).

Kiểm **hết** rồi mới ghi (sai một điều là bỏ toàn bộ): cả hai bộ phải tồn tại;
đích có `episodes_total` ≥ số tập lớn nhất của nguồn; đích **chưa có link** (không
trộn hai nguồn); nguồn phải có ít nhất 1 link. Sau khi dời, tập của nguồn do
**chính link** sinh ra (không ngày chiếu, không tên) mà không còn video nào sẽ bị
xoá — nếu không trang chi tiết vẫn hiện "62 tập" trống.

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

### Chẩn đoán mạng: `bash scripts/check_net.sh`

Khi một job cứ `ConnectTimeout` mà job khác vẫn chạy được (ca thật 02/11/2026:
Jikan chết 39/39 nhưng TMDB vẫn lấy được 63/126 `tmdb_id`), đừng đoán. Script đo
từng tầng rồi in kết luận:

```
── DNS ──
  Jikan/MAL (job F)   ✓ 135.181.39.91
── Kết nối HTTPS (IPv4 / IPv6) ──
  Jikan/MAL (job F)   ❌ v4=000  v6=000 → KHÔNG kết nối được (firewall/ISP)
  TMDB (job D)        ⚠ v4=401 (OK)  v6=000 → CHỈ IPv6 lỗi
```

Đọc kết quả:
- **DNS trống** → DNS nhà mạng chặn: đổi sang `1.1.1.1` / `8.8.8.8`, hoặc
  `nslookup api.jikan.moe 1.1.1.1` để xác nhận.
- **`v4` OK, `v6` 000** → chỉ IPv6 hỏng: `ingest/net.py` tự ép IPv4, không cần làm gì.
- **`v4` và `v6` đều 000** → firewall/ISP chặn host đó. Ba cách: thêm
  `HTTPS_PROXY=http://host:port` vào `.env` · chạy job trên GitHub Actions ·
  dùng nguồn khác cho job đó.

Lưu ý: `401`, `404`, `4xx` đều là **đã tới được server** — script chỉ coi `000`
là chặn. Vì vậy `curl` thiếu API key vẫn được tính là OK.

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
