#!/usr/bin/env python3
"""
anime_api_demo.py — Demo lấy dữ liệu anime từ API hợp pháp (không cần key).

Nguồn dùng:
  - AniList GraphQL   https://graphql.anilist.co     (lịch phát tập, trending, search)
  - Kitsu JSON:API    https://kitsu.io/api/edge      (vừa cập nhật)
  - AnimeSchedule v3  https://animeschedule.net/api/v3 (dự phòng lịch chiếu)

Cách dùng:
  python3 anime_api_demo.py lich            # tập sắp chiếu trong 24h tới
  python3 anime_api_demo.py lich 72         # trong 72h
  python3 anime_api_demo.py moi             # anime mùa này + top trending
  python3 anime_api_demo.py tim "frieren"   # tìm kiếm
  python3 anime_api_demo.py vua-cap-nhat    # Kitsu: bản ghi vừa update
  python3 anime_api_demo.py report          # xuất anime_report.html (ảnh nhúng sẵn)
"""
import io
import os
import sys
import json
import time
import base64
import datetime as dt
import requests

# Hiển thị giờ Việt Nam bất kể server chạy múi giờ nào (đổi thành "UTC" nếu cần)
os.environ["TZ"] = os.environ.get("ANIME_TZ", "Asia/Ho_Chi_Minh")
try:
    time.tzset()
except AttributeError:          # Windows không có tzset
    pass

ANILIST = "https://graphql.anilist.co"
KITSU = "https://kitsu.io/api/edge"
UA = {"User-Agent": "anime-api-demo/1.0", "Content-Type": "application/json"}

MEDIA_FIELDS = """
  id idMal
  title { romaji english native }
  coverImage { large }
  siteUrl
  averageScore
  episodes
  status
  genres
  season seasonYear
  nextAiringEpisode { episode airingAt }
"""


# ─────────────────────────────────────────── helpers
def anilist(query, variables=None, retries=3):
    """Gọi AniList GraphQL, retry khi bị rate limit (429)."""
    for attempt in range(retries):
        r = requests.post(ANILIST, json={"query": query, "variables": variables or {}},
                          headers=UA, timeout=25)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 10))
            print(f"  … rate limited, đợi {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        payload = r.json()
        if "errors" in payload:
            raise RuntimeError(payload["errors"])
        return payload["data"]
    raise RuntimeError("AniList: hết lượt retry")


def current_season(now=None):
    now = now or dt.date.today()
    return {1: "WINTER", 2: "WINTER", 3: "WINTER",
            4: "SPRING", 5: "SPRING", 6: "SPRING",
            7: "SUMMER", 8: "SUMMER", 9: "SUMMER",
            10: "FALL", 11: "FALL", 12: "FALL"}[now.month]


def vn_title(m):
    """Tiêu đề hiển thị: ưu tiên romaji (dễ đọc với người Việt hơn native)."""
    t = m.get("title") or {}
    return t.get("romaji") or t.get("english") or t.get("native") or "?"


def fmt_ts(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def countdown(ts):
    delta = ts - time.time()
    if delta <= 0:
        return "đang chiếu"
    h, m = divmod(int(delta // 60), 60)
    return f"{h}h{m:02d}p" if h < 48 else f"{h // 24} ngày"


# ─────────────────────────────────────────── commands
def cmd_lich(hours=24):
    now = int(time.time())
    q = f"""query($f:Int,$t:Int){{
      Page(perPage:60){{
        airingSchedules(airingAt_greater:$f, airingAt_lesser:$t, sort:TIME){{
          airingAt episode media{{ {MEDIA_FIELDS} }}
        }}
      }} }}"""
    data = anilist(q, {"f": now, "t": now + hours * 3600})
    rows = data["Page"]["airingSchedules"]
    print(f"\n🗓  {len(rows)} tập phát trong {hours}h tới (giờ VN)\n" + "-" * 78)
    for s in rows:
        m = s["media"]
        print(f'{fmt_ts(s["airingAt"])}  ({countdown(s["airingAt"]):>9})  '
              f'Ep {str(s["episode"]):>3}  {vn_title(m)[:46]}')
    print("-" * 78)
    return rows


def cmd_moi():
    season = current_season()
    year = dt.date.today().year
    q = f"""query($s:MediaSeason,$y:Int){{
      season: Page(perPage:12){{
        media(season:$s, seasonYear:$y, type:ANIME, sort:POPULARITY_DESC, isAdult:false){{ {MEDIA_FIELDS} }}
      }}
      trending: Page(perPage:10){{
        media(type:ANIME, sort:TRENDING_DESC, isAdult:false){{ {MEDIA_FIELDS} }}
      }} }}"""
    data = anilist(q, {"s": season, "y": year})
    print(f"\n🎬 Mùa {season} {year} — phổ biến nhất\n" + "-" * 78)
    for m in data["season"]["media"]:
        print(f'{m["averageScore"] or "--":>3}  {vn_title(m)[:52]:<52} {m["status"]}')
    print(f"\n🔥 Trending toàn cầu ngay bây giờ\n" + "-" * 78)
    for m in data["trending"]["media"]:
        nae = m.get("nextAiringEpisode")
        extra = f'→ ep {nae["episode"]} {countdown(nae["airingAt"])}' if nae else (m["status"] or "")
        print(f'{m["averageScore"] or "--":>3}  {vn_title(m)[:52]:<52} {extra}')
    print("-" * 78)
    return data


def cmd_tim(keyword):
    q = """query($q:String){ Page(perPage:8){ media(search:$q, type:ANIME){
             %s } } }""" % MEDIA_FIELDS
    data = anilist(q, {"q": keyword})
    print(f'\n🔎 "{keyword}"\n' + "-" * 78)
    for m in data["Page"]["media"]:
        t = m["title"]
        print(f'{m["id"]:>7}  {vn_title(m)[:44]:<44} {m["averageScore"] or "--":>3}  '
              f'{(t.get("english") or "")[:22]}')
    print("-" * 78)
    return data


def cmd_vua_cap_nhat(n=15):
    """Kitsu: anime vừa được cập nhật (sort=-updatedAt)."""
    r = requests.get(f"{KITSU}/anime",
                     params={"page[limit]": n, "sort": "-updatedAt"},
                     headers={"User-Agent": UA["User-Agent"], "Accept": "application/vnd.api+json"},
                     timeout=25)
    r.raise_for_status()
    items = r.json()["data"]
    print(f"\n♻️  {n} bản ghi vừa cập nhật trên Kitsu\n" + "-" * 78)
    for a in items:
        at = a["attributes"]
        print(f'{str(at.get("status")):<12} {str(at.get("canonicalTitle"))[:46]:<46} '
              f'{at.get("updatedAt", "")[:10]}')
    print("-" * 78)
    return items


# ─────────────────────────────────────────── HTML report
def _thumb(url, w=120):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": UA["User-Agent"]})
        r.raise_for_status()
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((w, w * 2))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def cmd_report():
    now = int(time.time())
    lich = anilist(f"""query($f:Int,$t:Int){{Page(perPage:18){{
        airingSchedules(airingAt_greater:$f, airingAt_lesser:$t, sort:TIME){{
          airingAt episode media{{ {MEDIA_FIELDS} }} }} }}}}""",
                   {"f": now, "t": now + 72 * 3600})["Page"]["airingSchedules"]
    season, year = current_season(), dt.date.today().year
    moi = anilist(f"""query($s:MediaSeason,$y:Int){{Page(perPage:12){{
        media(season:$s, seasonYear:$y, type:ANIME, sort:POPULARITY_DESC, isAdult:false){{ {MEDIA_FIELDS} }} }}}}""",
                  {"s": season, "y": year})["Page"]["media"]

    print("  đang tải poster (nhúng base64 để xem offline)…", file=sys.stderr)
    cards_lich = []
    for s in lich:
        m = s["media"]
        img = _thumb(m["coverImage"]["large"])
        cards_lich.append(f"""
        <div class="card">
          <img src="{img}" alt="">
          <div class="body">
            <div class="time">{fmt_ts(s['airingAt'])} · <b>{countdown(s['airingAt'])}</b></div>
            <div class="title">{vn_title(m)}</div>
            <div class="meta">Tập {s['episode']} · ⭐ {m['averageScore'] or '--'}</div>
          </div>
        </div>""")

    cards_moi = []
    for m in moi:
        img = _thumb(m["coverImage"]["large"])
        cards_moi.append(f"""
        <div class="card">
          <img src="{img}" alt="">
          <div class="body">
            <div class="title">{vn_title(m)}</div>
            <div class="meta">⭐ {m['averageScore'] or '--'} · {m['status'] or ''} ·
              {m['episodes'] or '?'} tập</div>
          </div>
        </div>""")

    html = f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anime Feed — {dt.date.today():%d/%m/%Y}</title>
<style>
  :root{{--bg:#0e1117;--card:#171b24;--line:#242a36;--tx:#e6e9ef;--mut:#8b94a7;--acc:#7c5cff}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--tx);
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;padding:28px}}
  h1{{font-size:21px;margin:0 0 4px}}
  .sub{{color:var(--mut);font-size:13px;margin-bottom:26px}}
  h2{{font-size:15px;margin:30px 0 14px;padding-left:10px;border-left:3px solid var(--acc);
     text-transform:uppercase;letter-spacing:.06em;color:#c9cee0}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}}
  .card{{display:flex;gap:11px;background:var(--card);border:1px solid var(--line);
        border-radius:11px;overflow:hidden;padding:9px}}
  .card img{{width:60px;height:88px;object-fit:cover;border-radius:7px;flex:0 0 auto;background:#222}}
  .body{{min-width:0;display:flex;flex-direction:column;justify-content:center;gap:3px}}
  .title{{font-size:13px;font-weight:600;line-height:1.3;
         display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .meta{{font-size:11.5px;color:var(--mut)}}
  .time{{font-size:11.5px;color:#9d8bff;font-weight:600}}
  footer{{margin-top:34px;font-size:11.5px;color:#5d6577;line-height:1.7}}
  code{{background:#1c2130;padding:1px 5px;border-radius:4px;font-size:11px}}
</style></head><body>
  <h1>🎬 Anime Feed</h1>
  <div class="sub">Tạo lúc {dt.datetime.now():%H:%M %d/%m/%Y} (giờ VN) · dữ liệu từ AniList GraphQL + Kitsu (miễn phí, không cần key)</div>
  <h2>Tập sắp phát · 72 giờ tới</h2>
  <div class="grid">{''.join(cards_lich)}</div>
  <h2>Mùa {season} {year} · phổ biến nhất</h2>
  <div class="grid">{''.join(cards_moi)}</div>
  <footer>
    Script: <code>anime_api_demo.py</code> · Chạy lại: <code>python3 anime_api_demo.py report</code><br>
    Ảnh đã nhúng base64 nên file xem được offline / trong preview không có mạng.<br>
    Nguồn: <code>graphql.anilist.co</code> (lịch phát) · <code>kitsu.io/api/edge</code> (cập nhật) —
    xem thêm <code>anime_sources.md</code> trong workspace.
  </footer>
</body></html>"""

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anime_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Đã ghi {out} ({len(html) / 1024:.0f} KB)")


# ─────────────────────────────────────────── main
def main():
    args = sys.argv[1:] or ["lich"]
    cmd = args[0]
    if cmd == "lich":
        cmd_lich(int(args[1]) if len(args) > 1 else 24)
    elif cmd == "moi":
        cmd_moi()
    elif cmd == "tim":
        if len(args) < 2:
            sys.exit("Thiếu từ khóa: python3 anime_api_demo.py tim \"frieren\"")
        cmd_tim(" ".join(args[1:]))
    elif cmd == "vua-cap-nhat":
        cmd_vua_cap_nhat(int(args[1]) if len(args) > 1 else 15)
    elif cmd == "report":
        cmd_report()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
