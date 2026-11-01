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
import sys
import time

from . import anilist, config, db as dbmod, match, tmdb, youtube


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
def job_youtube(DB, limit: int = 25, check_embed: bool = True,
                deep: bool = False, max_per_channel: int = 5000):
    mode = "BACKFILL toàn bộ kênh (YouTube API)" if deep else "RSS (video mới nhất)"
    print(f"\n▶ Job C — video official → streaming_links  [{mode}]")
    videos = youtube.collect(limit_per_channel=limit, check_embed=check_embed,
                             deep=deep, max_per_channel=max_per_channel)
    print(f"  · {len(videos)} video dùng được")

    cache, matched, unmatched = {}, [], {}
    links = []
    for v in videos:
        media, confidence, how = match.resolve(
            v["series"], cache, want_series=(v["episode"] > 0))
        # Fuzzy partial matches can confuse entirely different series or seasons.
        # Only editorial aliases or exact full titles are published automatically.
        import re
        import unicodedata
        def exact_title(value):
            value = unicodedata.normalize("NFKC", value or "").casefold()
            return re.sub(r"[^\w]+", " ", value).strip()
        title = (media or {}).get("title") or {}
        names = [title.get(k) for k in ("romaji", "english", "native")]
        alias_exists = match.alias_key(v["series"]) in match._ALIASES
        exact = exact_title(v["series"]) in {exact_title(n) for n in names if n}
        if not media or not (alias_exists or exact):
            unmatched.setdefault(v["series"], 0)
            unmatched[v["series"]] += 1
            continue
        matched.append((v, media, confidence, how))

    print(f"  · khớp được {len(matched)}/{len(videos)} video "
          f"({len(unmatched)} tên series chưa khớp)")

    # 1) upsert anime trước để có id
    rows, id_map = _upsert_media(DB, [m for _, m, _, _ in matched])

    # 2) tạo links
    seen_url = set()
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
        })

    if DB.dry:
        print(f"  [dry-run] sẽ upsert {len(links)} streaming_links")
        for v, media, conf, how in matched[:14]:
            t = (media.get("title") or {}).get("romaji", "")
            print(f"    ep{str(v['episode']).rjust(3)}  {conf:.2f} {how:<10} "
                  f"{v['series'][:30]:<30} → {t[:32]}")
    else:
        DB.upsert("streaming_links", links,
                  on_conflict="anime_id,platform,region,episode_number",
                  fallback_per_row=True)

    if unmatched:
        print("  ⚠ chưa khớp (cần map tay trong bảng platform_map / alias):")
        for name, n in list(unmatched.items())[:10]:
            print(f"      - {name}  ({n} video)")

    DB.log_ingest("youtube", "links", True, len(links))
    print(f"  ✓ {len(rows)} anime · {len(links)} links")
    return len(links)


# ─────────────────────────────────────────────── Job D
def job_tmdb(DB, limit: int = 60, with_episodes: bool = True):
    """Bổ sung tiếng Việt (title_vi, synopsis_vi) + danh sách tập từ TMDB.

    Vì sao cần: AniList không có tiếng Việt → app toàn hiện tên romaji; và chỉ
    22/104 anime có episodes nên mở bộ khác là trang chi tiết trống.
    """
    print("\n▶ Job D — TMDB: tên + tóm tắt tiếng Việt, danh sách tập")
    if not tmdb.is_configured():
        raise RuntimeError(
            "Thiếu TMDB_API_KEY → không bổ sung được tiếng Việt.\n"
            "  Lấy key miễn phí: https://www.themoviedb.org/settings/api\n"
            "  Thêm vào .env:  TMDB_API_KEY=xxxxxxxx"
        )

    cols = ("id, slug, title_romaji, title_english, title_native, title_vi, "
            "synopsis_vi, year, episodes_total, tmdb_id")
    # Ưu tiên bộ phổ biến (người dùng thấy trước), và bộ còn thiếu dữ liệu.
    rows = DB.select(
        "anime",
        f"select={cols}&or=(title_vi.is.null,synopsis_vi.is.null,episodes_total.is.null)"
        f"&order=popularity.desc&limit={int(limit)}",
    )
    print(f"  · {len(rows)} anime cần làm giàu")

    patched = eps_written = 0
    no_match, no_vi, multi_season, implausible = [], [], [], []
    for i, row in enumerate(rows, 1):
        label = (row.get("title_english") or row.get("title_romaji") or row.get("slug"))[:46]
        try:
            best, score, how = tmdb.match_anime(row)
            if not best:
                no_match.append(f"{label}  ({how})")
                continue
            detail = tmdb.fetch_detail(best["id"])
            title_vi, overview_vi = tmdb.extract_vietnamese(detail)

            # TMDB gộp cả series vào 1 id; AniList tách từng mùa. Phải chọn đúng mùa
            # thì danh sách tập mới đúng — trước đây bỏ qua MỌI bộ nhiều mùa nên
            # Takagi-san (3 mùa) không có tập nào dù đã có tmdb_id.
            season_no, why = tmdb.pick_season(
                detail, row.get("year"), row.get("episodes_total"))
            matched = season_no is not None
            if not matched and len(tmdb.real_seasons(detail)) > 1:
                multi_season.append(f"{label}  ({why})")

            hint = None
            if matched:
                hint = next(
                    (s["count"] for s in tmdb.season_candidates(detail)
                     if s["number"] == season_no), None)

            patch = tmdb.build_anime_patch(row, detail, title_vi, overview_vi,
                                           matched, episodes_total_hint=hint)
            if patch:
                DB.patch("anime", {"id": row["id"]}, patch)
                patched += 1
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
                have = DB.select("episodes", f"select=number&anime_id=eq.{row['id']}&limit=1")
                if not have:
                    season = tmdb.fetch_season(best["id"], season_no)
                    n_season = len([e for e in (season.get("episodes") or [])
                                    if isinstance(e.get("episode_number"), int)])
                    if not tmdb.episodes_plausible(row.get("episodes_total"), n_season):
                        implausible.append(
                            f"{label}  (TMDB {n_season} tập > AniList "
                            f"{row.get('episodes_total')})")
                    else:
                        eps = tmdb.episode_rows(row["id"], season, matched)
                        if eps:
                            DB.upsert("episodes", eps, on_conflict="anime_id,number")
                            eps_written += len(eps)
                            print(f"      + {len(eps)} tập (mùa {season_no}, {why})")
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
        print(f"  ⚠ {len(multi_season)} anime nhiều mùa mà KHÔNG xác định được mùa nào "
              f"→ chỉ lấy tên/tóm tắt, không lấy tập:")
        for n in multi_season[:8]:
            print(f"      - {n}")
    if implausible:
        print(f"  ⚠ {len(implausible)} anime có danh sách tập TMDB KHÔNG hợp với AniList "
              f"→ không ghi (tránh gán sai):")
        for n in implausible[:8]:
            print(f"      - {n}")

    DB.log_ingest("tmdb", "enrich", True, patched + eps_written)
    print(f"  ✓ {patched} anime được bổ sung · {eps_written} tập")
    return patched + eps_written


# ─────────────────────────────────────────────── CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="AniStream ingest worker")
    ap.add_argument("command", choices=["schedule", "catalog", "youtube", "tmdb", "all"])
    ap.add_argument("--hours", type=int, default=26)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--limit", type=int, default=25, help="số video mỗi kênh")
    ap.add_argument("--dry-run", action="store_true", help="không ghi DB")
    ap.add_argument("--no-embed-check", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="lấy TOÀN BỘ lịch sử kênh (cần YOUTUBE_API_KEY)")
    ap.add_argument("--limit-tmdb", type=int, default=60,
                    help="số anime làm giàu mỗi lần chạy job TMDB")
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
                                 deep=args.deep, max_per_channel=args.max_videos)
        if args.command == "tmdb":
            total += job_tmdb(DB, args.limit_tmdb)
        elif args.command == "all":
            # `all` chạy cả 4 job. Không có key TMDB thì BÁO RÕ rồi bỏ qua job D
            # (không im lặng, và không làm đỏ cả lần chạy vì thiếu key tuỳ chọn).
            if tmdb.is_configured():
                total += job_tmdb(DB, args.limit_tmdb)
            else:
                print("\n⚠ BỎ QUA Job D (TMDB): chưa có TMDB_API_KEY → "
                      "tên/tóm tắt tiếng Việt và danh sách tập sẽ không được bổ sung.")
                DB.log_ingest("tmdb", "enrich", False, 0, "thiếu TMDB_API_KEY")
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
