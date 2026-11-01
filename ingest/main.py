#!/usr/bin/env python3
"""
main.py — Worker ingest cho AniStream (mô hình 🅒 Free Legal Streaming).

Lệnh:
  python3 -m ingest.main schedule  [--hours 26]   # A. lịch phát → anime + episodes  (chạy mỗi 30')
  python3 -m ingest.main catalog   [--pages 2]    # B. catalog theo mùa → anime      (chạy mỗi đêm)
  python3 -m ingest.main youtube   [--limit 25]   # C. video official → streaming_links (mỗi 6h)
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

from . import anilist, config, db as dbmod, match, youtube


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


# ─────────────────────────────────────────────── CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="AniStream ingest worker")
    ap.add_argument("command", choices=["schedule", "catalog", "youtube", "all"])
    ap.add_argument("--hours", type=int, default=26)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--limit", type=int, default=25, help="số video mỗi kênh")
    ap.add_argument("--dry-run", action="store_true", help="không ghi DB")
    ap.add_argument("--no-embed-check", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="lấy TOÀN BỘ lịch sử kênh (cần YOUTUBE_API_KEY)")
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
