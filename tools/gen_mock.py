#!/usr/bin/env python3
"""
gen_mock.py — Sinh `app/lib/data/mock_data.dart` từ dữ liệu THẬT của AniList + YouTube.

Vì sao có script này:
  • App Flutter cần dữ liệu để chạy trước khi bạn dựng xong Supabase.
  • Mock bằng dữ liệu thật → UI không bị "lorem ipsum", và video ID thật nên
    màn hình player bấm ▶ là phát được ngay (video official, cho nhúng).

Chạy:  python3 tools/gen_mock.py
"""
import html
import json
import os
import re
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest import anilist, match, youtube     # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "app", "lib", "data", "mock_data.dart")

PLATFORM_URLS = {
    "Crunchyroll": "https://www.crunchyroll.com/",
    "Netflix": "https://www.netflix.com/",
    "Bilibili TV": "https://www.bilibili.tv/",
    "YouTube": "https://www.youtube.com/",
    "Hulu": "https://www.hulu.com/",
}


def strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:420] + ("…" if len(s) > 420 else "")


def slug(t: dict, iid: int) -> str:
    s = (t.get("romaji") or t.get("english") or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or f"anime-{iid}"


def vip_title(t: dict) -> str:
    """Tên tiếng Việt tạm (chưa có TMDB key) — dùng romaji làm chuẩn."""
    return t.get("romaji") or t.get("english") or t.get("native") or "?"


def main():
    print("· lấy anime từ AniList…")
    today = dt.date.today()
    season = anilist.season_of(today.month)

    pool = {}
    for m in anilist.seasonal(season, today.year, per_page=25):
        pool[m["id"]] = m
    q = """query{ Page(perPage:25){ media(type:ANIME, sort:TRENDING_DESC, isAdult:false){ %s } } }""" % anilist.MEDIA_FIELDS
    for m in anilist.gql(q)["Page"]["media"]:
        pool.setdefault(m["id"], m)
    print(f"  · {len(pool)} bộ")

    print("· lấy video official từ YouTube…")
    vids_by_anime = {}
    try:
        videos = youtube.collect(limit_per_channel=20, check_embed=True, verbose=False)
        cache = {}
        for v in videos:
            media, conf, how = match.resolve(v["series"], cache, want_series=v["episode"] > 0)
            if media and conf >= 0.72:
                vids_by_anime.setdefault(media["id"], []).append(v)
                pool.setdefault(media["id"], media)   # đảm bảo bộ có video luôn nằm trong catalog
        print(f"  · {len(videos)} video → {len(vids_by_anime)} bộ có video")
    except Exception as e:
        print(f"  ! bỏ qua YouTube: {e}")

    anime_rows = []
    for iid, m in list(pool.items()):
        t = m.get("title") or {}
        eps = []
        for v in sorted(vids_by_anime.get(iid, []), key=lambda x: x["episode"]):
            eps.append({
                "number": v["episode"],
                "title": v["raw_title"][:90],
                "video_id": v["video_id"],
                "platform": "youtube",
                "airing_at": v["published"],
            })
        if not eps and m.get("nextAiringEpisode"):
            n = m["nextAiringEpisode"]
            eps.append({
                "number": n["episode"],
                "title": f"Tập {n['episode']}",
                "video_id": None,
                "platform": None,
                "airing_at": dt.datetime.fromtimestamp(
                    n["airingAt"], dt.timezone.utc).isoformat(),
            })

        platforms = []
        for l in (m.get("externalLinks") or []):
            site = l.get("site") or ""
            if site in PLATFORM_URLS:
                platforms.append({"name": site, "url": l["url"], "verified": True})
        seen = set()
        platforms = [p for p in platforms
                     if not (p["name"] in seen or seen.add(p["name"]))]

        anime_rows.append({
            "id": iid,
            "slug": slug(t, iid),
            "title": vip_title(t),
            "title_vi": None,
            "title_native": t.get("native"),
            "cover": (m.get("coverImage") or {}).get("extraLarge")
                     or (m.get("coverImage") or {}).get("large"),
            "banner": m.get("bannerImage"),
            "score": round(m["averageScore"] / 10, 1) if m.get("averageScore") else None,
            "year": m.get("seasonYear"),
            "season": m.get("season"),
            "format": m.get("format"),
            "status": m.get("status"),
            "episodes_total": m.get("episodes"),
            "genres": (m.get("genres") or [])[:4],
            "synopsis": strip_html(m.get("description")),
            "is_free": bool(eps and eps[0]["video_id"]),
            "platforms": platforms[:3],
            "episodes": eps,
            "popularity": m.get("popularity") or 0,
        })

    anime_rows.sort(key=lambda a: -(a["popularity"] or 0))
    by_id = anime_rows

    def pick(pred, n=12):
        return [a["id"] for a in by_id if pred(a)][:n]

    shelves = [
        {"title": "Xem ngay — miễn phí, hợp pháp", "kind": "free",
         "ids": pick(lambda a: a["is_free"])},
        {"title": "Tập mới hôm nay", "kind": "new_episodes",
         "ids": [a["id"] for a in by_id if a["episodes"]][:12]},
        {"title": "Mùa này", "kind": "season",
         "ids": pick(lambda a: True)},
        {"title": "Điểm cao nhất", "kind": "top",
         "ids": [a["id"] for a in sorted(by_id, key=lambda a: -(a["score"] or 0))][:12]},
    ]
    shelves = [s for s in shelves if s["ids"]]

    # lịch phát 7 ngày tới (dùng nextAiringEpisode nếu có, nếu không thì giả lập giờ vàng)
    schedule = []
    now = dt.datetime.now(dt.timezone.utc)
    for i, a in enumerate(by_id[:24]):
        if a["episodes"] and a["episodes"][0]["airing_at"]:
            schedule.append({"anime_id": a["id"], "episode": a["episodes"][0]["number"],
                             "airing_at": a["episodes"][0]["airing_at"]})
        else:
            slot = (now + dt.timedelta(hours=3 + i * 5)).replace(minute=0, second=0, microsecond=0)
            schedule.append({"anime_id": a["id"], "episode": (i % 12) + 1,
                             "airing_at": slot.isoformat()})
    schedule.sort(key=lambda x: x["airing_at"])

    payload = {
        "generated_at": now.isoformat(),
        "source": "AniList GraphQL + YouTube RSS (dữ liệu thật, sinh tự động)",
        "anime": anime_rows,
        "shelves": shelves,
        "schedule": schedule,
    }

    js = json.dumps(payload, ensure_ascii=False, indent=1)
    dart = (
        "// AUTO-GENERATED bởi tools/gen_mock.py — ĐỪNG SỬA TAY.\n"
        "// Dữ liệu thật từ AniList + video official từ YouTube RSS.\n"
        "// Sinh lại: python3 tools/gen_mock.py\n\n"
        "const String kMockDataJson = r'''\n" + js + "\n''';\n"
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(dart)
    print(f"✅ {OUT} ({len(dart) / 1024:.0f} KB) · "
          f"{len(anime_rows)} anime · {sum(len(a['episodes']) for a in anime_rows)} tập · "
          f"{len(shelves)} shelf · {len(schedule)} slot lịch")


if __name__ == "__main__":
    main()
