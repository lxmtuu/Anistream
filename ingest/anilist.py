"""
anilist.py — AniList GraphQL: lịch phát, catalog theo mùa, search.
Miễn phí, không cần key. Giới hạn ~30–90 request/phút → có retry khi 429.
"""
import datetime as dt
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import requests

from . import config

ENDPOINT = "https://graphql.anilist.co"

# ── Chống rate limit ────────────────────────────────────────────────────────
# AniList cho ~90 request/phút, nhưng khi hệ thống của họ tải cao thì hạ xuống
# ~30/phút và trả 429 kèm Retry-After. Backfill YouTube có thể cần hàng trăm
# request → không tự giãn nhịp thì cứ 40 giây lại bị chặn một lần và chạy mãi
# không xong.
#   MIN_INTERVAL: giãn cách tối thiểu giữa 2 request (giây), tăng dần khi bị 429.
#   Chỉnh bằng biến môi trường ANILIST_MIN_INTERVAL nếu cần chạy nhanh/chậm hơn.
MIN_INTERVAL = float(os.environ.get("ANILIST_MIN_INTERVAL", "1.0"))
MAX_INTERVAL = 6.0
_last_call = 0.0


def _throttle() -> None:
    """Chờ cho đủ MIN_INTERVAL kể từ request trước (không chờ nếu đã đủ lâu)."""
    global _last_call
    wait = _last_call + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _slow_down(retry_after: Optional[str] = None) -> None:
    """Bị 429 → giãn nhịp cho các request sau (không chỉ ngủ rồi thử lại y như cũ)."""
    global MIN_INTERVAL
    MIN_INTERVAL = min(round(MIN_INTERVAL * 1.5, 2), MAX_INTERVAL)
    del retry_after                     # Retry-After được ngủ riêng trong gql()

MEDIA_FIELDS = """
  id idMal
  title { romaji english native }
  description(asHtml: false)
  coverImage { large extraLarge color }
  bannerImage
  siteUrl
  averageScore meanScore popularity
  episodes duration status season seasonYear format
  genres
  studios(isMain: true) { nodes { name } }
  nextAiringEpisode { episode airingAt }
  trailer { id site }
  externalLinks { url site type }
"""


def gql(query: str, variables: Optional[Dict] = None, retries: int = 4) -> Dict:
    for attempt in range(retries):
        _throttle()
        r = requests.post(
            ENDPOINT,
            json={"query": query, "variables": variables or {}},
            headers={"User-Agent": config.USER_AGENT, "Content-Type": "application/json"},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code == 429:
            raw = r.headers.get("Retry-After", "15")
            try:
                wait = int(float(raw))
            except (TypeError, ValueError):
                wait = 15
            _slow_down(raw)
            print(f"  … AniList rate limit, đợi {wait}s "
                  f"(giãn nhịp lên {MIN_INTERVAL}s/request)")
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        payload = r.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        return payload["data"]
    raise RuntimeError("AniList: hết lượt retry")


# ──────────────────────────────────────────────────────────
def airing_schedules(from_ts: int, to_ts: int, per_page: int = 50) -> List[Dict]:
    """Tập sắp/đang phát trong khoảng [from_ts, to_ts] (unix giây)."""
    q = """
    query($from:Int,$to:Int,$n:Int){
      Page(perPage:$n){
        airingSchedules(airingAt_greater:$from, airingAt_lesser:$to, sort:TIME){
          airingAt episode
          media { %s }
        }
      }
    }""" % MEDIA_FIELDS
    data = gql(q, {"from": from_ts, "to": to_ts, "n": per_page})
    return data["Page"]["airingSchedules"]


def seasonal(season: str, year: int, page: int = 1, per_page: int = 50) -> List[Dict]:
    """Danh sách anime của một mùa, sắp theo độ phổ biến."""
    q = """
    query($s:MediaSeason,$y:Int,$p:Int,$n:Int){
      Page(page:$p, perPage:$n){
        media(season:$s, seasonYear:$y, type:ANIME, sort:POPULARITY_DESC, isAdult:false){
          %s
        }
      }
    }""" % MEDIA_FIELDS
    data = gql(q, {"s": season, "y": year, "p": page, "n": per_page})
    return data["Page"]["media"]


def search_media(title: str, per_page: int = 5) -> List[Dict]:
    """Tìm anime theo tên (dùng để match video YouTube → anime)."""
    q = """
    query($q:String,$n:Int){
      Page(perPage:$n){
        media(search:$q, type:ANIME, isAdult:false, sort:SEARCH_MATCH){ %s }
      }
    }""" % MEDIA_FIELDS
    try:
        data = gql(q, {"q": title, "n": per_page})
    except Exception as e:
        print(f"  ! search lỗi cho '{title}': {e}")
        return []
    return data["Page"]["media"]


# ──────────────────────────────────────────────────────────
# Mùa MỚI: AniList ghi quan hệ PREQUEL/SEQUEL giữa các entry. Đây là cách DUY NHẤT
# biết "bộ này vừa có mùa 2" mà không phải thêm tay từng bộ: mỗi mùa là một entry
# riêng, và entry mùa 1 KHÔNG tự có tập của mùa 2.
def related(media_id: int,
            kinds: Tuple[str, ...] = ("SEQUEL",)) -> List[Dict]:
    """Các entry có quan hệ thuộc `kinds` (SEQUEL / PREQUEL / …) với `media_id`."""
    q = """
    query($id:Int){
      Media(id:$id, type:ANIME){
        id
        relations{
          edges{
            relationType(version:2)
            node{ %s }
          }
        }
      }
    }""" % MEDIA_FIELDS
    data = gql(q, {"id": media_id})
    edges = (((data.get("Media") or {}).get("relations") or {}).get("edges") or [])
    wanted = {k.upper() for k in kinds}
    out = []
    for e in edges:
        if (e.get("relationType") or "").upper() not in wanted:
            continue
        node = e.get("node") or {}
        if node.get("id"):
            out.append(node)
    return out


def sequels(media_id: int) -> List[Dict]:
    """Các entry là SEQUEL (mùa sau) của `media_id`."""
    return related(media_id, ("SEQUEL",))


def prequels(media_id: int) -> List[Dict]:
    """Các entry là PREQUEL (mùa TRƯỚC) của `media_id`.

    Cần vì Muse đăng mùa mới nhất trước, nên DB có "Ao no Hako Season 2" mà KHÔNG
    có mùa 1 — người dùng bấm vào bộ là thấy thiếu hẳn phần đầu.
    """
    return related(media_id, ("PREQUEL",))


def is_series_like(media: Dict) -> bool:
    """SEQUEL dạng TV/ONA mới là 'mùa mới'; MOVIE/SPECIAL thì không cùng danh sách tập."""
    return (media.get("format") or "").upper() in ("TV", "TV_SHORT", "ONA")


def season_of(month: int) -> str:
    if month in (1, 2, 3):
        return "WINTER"
    if month in (4, 5, 6):
        return "SPRING"
    if month in (7, 8, 9):
        return "SUMMER"
    return "FALL"


def clean_html(text: str | None) -> str | None:
    """AniList trả description dạng HTML nhẹ (<br>, <i>, <a>…). App render Text
    thuần nên phải strip tag, giữ lại nội dung. Trả None nếu rỗng.
    """
    if not text:
        return None
    import re
    s = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&amp;", "&").replace("&quot;", '"').replace("&#039;", "'")
          .replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " "))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s or None


def slugify(text: str, fallback_id: int) -> str:
    import re
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or f"anime-{fallback_id}"


def to_anime_row(m: Dict) -> Dict:
    """Chuẩn hoá media của AniList → row cho bảng `anime`."""
    t = m.get("title") or {}
    studio_nodes = ((m.get("studios") or {}).get("nodes") or [])
    return {
        "anilist_id": m["id"],
        "mal_id": m.get("idMal"),
        "slug": slugify(t.get("romaji") or t.get("english") or "", m["id"]),
        "title_romaji": t.get("romaji") or t.get("english") or f"anime-{m['id']}",
        "title_english": t.get("english"),
        "title_native": t.get("native"),
        "cover_url": (m.get("coverImage") or {}).get("extraLarge")
                     or (m.get("coverImage") or {}).get("large"),
        "banner_url": m.get("bannerImage"),
        "year": m.get("seasonYear"),
        "season": m.get("season"),
        "status": m.get("status"),
        "format": m.get("format"),
        "episodes_total": m.get("episodes"),
        "duration_min": m.get("duration"),
        # AniList trả 0–100 → app dùng thang 0–10
        "score": round(m["averageScore"] / 10, 1) if m.get("averageScore") else None,
        "popularity": m.get("popularity") or 0,
        "genres": m.get("genres") or [],
        # AniList có sẵn mô tả (thường tiếng Anh) → dùng làm nội dung dự phòng khi
        # chưa có bản dịch tiếng Việt. Trước đây field này bị vứt đi nên
        # `synopsis` trong API LUÔN rỗng → trang chi tiết trống phần giới thiệu.
        "synopsis_original": clean_html(m.get("description")),
        "studios": [n["name"] for n in studio_nodes if n.get("name")],
        "source": "anilist",
        "last_synced_at": None,   # Postgres tự set bằng now() ở tầng dưới
    }


def to_iso(ts: Any) -> Optional[str]:
    """AniList trả `airingAt` là epoch GIÂY (int). Cột `airing_at` là timestamptz
    nên Postgres cần chuỗi ISO 8601 — gửi số thô sẽ bị
    `22008 date/time field value out of range: "1793536200"` và chết cả job A.
    """
    if ts is None or ts == "":
        return None
    if isinstance(ts, str):
        return ts
    return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).isoformat()


def to_episode_row(anime_id: int, number: int, airing_at: Any, title: str = "") -> Dict:
    return {
        "anime_id": anime_id,
        "number": number,
        "airing_at": to_iso(airing_at),
        "title": title or None,
    }
