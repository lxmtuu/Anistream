#!/usr/bin/env python3
"""
main.py — Worker ingest cho AniStream (mô hình 🅒 Free Legal Streaming).

Lệnh:
  python3 -m ingest.main schedule  [--hours 26]   # A. lịch phát → anime + episodes  (chạy mỗi 30')
  python3 -m ingest.main catalog   [--pages 2]    # B. catalog theo mùa → anime      (chạy mỗi đêm)
  python3 -m ingest.main youtube   [--limit 25]   # C. video official → streaming_links (mỗi 6h)
  python3 -m ingest.main tmdb                    # D. tên/tóm tắt tiếng Việt + tập (cần TMDB_API_KEY)
  python3 -m ingest.main all                      # chạy cả 3

Cờ chung:
  --dry-run        không ghi DB, chỉ in kết quả (dùng để test)
  --no-embed-check bỏ qua kiểm tra oEmbed (nhanh hơn, cho lần chạy đầu)

Ví dụ test không cần Supabase:
  python3 -m ingest.main youtube --dry-run --limit 12
"""
import argparse
import datetime as dt
import re
import sys
import time

from . import anilist, config, db as dbmod, jikan, match, qa, tmdb, youtube


# ─────────────────────────────────────────────── helpers
def _season_now():
    today = dt.date.today()
    return anilist.season_of(today.month), today.year


def _upsert_media(DB, medias):
    """Upsert danh sách media AniList → bảng anime, trả map anilist_id → db id."""
    rows = [anilist.to_anime_row(m) for m in medias if m and m.get("id")]
    # bỏ trùng trong cùng 1 batch (AniList có thể trả 2 lần nếu 2 tập cùng bộ)
    seen, uniq = set(), []
    for r in rows:
        if r["anilist_id"] in seen:
            continue
        seen.add(r["anilist_id"])
        uniq.append(r)

    written = DB.upsert("anime", uniq, on_conflict="anilist_id")
    id_map = {}
    for w in written:
        if isinstance(w, dict) and w.get("anilist_id"):
            id_map[w["anilist_id"]] = w.get("id")
    return uniq, id_map


# ─────────────────────────────────────────────── Job A
def job_schedule(DB, hours: int = 26):
    print(f"\n▶ Job A — lịch phát {hours}h tới")
    now = int(time.time())
    schedules = anilist.airing_schedules(now, now + hours * 3600, per_page=50)
    print(f"  · {len(schedules)} tập từ AniList")

    medias = [s["media"] for s in schedules if s.get("media")]
    rows, id_map = _upsert_media(DB, medias)

    eps = []
    for s in schedules:
        m = s.get("media") or {}
        aid = id_map.get(m.get("id"))
        if not aid:
            continue          # dry-run: không có id thật → bỏ qua episodes
        eps.append(anilist.to_episode_row(aid, s["episode"], s["airingAt"]))
    if DB.dry:
        print(f"  [dry-run] sẽ upsert {len(eps) or len(schedules)} episodes "
              f"(cần Supabase để có anime_id thật)")
        for s in schedules[:8]:
            t = dt.datetime.fromtimestamp(s["airingAt"]).strftime("%d/%m %H:%M")
            print(f"    {t}  ep{str(s['episode']).rjust(3)}  "
                  f"{(s['media'].get('title') or {}).get('romaji', '')[:52]}")
    else:
        DB.upsert("episodes", eps, on_conflict="anime_id,number")

    DB.log_ingest("anilist", "schedule", True, len(rows) + len(eps))
    print(f"  ✓ {len(rows)} anime · {len(eps)} episodes")
    return len(rows) + len(eps)


# ─────────────────────────────────────────────── Job B
def job_catalog(DB, pages: int = 2):
    season, year = _season_now()
    print(f"\n▶ Job B — catalog mùa {season} {year}")
    medias = []
    for p in range(1, pages + 1):
        got = anilist.seasonal(season, year, page=p, per_page=50)
        print(f"  · trang {p}: {len(got)} bộ")
        medias.extend(got)
        if len(got) < 50:
            break
        time.sleep(1.2)          # lịch sự với API
    rows, _ = _upsert_media(DB, medias)
    DB.log_ingest("anilist", "catalog", True, len(rows))
    print(f"  ✓ {len(rows)} anime")
    return len(rows)


# ─────────────────────────────────────────────── Job C
def _link_rows(DB, videos, cache, verbose=True):
    """Ghép tên → anime rồi tạo rows `streaming_links`. Trả (matched, links, unmatched)."""
    import re
    import unicodedata

    def exact_title(value):
        value = unicodedata.normalize("NFKC", value or "").casefold()
        return re.sub(r"[^\w]+", " ", value).strip()

    matched, unmatched, need_review = [], {}, {}
    for i, v in enumerate(videos, 1):
        media, confidence, how = match.resolve(
            v["series"], cache, want_series=(v["episode"] > 0))
        # Fuzzy partial matches can confuse entirely different series or seasons.
        # Only editorial aliases or exact full titles are published automatically.
        title = (media or {}).get("title") or {}
        names = [title.get(k) for k in ("romaji", "english", "native")]
        alias_exists = match.alias_key(v["series"]) in match._ALIASES
        exact = exact_title(v["series"]) in {exact_title(n) for n in names if n}
        if not media or not (alias_exists or exact):
            unmatched.setdefault(v["series"], 0)
            unmatched[v["series"]] += 1
            if verbose and i % 50 == 0:
                print(f"    … ghép tên {i}/{len(videos)}")
            continue

        # Chốt chặn: KHÔNG bao giờ ghi link có số tập vượt tổng số tập của bộ.
        # Ca thật: Muse đăng "Hunter x Hunter (2011)" 148 tập nhưng AniList entry
        # khớp tên là bản 1999 (62 tập) → 86 link bị gán sai bộ và hiện lẫn trong
        # danh sách tập của bộ kia. Thà bỏ và báo ra để biết còn hơn ghi bừa.
        total = media.get("episodes")
        if isinstance(total, int) and total > 0 and v["episode"] > total:
            key = f'{v["series"]} (tập {v["episode"]} > {total} tập)'
            need_review[key] = need_review.get(key, 0) + 1
            continue

        matched.append((v, media, confidence, how))

    if not matched:
        return [], [], unmatched, need_review

    # upsert anime trước để có id
    rows, id_map = _upsert_media(DB, [m for _, m, _, _ in matched])

    links, seen_url = [], set()
    for v, media, conf, how in matched:
        # dry-run chưa có id thật → dùng anilist_id làm chỗ giữ để đếm cho đúng
        aid = id_map.get(media["id"]) or (media["id"] if DB.dry else None)
        if not aid or v["url"] in seen_url:
            continue
        seen_url.add(v["url"])
        links.append({
            "anime_id": aid,
            "episode_number": v["episode"],        # 0 = cả bộ
            "platform": "youtube",
            "region": v["region"],
            "url": v["url"],
            "kind": "free_legal",
            "is_verified": True,
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            # Truy ngược: link này đến từ tiêu đề YouTube nào? Cần khi số tập bị
            # parse sai (vd bản gộp "Tập 01-24" từng bị gán thành tập 1).
            "source_title": (v.get("raw_title") or "")[:300] or None,
        })
    return rows, links, unmatched, need_review


def job_youtube(DB, limit: int = 25, check_embed: bool = True,
                deep: bool = False, max_per_channel: int = 5000,
                use_cache: bool = True, only_channel: str = ""):
    """Video official → streaming_links.

    Khác bản cũ ở 3 điểm (đều là lỗi thật gặp khi backfill 5.560 video):
      1. GHI DB THEO TỪNG KÊNH — bản cũ gom cả 2 kênh rồi ghi một lần, nên mất
         mạng/Ctrl+C ở khâu ghép tên là mất trắng, `ingest_runs` không có dấu vết.
      2. CACHE GHÉP TÊN RA ĐĨA (`.cache/match_cache.json`) — chạy lại thì bỏ qua
         tên đã biết, không search lại 4 request/tên.
      3. LỖI ĐƯỢC GHI LẠI: kênh nào hỏng thì các kênh khác vẫn ghi, và
         `ingest_runs` ghi ok=false kèm lý do.
    """
    mode = "BACKFILL toàn bộ kênh (YouTube API)" if deep else "RSS (video mới nhất)"
    print(f"\n▶ Job C — video official → streaming_links  [{mode}]")

    cache = match.load_disk_cache() if use_cache else {}
    if use_cache and cache:
        known = sum(1 for v in cache.values() if v)
        print(f"  · cache ghép tên: {len(cache)} tên "
              f"({known} đã khớp, {len(cache) - known} đã biết là không khớp)")

    channels = [c for c in youtube.enabled_channels()
                if not only_channel or c["key"] == only_channel]
    if not channels:
        raise RuntimeError(f"không có kênh nào khớp --channel={only_channel}")

    total_rows = total_links = 0
    all_unmatched, all_review = {}, {}
    failures = []

    for n, ch in enumerate(channels, 1):
        print(f"\n  ── Kênh {n}/{len(channels)}: {ch['name']} ──")
        try:
            videos = youtube.collect_channel(
                ch, limit_per_channel=limit, check_embed=check_embed,
                deep=deep, max_per_channel=max_per_channel)
        except Exception as e:
            print(f"  ✗ không lấy được video {ch['name']}: {type(e).__name__}: {e}")
            failures.append(f"{ch['name']}: {e}")
            continue

        print(f"  · {len(videos)} video dùng được")
        if not videos:
            continue

        try:
            rows, links, unmatched, need_review = _link_rows(DB, videos, cache)
        except Exception as e:
            print(f"  ✗ lỗi khi ghép tên/ghi {ch['name']}: {type(e).__name__}: {e}")
            failures.append(f"{ch['name']}: {e}")
            if use_cache:
                match.save_disk_cache(cache)
            continue

        for name, cnt in unmatched.items():
            all_unmatched[name] = all_unmatched.get(name, 0) + cnt
        for name, cnt in need_review.items():
            all_review[name] = all_review.get(name, 0) + cnt

        print(f"  · khớp được {sum(1 for _ in links)}/{len(videos)} video "
              f"({len(unmatched)} tên series chưa khớp)")

        if DB.dry:
            print(f"  [dry-run] sẽ upsert {len(links)} streaming_links")
        elif links:
            DB.upsert("streaming_links", links,
                      on_conflict="anime_id,platform,region,episode_number",
                      fallback_per_row=True)
            print(f"  ✓ đã ghi {len(links)} link / {len(rows)} anime (kênh {ch['name']})")

        total_rows += len(rows)
        total_links += len(links)

        if use_cache:
            path = match.save_disk_cache(cache)
            print(f"  · đã lưu cache {len(cache)} tên → {path}")

    if all_unmatched:
        print(f"\n  ⚠ {len(all_unmatched)} tên series chưa khớp "
              f"(thêm vào ingest/aliases.json rồi chạy lại):")
        for name, cnt in sorted(all_unmatched.items(), key=lambda x: -x[1])[:15]:
            print(f"      - {name}  ({cnt} video)")

    if all_review:
        print(f"\n  ⚠ {len(all_review)} series có tập VƯỢT tổng số tập của bộ đang ghép "
              f"→ KHÔNG ghi (nghi sai bộ/mùa):")
        for name, cnt in sorted(all_review.items(), key=lambda x: -x[1])[:15]:
            print(f"      - {name}  ({cnt} video)")

    # Link đã ghi xong → biến chúng thành tập hiển thị được (bộ 0 tập vì không
    # khớp TMDB sẽ có danh sách tập thật). KHÔNG cộng vào `total_links`: số tập
    # không phải số link, cộng vào sẽ làm `ingest_runs.rows` của job C sai.
    job_link_episodes(DB)

    ok = not failures
    DB.log_ingest("youtube", "links", ok, total_links,
                  error="; ".join(failures)[:500])
    print(f"  ✓ tổng: {total_rows} anime · {total_links} links")
    if failures:
        # NỔ, không im lặng: cron "xanh" mà không lấy được video nào là loại lỗi
        # tệ nhất — các kênh khác đã ghi xong nên dữ liệu không mất, nhưng lần
        # chạy này PHẢI đỏ để người vận hành biết mà sửa.
        print(f"\n  ✗ {len(failures)} kênh lỗi (các kênh khác vẫn đã ghi):")
        for f in failures:
            print(f"      - {f}")
        raise RuntimeError(f"{len(failures)}/{len(channels)} kênh không lấy được video: "
                           + "; ".join(failures)[:300])
    return total_links


# ─────────────────────────────────────────────── Job C'
def job_link_episodes(DB, limit: int = 20000):
    """Tạo dòng `episodes` từ chính các link official đã có.

    Vì sao cần: trước đây danh sách tập CHỈ đến từ TMDB (job D). Bộ không khớp
    TMDB (hoặc thiếu TMDB_API_KEY) thì có link mà bảng tập TRỐNG → trang chi tiết
    hiện "0 tập" trong khi vẫn có 12 video. Đo 2026-11-01: 23/27 bộ có link đều
    rơi vào cảnh này (`dandadan` 12 link/0 tập, `noblesse` 13/0, `bang-dream-*` 13/0).

    Nguyên tắc:
      · chỉ tạo tập cho số tập CÓ video official thật (khớp yêu cầu "số tập hiển
        thị phải khớp nội dung video");
      · KHÔNG tạo tập vượt `episodes_total` — chốt chặn "không link nào vượt tổng
        số tập của bộ"; phần vượt được đếm và in ra để người vận hành xử lý;
      · không ghi đè tập đã có (title/airing_at của TMDB/Jikan giữ nguyên).
    """
    print("\n▶ Job C' — tạo tập từ link official (bộ có video nhưng 0 tập)")
    if DB.dry:
        print("  [dry-run] cần Supabase để đọc link → bỏ qua")
        return 0

    # select_all: PostgREST cắt ở 1000 dòng, xin limit=20000 cũng chỉ được 1000.
    links = DB.select_all(
        "streaming_links",
        "select=anime_id,episode_number&kind=eq.free_legal&episode_number=gt.0",
    )
    if not links:
        print("  · không có link nào có số tập")
        return 0

    totals = {r["id"]: r.get("episodes_total")
              for r in DB.select_all("anime", "select=id,episodes_total")}
    slugs = {r["id"]: r.get("slug")
             for r in DB.select_all("anime", "select=id,slug")}
    existing = {r["anime_id"] for r in
                DB.select_all("episodes", "select=anime_id")}

    by_anime = {}
    for l in links:
        if l.get("anime_id") and l.get("episode_number"):
            by_anime.setdefault(l["anime_id"], set()).add(int(l["episode_number"]))

    rows, overflow = [], []
    for aid, numbers in by_anime.items():
        if aid in existing:
            continue                      # đã có danh sách tập → không đụng
        total = totals.get(aid)
        keep = sorted(numbers)
        if isinstance(total, int) and total > 0:
            keep = [n for n in sorted(numbers) if n <= total]
            over = [n for n in sorted(numbers) if n > total]
            if over:
                overflow.append((slugs.get(aid) or aid, total, len(over)))
        if not keep:
            continue
        for n in keep:
            rows.append({"anime_id": aid, "number": n, "title": None,
                         "airing_at": None})

    if rows:
        DB.upsert("episodes", rows, on_conflict="anime_id,number")
    filled = len({r["anime_id"] for r in rows})

    if overflow:
        print(f"  ⚠ {len(overflow)} bộ có link VƯỢT tập tối đa → không tạo tập:")
        for slug, total, cnt in sorted(overflow, key=lambda x: -x[2])[:10]:
            print(f"      - {slug}: {cnt} link > {total} tập (nghi link thuộc mùa khác)")

    DB.log_ingest("links", "episodes", True, len(rows))
    print(f"  ✓ {filled} bộ · {len(rows)} tập tạo từ link")
    return len(rows)


# ─────────────────────────────────────────────── Job D
TMDB_COLS = ("id, slug, title_romaji, title_english, title_native, title_vi, "
             "synopsis_vi, year, episodes_total, tmdb_id, tmdb_checked_at")


def _mark_checked(DB, row: dict) -> None:
    """Ghi mốc "đã hỏi TMDB về bộ này" để lần sau không quét lại ngay.

    Không làm chết job: đây chỉ là tối ưu thời gian, lỗi thì bỏ qua.
    """
    try:
        DB.patch("anime", {"id": row["id"]},
                 {"tmdb_checked_at": tmdb.now_iso()})
    except Exception:                  # noqa: BLE001
        pass


def _airing_window(row: dict) -> dict:
    """Khoảng chiếu của entry AniList ({"from","to"}) — {} nếu không có.

    Chỉ dùng cho ca TMDB lệch mùa. Lỗi mạng KHÔNG được làm chết job, nhưng phải
    báo ra (trả {"error": …}) để không ai tưởng là dữ liệu đã khớp.
    """
    aid = row.get("anilist_id")
    if not aid:
        return {}
    try:
        return anilist.airing_window(int(aid))
    except Exception as e:                        # noqa: BLE001
        return {"error": str(e)[:90]}


def _prune_episodes_outside(DB, row: dict, win: dict) -> int:
    """Xoá tập có ngày chiếu nằm NGOÀI khoảng chiếu AniList (dữ liệu gộp mùa cũ).

    Ca thật 02/11/2026: `tensei-kizoku-…-3rd-season` (2026) bị ghi 36 tập của
    TMDB season 1 gộp (07/04/2024 →), tức tập của mùa 1+2 nằm trong mùa 3. Khi
    đã xác định đúng khoảng chiếu thì tập cũ nằm ngoài khoảng đó là SAI.

    Chừa 90 ngày mỗi đầu để không xoá nhầm ca mùa đông chiếu từ tháng 12 năm
    trước. Xoá theo tập đã ghi (không đụng bảng khác).
    """
    start, end = win.get("from"), win.get("to")
    removed = 0
    if isinstance(start, dt.date):
        lo = (start - dt.timedelta(days=90)).isoformat()
        removed += DB.delete("episodes",
                             {"anime_id": row["id"], "airing_at": f"lt.{lo}"})
    if isinstance(end, dt.date):
        hi = (end + dt.timedelta(days=90)).isoformat()
        removed += DB.delete("episodes",
                             {"anime_id": row["id"], "airing_at": f"gt.{hi}"})
    return removed


def job_tmdb(DB, limit: int = 60, with_episodes: bool = True,
             refresh: bool = False):
    """Bổ sung tiếng Việt (title_vi, synopsis_vi) + danh sách tập từ TMDB.

    Hai chế độ:

    · mặc định (`refresh=False`) — **bổ sung** bộ còn thiếu dữ liệu. Điều kiện cũ
      `or=(title_vi.is.null, …)` khiến bộ nào đã đủ 3 trường thì KHÔNG BAO GIỜ được
      ghé lại, và danh sách tập chỉ lấy khi bảng trống → tập mới của bộ đang chiếu
      không bao giờ vào. Đó là lý do "cập nhật thường xuyên" không hoạt động.
    · `refresh=True` — **làm mới** mọi bộ đang chiếu (`status = RELEASING`): upsert
      các tập MỚI của mùa đang phát (không chỉ khi bảng trống).
    """
    mode = "làm mới bộ đang chiếu" if refresh else "bổ sung bộ còn thiếu"
    print(f"\n▶ Job D — TMDB: tên + tóm tắt tiếng Việt, danh sách tập  [{mode}]")
    if not tmdb.is_configured():
        raise RuntimeError(
            "Thiếu TMDB_API_KEY → không bổ sung được tiếng Việt.\n"
            "  Lấy key miễn phí: https://www.themoviedb.org/settings/api\n"
            "  Thêm vào .env:  TMDB_API_KEY=xxxxxxxx"
        )

    # Ưu tiên bộ phổ biến (người dùng thấy trước).
    #
    # Bỏ qua bộ VỪA hỏi TMDB gần đây: bộ mà TMDB không có (44 bộ) hoặc không có
    # bản dịch vi (13 bộ) luôn thoả điều kiện `title_vi.is.null` nên trước đây bị
    # quét lại ở MỌI lần chạy. Đo 02/11/2026: 792 giây cho 0 bản ghi.
    # RELEASING hỏi lại sau 1 ngày (cần bắt tập mới), còn lại 7 ngày.
    stale_after = tmdb.STALE_DAYS_RELEASING if refresh else tmdb.STALE_DAYS
    cutoff = tmdb.stale_cutoff(stale_after)
    # Lọc "đã hỏi gần đây" ở Python chứ không nhồi vào query string: PostgREST
    # không nhận hai tham số `or=` cùng lúc, còn logic tree `and=(or(…),or(…))`
    # rất dễ sai cú pháp và làm job chết trên máy người chạy.
    over = int(limit) * 4
    if refresh:
        cand = DB.select(
            "anime",
            f"select={TMDB_COLS}&status=eq.RELEASING"
            f"&order=popularity.desc&limit={over}",
        )
        print(f"  · {len(cand)} anime đang chiếu · làm mới những bộ chưa hỏi "
              f"trong {stale_after} ngày")
    else:
        cand = DB.select(
            "anime",
            f"select={TMDB_COLS}"
            f"&or=(title_vi.is.null,synopsis_vi.is.null,episodes_total.is.null)"
            f"&order=popularity.desc&limit={over}",
        )
        print(f"  · {len(cand)} anime cần làm giàu · bỏ qua bộ đã hỏi TMDB "
              f"trong {stale_after} ngày")
    rows = [r for r in cand if tmdb.is_stale(r.get("tmdb_checked_at"), cutoff)]
    rows = rows[:int(limit)]
    print(f"  · {len(rows)} anime sẽ xử lý lần này")

    patched = eps_written = new_episodes = 0
    no_match, no_vi, multi_season, implausible = [], [], [], []
    patch_errors: list = []
    for i, row in enumerate(rows, 1):
        label = (row.get("title_english") or row.get("title_romaji") or row.get("slug"))[:46]
        try:
            # Gợi ý mùa từ CHÍNH TÊN bộ: "… 2nd Season" → mùa 2. Không có bước
            # này thì bộ nhiều mùa giống nhau (12–13 tập/mùa) bị bỏ trống danh
            # sách tập dù TMDB có đủ (đo 02/11/2026: 30 bộ FINISHED 0 tập).
            hint_season = tmdb.season_from_title(
                row.get("title_romaji"), row.get("title_english"),
                row.get("title_native"))
            details: dict = {}                 # tmdb_id → detail, tránh gọi 2 lần

            def detail_of(tv_id: int) -> dict:
                if tv_id not in details:
                    details[tv_id] = tmdb.fetch_detail(tv_id)
                return details[tv_id]

            def season_for(tv_id: int):
                """(mùa, lý do, split) cho 1 ứng viên TMDB; mùa None = không dùng được."""
                det = detail_of(tv_id)
                no, why_ = tmdb.pick_season(
                    det, row.get("year"), row.get("episodes_total"), hint_season)
                # TMDB gộp nhiều mùa AniList vào MỘT season (DAN DA DAN: 1 mùa
                # 24 tập = mùa 1 + mùa 2). `pick_season` từ chối ⇒ trước đây bộ
                # LẶNG LẼ không có tập nào. Nay lấy nửa thứ `hint` rồi trừ offset.
                sp = None
                if no is None:
                    sp = tmdb.split_season_offset(
                        det, hint_season, row.get("episodes_total"))
                    if sp:
                        no = sp["season"]
                        why_ = (f"gộp mùa — trừ {sp['offset']} tập "
                                f"(TMDB {sp['count']} tập)")
                # TMDB dồn NHIỀU mùa vào 1 season với số tập lẻ (60 = 24+24+12):
                # tách theo NĂM chiếu của entry AniList (xem
                # `episode_rows_by_year`). Cần ngày chiếu nên quyết định ở dưới.
                if no is None:
                    yno = tmdb.merged_year_candidate(
                        det, hint_season, row.get("year"),
                        row.get("episodes_total"))
                    if yno is not None:
                        no = yno
                        why_ = (f"dồn mùa — tách theo năm {row.get('year')} "
                                f"(TMDB {yno} mùa gộp)")
                        sp = {"season": yno, "offset": 0, "by_year": True}
                return no, why_, sp

            # TMDB có thể trả NHIỀU series cho cùng một bộ (đo 02/11/2026:
            # "The Apothecary Diaries" → 220542 và 333686). Chỉ thử ứng viên
            # điểm cao nhất thì bộ bị bỏ trắng dù ứng viên khác có đủ mùa.
            last_why = ""
            best, score, how = tmdb.match_anime(
                row, accept=lambda r: season_for(r["id"])[0] is not None)
            if not best:
                # không ứng viên nào có mùa cần tìm → lấy ứng viên đầu để báo lý do
                first, _, how2 = tmdb.match_anime(row)
                if not first:
                    no_match.append(f"{label}  ({how2})")
                    _mark_checked(DB, row)      # đã hỏi TMDB, đừng hỏi lại ngay
                    continue
                _, last_why, _ = season_for(first["id"])
                multi_season.append(f"{label}  ({last_why})")
                best, score, how = first, 0.0, how2

            detail = detail_of(best["id"])
            title_vi, overview_vi = tmdb.extract_vietnamese(detail)
            season_no, why, split = season_for(best["id"])
            matched = season_no is not None

            hint = None
            if matched:
                hint = next(
                    (s["count"] for s in tmdb.season_candidates(detail)
                     if s["number"] == season_no), None)

            patch = tmdb.build_anime_patch(row, detail, title_vi, overview_vi,
                                           matched, episodes_total_hint=hint)
            if patch:
                # Lỗi ghi hồ sơ KHÔNG được chặn phần danh sách tập phía dưới:
                # trước đây một 409 (tmdb_id trùng) làm cả bộ bị bỏ, nên 13 bộ
                # vừa có tmdb_id lại vừa 0 tập (đo 02/11/2026).
                try:
                    DB.patch("anime", {"id": row["id"]}, patch)
                    patched += 1
                except Exception as e:            # noqa: BLE001 — cần biết mọi kiểu
                    patch_errors.append(f"{label}  ({str(e)[:90]})")
                chi_tiet = ", ".join(
                    f"{k}={v}" for k, v in patch.items() if k in ("title_vi", "episodes_total")
                ) or ", ".join(sorted(patch))
                print(f"  [{i}/{len(rows)}] {label[:40]:<40} tmdb={best['id']} "
                      f"{score:.2f} ← {chi_tiet}")
            elif not title_vi and not overview_vi:
                no_vi.append(label)

            # Danh sách tập: khi đã xác định được mùa VÀ row chưa có tập nào.
            # (Trước đây còn đòi `episodes_total is null` → bộ nào AniList đã biết
            #  tổng số tập thì KHÔNG BAO GIỜ có danh sách tập. Đó là lỗi.)
            if with_episodes and matched:
                if refresh:
                    # Đang chiếu → mỗi lần chạy phải lấy lại danh sách để bắt tập mới
                    have = DB.select(
                        "episodes", f"select=number&anime_id=eq.{row['id']}&limit=600")
                    existing = {e.get("number") for e in have}
                else:
                    have = DB.select(
                        "episodes",
                        f"select=number,airing_at&anime_id=eq.{row['id']}"
                        "&order=airing_at.asc&limit=1")
                    existing = set()
                # Tập đã có nhưng bắt đầu ở NĂM KHÁC năm của entry ⇒ dữ liệu cũ
                # lấy từ season gộp (tensei-…-3rd-season: 2026 nhưng tập từ
                # 2024). Vẫn phải xử lý lại, không được coi là "đã có tập".
                first_have = str((have[0].get("airing_at") if have else "") or "")[:4]
                wrong_start = (
                    first_have.isdigit() and isinstance(row.get("year"), int)
                    and int(first_have) != int(row["year"]))
                if refresh or not have or wrong_start:
                    season = tmdb.fetch_season(best["id"], season_no)
                    n_season = len([e for e in (season.get("episodes") or [])
                                    if isinstance(e.get("episode_number"), int)])
                    # Season TMDB "trông như gộp nhiều mùa": số tập khác tổng
                    # của AniList, hoặc season bắt đầu ở năm KHÁC entry. Khi đó
                    # khoảng chiếu của chính entry AniList là ranh giới đúng.
                    first_year = tmdb.season_first_year(season)
                    merged_look = bool(
                        row.get("episodes_total")
                        and isinstance(first_year, int)
                        and isinstance(row.get("year"), int)
                        and (n_season != row["episodes_total"]
                             or first_year != int(row["year"])))
                    if merged_look:
                        win = _airing_window(row)
                        eps_w = tmdb.episode_rows_in_window(
                            row["id"], season, win.get("from"), win.get("to"),
                            row.get("episodes_total")) if win.get("from") else []
                        if eps_w:
                            DB.upsert("episodes", eps_w,
                                      on_conflict="anime_id,number")
                            eps_written += len(eps_w)
                            n_pruned = _prune_episodes_outside(DB, row, win)
                            print(f"      + {len(eps_w)} tập (theo khoảng chiếu "
                                  f"{win['from']} → {win.get('to') or '…'}, "
                                  f"TMDB {n_season} tập"
                                  + (f", dọn {n_pruned} tập cũ sai" if n_pruned else "")
                                  + ")")
                            _mark_checked(DB, row)
                            continue
                    if (split or {}).get("by_year"):
                        # TMDB dồn nhiều mùa → lấy tập có NGÀY CHIẾU đúng năm
                        # của entry AniList, đánh số lại 1..N. Tự kiểm số lượng
                        # (lệch > 2 thì trả rỗng → không ghi gì).
                        eps = tmdb.episode_rows_by_year(
                            row["id"], season, row.get("year") or 0,
                            row.get("episodes_total") or 0)
                        if eps:
                            DB.upsert("episodes", eps,
                                      on_conflict="anime_id,number")
                            eps_written += len(eps)
                            print(f"      + {len(eps)} tập (dồn mùa, tách theo "
                                  f"năm {row.get('year')} trong {n_season} tập TMDB)")
                        else:
                            win = _airing_window(row)
                            eps = tmdb.episode_rows_in_window(
                                row["id"], season, win.get("from"), win.get("to"),
                                row.get("episodes_total")) if win.get("from") else []
                            if eps:
                                DB.upsert("episodes", eps,
                                          on_conflict="anime_id,number")
                                eps_written += len(eps)
                                print(f"      + {len(eps)} tập (theo khoảng chiếu "
                                      f"{win['from']} → {win.get('to') or '…'}, "
                                      f"TMDB {n_season} tập)")
                            else:
                                why = ("không đọc được ngày chiếu AniList: "
                                       f"{win['error']}" if win.get("error") else
                                       f"năm {row.get('year')} không khớp "
                                       f"{row.get('episodes_total')} tập")
                                implausible.append(f"{label}  (dồn mùa nhưng {why})")
                        _mark_checked(DB, row)
                        continue

                    plausible = tmdb.episodes_plausible(
                        row.get("episodes_total"), n_season)
                    max_number = None
                    if split:
                        # đã trừ offset khi đánh số → chỉ giữ [1, tổng]
                        max_number = row.get("episodes_total")
                        plausible = True
                    elif not plausible:
                        # TMDB gộp nhiều mùa/nhiều cour vào MỘT mùa → nhiều tập hơn
                        # AniList. Nếu ĐÂY là mùa đầu thì tập 1..N vẫn đúng, cắt
                        # phần dư (9 bộ rơi vào cảnh này ngày 02/11/2026).
                        max_number = tmdb.first_season_cut(
                            detail, season_no, hint_season, row.get("year"),
                            row.get("episodes_total"), season_count=n_season)
                        if not max_number:
                            # Ngày chiếu của CHÍNH entry AniList là ranh giới đúng
                            # nhất khi TMDB gộp nhiều cour vào một season.
                            win = _airing_window(row)
                            eps_win = tmdb.episode_rows_in_window(
                                row["id"], season, win.get("from"), win.get("to"),
                                row.get("episodes_total")) if win.get("from") else []
                            if eps_win:
                                DB.upsert("episodes", eps_win,
                                          on_conflict="anime_id,number")
                                eps_written += len(eps_win)
                                print(f"      + {len(eps_win)} tập (theo khoảng chiếu "
                                      f"{win['from']} → {win.get('to') or '…'}, "
                                      f"TMDB {n_season} tập)")
                                _mark_checked(DB, row)
                                continue
                        if not max_number:
                            # `seasons[].episode_count` trong detail TMDB hay LỆCH
                            # so với danh sách tập thật (báo 12 nhưng trả 24) →
                            # `merged_year_candidate` đã bỏ qua ca này. Thử lại
                            # luật "gộp mùa" với SỐ TẬP THẬT đọc được.
                            # Ca thật: yozakura-…-2nd-season (12 tập) — 24 = 2×12.
                            sp2 = tmdb.split_season_offset(
                                detail, hint_season, row.get("episodes_total"),
                                season_count=n_season)
                            if sp2:
                                eps_split = tmdb.episode_rows(
                                    row["id"], season, matched,
                                    max_number=row.get("episodes_total"),
                                    offset=sp2["offset"])
                                if eps_split:
                                    DB.upsert("episodes", eps_split,
                                              on_conflict="anime_id,number")
                                    eps_written += len(eps_split)
                                    print(f"      + {len(eps_split)} tập (gộp mùa "
                                          f"— trừ {sp2['offset']}, TMDB "
                                          f"{n_season} tập)")
                                    _mark_checked(DB, row)
                                    continue
                            # Luật cuối: cùng một season nhưng TMDB chứa NHIỀU mùa
                            # liền nhau (24 = 12 + 12, 37 = 25 + 12). Tách theo
                            # NĂM chiếu của entry AniList; hàm tự kiểm số lượng
                            # (lệch > 2 → rỗng) nên không ghép bừa.
                            eps_by_year = tmdb.episode_rows_by_year(
                                row["id"], season, row.get("year") or 0,
                                row.get("episodes_total") or 0)
                            if eps_by_year:
                                DB.upsert("episodes", eps_by_year,
                                          on_conflict="anime_id,number")
                                eps_written += len(eps_by_year)
                                print(f"      + {len(eps_by_year)} tập (tách theo "
                                      f"năm {row.get('year')} trong {n_season} "
                                      f"tập TMDB)")
                                _mark_checked(DB, row)
                                continue
                            implausible.append(
                                f"{label}  (TMDB {n_season} tập > AniList "
                                f"{row.get('episodes_total')}, năm "
                                f"{row.get('year')} không tách được)")
                    if plausible or max_number:
                        if max_number:
                            print(f"      · TMDB có {n_season} tập, cắt còn "
                                  f"{max_number} (mùa đầu của series)")
                        eps = tmdb.episode_rows(
                            row["id"], season, matched, max_number=max_number,
                            offset=(split or {}).get("offset", 0))
                        if eps:
                            DB.upsert("episodes", eps, on_conflict="anime_id,number")
                            eps_written += len(eps)
                            new_eps = [e["number"] for e in eps
                                       if e["number"] not in existing]
                            if refresh:
                                if new_eps:
                                    print(f"      + {len(new_eps)} tập MỚI "
                                          f"(mùa {season_no}, {why}): "
                                          f"tập {', '.join(map(str, new_eps[:8]))}"
                                          + ("…" if len(new_eps) > 8 else ""))
                                    new_episodes += len(new_eps)
                            else:
                                print(f"      + {len(eps)} tập (mùa {season_no}, {why})")
            _mark_checked(DB, row)          # xong bộ này → ghi mốc "đã hỏi"
        except tmdb.TmdbError:
            raise                      # lỗi cấu hình/mạng → nổ ngay, không nuốt
        except Exception as e:         # lỗi 1 bộ không được làm chết cả job
            print(f"  ! {label}: {type(e).__name__}: {str(e)[:140]}")

    if no_match:
        print(f"  ⚠ {len(no_match)} anime không tìm được trên TMDB (bỏ qua, không đoán bừa):")
        for n in no_match[:10]:
            print(f"      - {n}")
    if no_vi:
        print(f"  ⚠ {len(no_vi)} anime có trên TMDB nhưng CHƯA có bản dịch tiếng Việt")
    if multi_season:
        print(f"  ⚠ {len(multi_season)} anime KHÔNG xác định được mùa "
              f"→ chỉ lấy tên/tóm tắt, không lấy tập:")
        for n in multi_season[:8]:
            print(f"      - {n}")
    if implausible:
        print(f"  ⚠ {len(implausible)} anime có danh sách tập TMDB KHÔNG hợp với AniList "
              f"→ không ghi (tránh gán sai):")
        for n in implausible[:8]:
            print(f"      - {n}")
    if patch_errors:
        print(f"  ⚠ {len(patch_errors)} anime KHÔNG ghi được hồ sơ (vẫn thử lấy tập):")
        for n in patch_errors[:8]:
            print(f"      - {n}")

    job_name = "refresh" if refresh else "enrich"
    DB.log_ingest("tmdb", job_name, True, patched + eps_written)
    if refresh:
        print(f"  ✓ {patched} anime được cập nhật · {new_episodes} tập MỚI "
              f"({eps_written} tập đã đồng bộ)")
    else:
        print(f"  ✓ {patched} anime được bổ sung · {eps_written} tập")
    return patched + eps_written


# ─────────────────────────────────────────────── Job E
_LATER_SEASON = re.compile(
    r"(season\s*\d|\d(st|nd|rd|th)\s*season|final season|part\s*\d|"
    r"m[ùu]a\s*\d|cour\s*\d)",
    re.IGNORECASE,
)


def looks_later_season(row) -> bool:
    """Tên bộ cho thấy đây là mùa 2/3/4… (hoặc cour/part sau)."""
    text = " ".join(str(row.get(k) or "") for k in ("slug", "title_romaji"))
    return bool(_LATER_SEASON.search(text))


def job_seasons(DB, limit: int = 80):
    """Phát hiện mùa bị THIẾU qua quan hệ SEQUEL / PREQUEL của AniList.

    AniList tách mỗi mùa thành 1 entry riêng, nên "bộ X có mùa 2" không tự xuất
    hiện trong DB: phải đi theo quan hệ SEQUEL. Trước đây không làm → app chỉ có
    mùa mà job catalog/schedule tình cờ gặp.

    Chiều ngược lại cũng hỏng: Muse đăng mùa mới trước, nên DB có
    "Ao no Hako Season 2" mà KHÔNG có mùa 1 (đo 2026-11-01: 9/10 bộ có tên mùa
    đều thiếu mùa gốc). Vì vậy bộ nào trông như mùa sau thì đi thêm PREQUEL.
    """
    print("\n▶ Job E — AniList relations: tìm mùa thiếu (SEQUEL + PREQUEL)")
    rows = DB.select(
        "anime",
        "select=id, slug, title_romaji, anilist_id, status&anilist_id=not.is.null"
        f"&order=popularity.desc&limit={int(limit)}",
    )
    print(f"  · {len(rows)} anime sẽ kiểm quan hệ")
    if not rows:
        return 0

    # `known` phải là TOÀN BỘ bảng, không chỉ trang này: nếu chỉ lấy id trong
    # trang thì mùa đã có sẵn (nằm ngoài top `limit`) bị báo nhầm là "mùa mới".
    all_rows = DB.select_all("anime", "select=anilist_id&anilist_id=not.is.null")
    known = {r["anilist_id"] for r in all_rows if r.get("anilist_id")}
    known |= {r["anilist_id"] for r in rows if r.get("anilist_id")}
    added, seen, failures = [], set(), 0
    for i, row in enumerate(rows, 1):
        try:
            sups = anilist.sequels(row["anilist_id"])
        except Exception as e:
            print(f"  ! {row.get('slug')}: {type(e).__name__}: {str(e)[:120]}")
            failures += 1
            continue
        if looks_later_season(row):
            try:
                pres = anilist.prequels(row["anilist_id"])
            except Exception as e:
                print(f"  ! {row.get('slug')} (prequel): {type(e).__name__}: {str(e)[:120]}")
                failures += 1
                pres = []
            for m in pres:
                aid = m.get("id")
                if not aid or aid in known or aid in seen:
                    continue
                if not anilist.is_series_like(m):
                    continue
                seen.add(aid)
                added.append(m)
                t = (m.get("title") or {}).get("romaji") or aid
                print(f"  + mùa TRƯỚC: {t}  (anilist {aid}, {m.get('episodes') or '?'} tập, "
                      f"{m.get('seasonYear') or '?'}) → {row.get('title_romaji')}")
        for m in sups:
            aid = m.get("id")
            if not aid or aid in known or aid in seen:
                continue
            if not anilist.is_series_like(m):
                continue
            seen.add(aid)
            added.append(m)
            t = (m.get("title") or {}).get("romaji") or aid
            print(f"  + mùa mới: {t}  (anilist {aid}, {m.get('episodes') or '?'} tập, "
                  f"{m.get('seasonYear') or '?'}) ← {row.get('title_romaji')}")
        if i % 20 == 0:
            print(f"    … kiểm {i}/{len(rows)}")

    # GHI THEO TỪNG LÔ 25, không gom hết rồi ghi một lần. Ca thật 02/11/2026:
    # phát hiện ~50 mùa trong 6 phút, rồi bước ghi cuối cùng lỗi PGRST102 → mất
    # TRẮNG toàn bộ. Ghi dần thì lỗi giữa đường chỉ mất phần còn lại.
    written = 0
    for i in range(0, len(added), 25):
        chunk = added[i:i + 25]
        _, id_map = _upsert_media(DB, chunk)
        written += len(id_map) if id_map else len(chunk)
        if i + 25 < len(added):
            print(f"    … đã ghi {written}/{len(added)} mùa")

    ok = failures == 0 or bool(added)
    DB.log_ingest("anilist", "seasons", ok, len(added),
                  error=f"{failures} bộ lỗi" if failures else "")
    print(f"  ✓ {len(added)} mùa mới được thêm"
          + (f" · {failures} bộ lỗi (đã bỏ qua)" if failures else ""))
    return len(added)


# ─────────────────────────────────────────────── Job F
def job_jikan(DB, limit: int = 40, only_airing: bool = False,
              fill_gaps: bool = False):
    """Lấp danh sách tập còn THIẾU bằng Jikan (MyAnimeList).

    Vì sao cần: AniList chỉ có tổng số tập; TMDB đôi khi thiếu/lệch mùa. Jikan có
    `title` + `aired` cho từng tập, miễn phí và không cần key, lại dùng đúng
    `mal_id` mà AniList đã trả (`idMal`) nên không phải đoán tên.

    `fill_gaps=False` (mặc định) chỉ lấp bộ **chưa có tập nào**. Bộ thiếu VÀI tập
    (đo 01/11/2026: 33 bộ) trước đây không bao giờ được lấp — dùng `--fill-gaps`.
    """
    print("\n▶ Job F — Jikan (MAL): lấp danh sách tập còn thiếu")
    cols = "id, slug, title_romaji, mal_id, episodes_total, status"
    q = (f"select={cols}&mal_id=not.is.null")
    if only_airing:
        q += "&status=eq.RELEASING"
    q += f"&order=popularity.desc&limit={int(limit)}"
    rows = DB.select("anime", q)
    print(f"  · {len(rows)} anime có mal_id sẽ kiểm")

    filled = written = skipped = errors = 0
    net_errors_in_a_row = 0        # "cầu dao" khi mạng chết hẳn
    for i, row in enumerate(rows, 1):
        try:
            have_rows = DB.select(
                "episodes", f"select=number&anime_id=eq.{row['id']}&limit=600")
            have = {e.get("number") for e in have_rows if e.get("number") is not None}
            total = row.get("episodes_total")
            if have and not fill_gaps:
                skipped += 1
                continue                      # đã có danh sách tập → không đụng
            if have and isinstance(total, int) and total > 0 and len(have) >= total:
                skipped += 1
                continue                      # đã đủ → không gọi API
            items = jikan.episodes(row["mal_id"])
            eps = jikan.episode_rows(row["id"], items, total)
            if have:
                # Chỉ THÊM tập còn thiếu — không ghi đè tên/lịch TMDB đã có.
                eps = [e for e in eps if e["number"] not in have]
            if not eps:
                print(f"  ! {row['slug'][:40]}: Jikan không có tập nào dùng được")
                continue
            DB.upsert("episodes", eps, on_conflict="anime_id,number")
            filled += 1
            written += len(eps)
            print(f"  [{i}/{len(rows)}] {row['slug'][:40]:<40} "
                  f"+{len(eps)} tập (mal {row['mal_id']})")
        except jikan.JikanError as e:
            errors += 1
            print(f"  ! {row['slug'][:40]}: {str(e)[:120]}")
            # Mạng chết thì KHÔNG ngồi chờ 39 bộ × 3 lần thử (ca thật 02/11/2026:
            # 856 giây cho một lần chạy vô ích). 5 bộ liên tiếp không kết nối
            # được → dừng ngay và báo.
            if "không kết nối được" in str(e):
                net_errors_in_a_row += 1
                if net_errors_in_a_row >= 5:
                    raise RuntimeError(
                        f"mạng không tới được api.jikan.moe ({net_errors_in_a_row} bộ "
                        f"liên tiếp) — dừng sớm để không đốt thời gian. "
                        f"Xem gợi ý chẩn đoán ở trên.") from e
            else:
                net_errors_in_a_row = 0
        except Exception as e:
            errors += 1
            print(f"  ! {row['slug'][:40]}: {type(e).__name__}: {str(e)[:120]}")
            net_errors_in_a_row = 0
        else:
            net_errors_in_a_row = 0

    ok = errors == 0 or filled > 0
    DB.log_ingest("jikan", "episodes", ok, written,
                  error=f"{errors} bộ lỗi" if errors else "")
    print(f"  ✓ {filled} bộ được lấp · {written} tập · "
          f"{skipped} bộ đã đủ/đã có tập (bỏ qua)"
          + (f" · {errors} lỗi" if errors else ""))

    # NỔ khi KHÔNG lấp được bộ nào mà vẫn có lỗi. Ca thật 02/11/2026: 39/39 bộ
    # ConnectTimeout tới api.jikan.moe, job in 39 dòng lỗi rồi exit 0 → CI xanh,
    # dữ liệu không đổi, không ai biết. Đúng loại "xanh mà việc thật không xảy ra".
    if filled == 0 and errors > 0:
        raise RuntimeError(
            f"job F không lấp được bộ nào: {errors} bộ lỗi, 0 bộ thành công. "
            f"Xem gợi ý mạng ở log phía trên."
        )
    return written


# ─────────────────────────────────────────────── Job G
def job_check(DB, strict: bool = True):
    """Kiểm bất biến dữ liệu sau khi ingest (xem `ingest/qa.py`).

    Chạy cuối mọi lần `all`/cron hằng ngày. Vi phạm CỨNG (tập vượt tổng, slug
    trùng, một URL gắn 2 bộ…) làm job ĐỎ — vì "cron xanh mà dữ liệu sai" đúng là
    kiểu hỏng tệ nhất. Thiếu nội dung (link vượt tổng, bộ 0 tập) chỉ cảnh báo.
    """
    print("\n▶ Job G — kiểm bất biến dữ liệu")
    if DB.dry:
        print("  [dry-run] cần Supabase để kiểm → bỏ qua")
        return 0
    v = qa.collect(DB)
    print(qa.report(v))
    n_hard = sum(len(x) for x in v["hard"].values())
    DB.log_ingest("qa", "check", not qa.has_hard(v), n_hard,
                  error="; ".join(f"{k}:{len(x)}" for k, x in v["hard"].items())[:400])
    if qa.has_hard(v) and strict:
        raise RuntimeError(
            f"{n_hard} vi phạm cứng trong dữ liệu — xem log phía trên")
    print(f"  ✓ {n_hard} vi phạm cứng" if n_hard else "  ✓ dữ liệu nhất quán")
    return n_hard


# ─────────────────────────────────────────────── CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="AniStream ingest worker")
    ap.add_argument("command", choices=["schedule", "catalog", "youtube", "tmdb",
                                        "seasons", "jikan", "episodes",
                                        "check", "all"])
    ap.add_argument("--hours", type=int, default=26)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--limit", type=int, default=25, help="số video mỗi kênh")
    ap.add_argument("--dry-run", action="store_true", help="không ghi DB")
    ap.add_argument("--no-embed-check", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="lấy TOÀN BỘ lịch sử kênh (cần YOUTUBE_API_KEY)")
    ap.add_argument("--limit-tmdb", type=int, default=60,
                    help="số anime làm giàu mỗi lần chạy job TMDB")
    ap.add_argument("--refresh", action="store_true",
                    help="job tmdb: LÀM MỚI bộ đang chiếu (bắt tập mới), "
                         "không chỉ bộ còn thiếu dữ liệu")
    ap.add_argument("--limit-seasons", type=int, default=80,
                    help="số anime kiểm quan hệ SEQUEL mỗi lần (job seasons)")
    ap.add_argument("--limit-jikan", type=int, default=40,
                    help="số anime lấp danh sách tập từ Jikan mỗi lần")
    ap.add_argument("--only-airing", action="store_true",
                    help="job jikan: chỉ xử lý bộ đang chiếu")
    ap.add_argument("--fill-gaps", action="store_true",
                    help="job jikan: lấp cả bộ THIẾU VÀI TẬP (không chỉ bộ 0 tập)")
    ap.add_argument("--no-strict", action="store_true",
                    help="job check: chỉ cảnh báo, không làm đỏ job")
    ap.add_argument("--no-cache", action="store_true",
                    help="bỏ qua .cache/match_cache.json (ghép lại tên từ đầu)")
    ap.add_argument("--channel", default="",
                    help="chỉ xử lý 1 kênh (muse_vn | ani_one_asia)")
    ap.add_argument("--max-videos", type=int, default=5000,
                    help="giới hạn số video mỗi kênh khi --deep")
    args = ap.parse_args(argv)

    if args.dry_run:
        config.DRY_RUN = True

    print(f"AniStream ingest · {dt.datetime.now():%Y-%m-%d %H:%M} · "
          f"{'DRY-RUN (không ghi DB)' if config.DRY_RUN else 'GHI THẬT vào Supabase'}")

    try:
        DB = dbmod.DB(dry_run=config.DRY_RUN)
    except RuntimeError as e:
        print(f"\n✗ {e}")
        return 2

    started = time.time()
    total = 0
    try:
        if args.command in ("schedule", "all"):
            total += job_schedule(DB, args.hours)
        if args.command in ("catalog", "all"):
            total += job_catalog(DB, args.pages)
        if args.command in ("youtube", "all"):
            total += job_youtube(DB, args.limit, not args.no_embed_check,
                                 deep=args.deep, max_per_channel=args.max_videos,
                                 use_cache=not args.no_cache,
                                 only_channel=args.channel)
        if args.command == "tmdb":
            total += job_tmdb(DB, args.limit_tmdb, refresh=args.refresh)
        if args.command == "seasons":
            total += job_seasons(DB, args.limit_seasons)
        if args.command == "jikan":
            total += job_jikan(DB, args.limit_jikan, args.only_airing, args.fill_gaps)
        if args.command == "episodes":
            total += job_link_episodes(DB)
        if args.command == "check":
            total += job_check(DB, strict=not args.no_strict)
        if args.command == "all":
            # Job D cần key; job E/F thì không → thiếu key TMDB KHÔNG được chặn E/F.
            if tmdb.is_configured():
                # ngày chạy đầy đủ: bổ sung bộ thiếu + làm mới bộ đang chiếu
                total += job_tmdb(DB, args.limit_tmdb)
                total += job_tmdb(DB, args.limit_tmdb, refresh=True)
            else:
                print("\n⚠ BỎ QUA Job D (TMDB): chưa có TMDB_API_KEY → "
                      "tên/tóm tắt tiếng Việt và danh sách tập sẽ không được bổ sung.")
                DB.log_ingest("tmdb", "enrich", False, 0, "thiếu TMDB_API_KEY")
            total += job_seasons(DB, args.limit_seasons)
            total += job_jikan(DB, args.limit_jikan, fill_gaps=True)
            total += job_link_episodes(DB)
            total += job_check(DB, strict=not args.no_strict)
    except KeyboardInterrupt:
        print("\n… dừng theo yêu cầu")
        return 130
    except Exception as e:
        print(f"\n✗ Lỗi: {e}")
        DB.log_ingest("worker", args.command, False, total, str(e))
        raise

    print(f"\n✅ Xong sau {time.time() - started:.1f}s · {total} bản ghi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
