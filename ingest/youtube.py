"""
youtube.py — Lấy video official (miễn phí, hợp pháp) từ RSS của các kênh publisher/Muse/Ani-One.

Vì sao hợp pháp:
  • Đây là video do chủ kênh đăng CÔNG KHAI, app chỉ NHÚNG bằng IFrame Player API chính thức.
  • Không trích xuất stream (không dùng youtube_explode/yt-dlp) → không vi phạm ToS YouTube.
  • Không chặn quảng cáo của họ.

Cách hoạt động (0 API key, 0 đồng):
  1. GET https://www.youtube.com/feeds/videos.xml?channel_id=<UC...>
  2. Parse tiêu đề → (tên series, số tập)
  3. GET https://www.youtube.com/oembed?url=...  → 200 = cho nhúng, 401 = chủ video tắt nhúng
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import requests

from . import config, youtube_api

# Kênh official đã kiểm tra tồn tại (channel_id lấy từ trang kênh, 01/11/2026)
CHANNELS: List[Dict] = [
    {"key": "muse_vn",       "name": "Muse Việt Nam",  "channel_id": "UCott96qGP5ADmsB_yNQMvDA", "region": "VN"},
    {"key": "ani_one_asia",  "name": "Ani-One Asia",   "channel_id": "UC45ONEZZfMDZCnEhgYmVu-A", "region": "AS"},
    # Thêm kênh khác tại đây. Lấy channel_id bằng: curl -s <url kênh> | grep -o '"channelId":"UC[^"]*"'
]


def enabled_channels() -> List[Dict]:
    """Kênh đang bật, theo `YOUTUBE_CHANNELS` (mặc định chỉ `muse_vn`).

    Tên kênh sai chính tả mà im lặng bỏ qua là kiểu lỗi tệ nhất (chạy "thành công"
    mà không lấy được gì) → nổ ngay kèm danh sách hợp lệ.
    """
    wanted, out = config.YOUTUBE_CHANNELS, []
    known = {c["key"]: c for c in CHANNELS}
    unknown = [k for k in wanted if k not in known]
    if unknown:
        raise RuntimeError(
            f"YOUTUBE_CHANNELS có kênh không tồn tại: {', '.join(unknown)}. "
            f"Hợp lệ: {', '.join(known)}"
        )
    for k in wanted:
        out.append(known[k])
    return out

# Tiêu đề chứa các từ này → KHÔNG phải tập phim đầy đủ → bỏ
SKIP_WORDS = [
    "shorts", "trailer", "teaser", "pv", "預告", "預告片", "精華", "精華重溫",
    "recap", "digest", "総集編", "回顧", "announce", "teaser pv", "spot", "cm",
    "behind the scenes", "interview", "phỏng vấn", "hậu trường",
    "khoảnh khắc nổi bật", "trích đoạn", "đoạn trích", "tóm tắt", "review",
    "系列", "合集", "總集", "总集", "全集", "compilation", "playlist",
]

# 第12話 / 第12话 / 第12集  |  Episode 12 |  - Ep 12 |  (S1E12)
# Dải tập: "Tập 01-24", "第01-26話", "Ep 5-8". Muse/Ani-One hay đăng BẢN GỘP nhiều
# tập trong 1 video. Ca thật: "[Bản Lồng Tiếng] One Punch Man - Tập 01-24" từng bị
# parse thành episode 1 → app ghi "Tập 1" nhưng bấm vào là video 24 tập.
_RANGE = r"(?:\s*[-–—~]\s*(\d{1,4}))?"
RE_CN_EP = re.compile(r"第\s*(\d{1,4})" + _RANGE + r"\s*[話话集]")
RE_VI_EP = re.compile(r"(?:^|[\s\-–—:|])tập\s*(\d{1,4})" + _RANGE + r"(?!\d)",
                      re.IGNORECASE)
RE_EN_EP = re.compile(r"(?:^|[\s\-–—:|])(?:episode|ep)\.?\s*(\d{1,4})" + _RANGE,
                      re.IGNORECASE)
RE_SxE   = re.compile(r"\(S\d+\s*E(\d{1,3})\)", re.IGNORECASE)
# Mùa được viết nhiều kiểu; Muse VN dùng "Mùa 2" (tiếng Việt) là chính.
# Bổ sung 03/11/2026: Muse VN viết tắt trần "S4" — "Re:Zero - ... S4 - Tập 83".
# Trước đây chỉ nhận "(S4)" có NGOẶC, nên "S4" dính vào tên bộ → không khớp được
# bộ nào (Re:Zero mùa 4 trong DB có 0 link dù kênh đăng đủ tập).
RE_SEASON = re.compile(
    r"(?:\(S(?P<paren>\d+)\)"
    r"|(?:^|[\s\-–—:|])s(?P<short>\d{1,2})(?![\w\d])"
    r"|(?:^|[\s\-–—:|])(?:mùa|mua|season|phần|phan)\s*(?P<word>\d{1,2})\b)",
    re.IGNORECASE,
)

BRACKETS = [
    re.compile(r"【[^】]*】"), re.compile(r"\[[^\]]*\]"),
    re.compile(r"（[^）]*）"), re.compile(r"\([^)]*\)"),
    re.compile(r"《|》"),
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def is_skippable(title: str) -> bool:
    low = _norm(title).lower()
    return any(w in low for w in SKIP_WORDS)


def parse_title(raw: str) -> Optional[Dict]:
    """
    Trả về {'series': str, 'episode': int|0, 'season': int|None, 'kind': 'episode'|'series'}
    episode = 0 nghĩa là link cho cả bộ (movie / complete series / limited-time).
    Trả None nếu không nhận dạng được hoặc là trailer/shorts.
    """
    title = _norm(raw)
    if not title or is_skippable(title):
        return None

    # Năm trong tiêu đề ("Hunter x Hunter (2011)", "Fairy Tail 2014") là thông tin
    # rất mạnh để phân biệt bản 1999 và bản 2011 — lấy TRƯỚC khi xoá ngoặc.
    m_year = re.search(r"\(((?:19|20)\d{2})\)|(?<!\d)((?:19|20)\d{2})(?!\d)", title)
    year = None
    if m_year:
        raw_year = "".join(g for g in m_year.groups() if g)
        year = int(raw_year) if len(raw_year) == 4 else None
        if year and not (1950 <= year <= 2100):
            year = None

    season = None
    m_season = RE_SEASON.search(title)
    if m_season:
        season = int(m_season.group("paren") or m_season.groupdict().get("short")
                     or m_season.group("word"))

    # 1) số tập (có thể là DẢI TẬP — xem `_RANGE`)
    episode = 0
    cut_at = None
    for rx in (RE_CN_EP, RE_VI_EP, RE_EN_EP, RE_SxE):
        m = rx.search(title)
        if not m:
            continue
        groups = m.groups()
        start = int(groups[0])
        end = int(groups[1]) if len(groups) > 1 and groups[1] else None
        if end is not None and end > start:
            if start <= 1:
                # Bản gộp CẢ BỘ → đúng nghĩa "link cho cả bộ" (episode_number = 0).
                episode = 0
            else:
                # Bản gộp MỘT PHẦN (vd "Tập 1000-1099"): không có số tập nào đúng
                # để gán. Gán start sẽ nói dối và ghi đè link tập thật → bỏ qua.
                return None
        else:
            episode = start
        cut_at = m.start()
        break

    # 2) tên series = phần trước chỗ có số tập
    head = title[:cut_at] if cut_at is not None else title

    # bỏ ngoặc, ký hiệu
    for rx in BRACKETS:
        head = rx.sub(" ", head)
    head = re.sub(r"^[\s\-–—:|]+", "", head)
    head = re.sub(r"[\s\-–—:|]+$", "", head)
    head = re.sub(r"\s{2,}", " ", head).strip()
    # tên gốc không kèm "Mùa 2" — dùng để tìm bộ trên AniList khi bộ mùa đó
    # chưa có trong DB
    base = RE_SEASON.sub(" ", head)
    base = re.sub(r"[\s\-–—:|]+$", "", re.sub(r"^[\s\-–—:|]+", "", base)).strip()

    if len(head) < 2:
        return None

    kind = "episode" if episode > 0 else "series"
    return {"series": head, "series_base": base or head,
            "episode": episode, "season": season, "year_hint": year, "kind": kind}


def fetch_rss(channel_id: str, limit: int = 25) -> List[Dict]:
    """RSS chính thức của YouTube — không cần API key."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                     timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom",
          "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
    root = ET.fromstring(r.content)
    out = []
    for e in root.findall("a:entry", ns)[:limit]:
        vid = e.find("yt:videoId", ns)
        ttl = e.find("a:title", ns)
        pub = e.find("a:published", ns)
        views = e.find("media:group/media:community/media:statistics", ns)
        if vid is None or ttl is None:
            continue
        out.append({
            "video_id": vid.text,
            "title": ttl.text or "",
            "published": pub.text if pub is not None else "",
            "views": int(views.get("views", 0)) if views is not None else 0,
            "url": f"https://www.youtube.com/watch?v={vid.text}",
        })
    return out


def is_embeddable(video_id: str) -> bool:
    """
    Kiểm tra video có cho nhúng không.
      oEmbed chỉ là kiểm tra sơ bộ; HTTP 200 không đảm bảo có thể nhúng hay xem theo vùng.
    """
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        return r.status_code == 200
    except Exception:
        return False


def collect_channel(
    ch: Dict,
    limit_per_channel: int = 25,
    check_embed: bool = True,
    verbose: bool = True,
    deep: bool = False,
    max_per_channel: int = 5000,
) -> List[Dict]:
    """Video của MỘT kênh. Ném lỗi nếu không lấy được (để job ghi nhận kênh hỏng).

    Tách riêng khỏi `collect()` để job có thể GHI DB từng kênh một: chạy 2 kênh
    × 5.000 video mà chỉ ghi ở cuối thì mất mạng ở kênh thứ 2 là mất cả kênh 1.
    """
    use_api = deep and youtube_api.has_key()
    details = {}
    if use_api:
        pl = youtube_api.uploads_playlist_id(ch["channel_id"])
        if not pl:
            raise RuntimeError(f"không tìm thấy uploads playlist: {ch['name']}")
        entries = youtube_api.list_videos(pl, max_videos=max_per_channel)
        # kiểm tra nhúng + thời lượng theo lô 50 (rẻ hơn oEmbed rất nhiều)
        details = youtube_api.video_details([e["video_id"] for e in entries])
    else:
        entries = fetch_rss(ch["channel_id"], limit=limit_per_channel)

    if verbose:
        mode = f"API (tối đa {max_per_channel})" if use_api else "RSS"
        print(f"  · {ch['name']} [{mode}]: {len(entries)} video")

    out: List[Dict] = []
    for e in entries:
        parsed = parse_title(e["title"])
        if not parsed or parsed["episode"] <= 0:
            continue

        if use_api:
            d = details.get(e["video_id"]) or {}
            if d and not d.get("embeddable", True):
                if verbose:
                    print(f"    ✗ tắt nhúng: {e['title'][:60]}")
                continue
            # bỏ shorts / clip ngắn: tập anime thật thường >= 4 phút
            dur = d.get("duration", 0)
            if dur and dur < 240:
                continue
            e["duration"] = dur
        elif check_embed and not is_embeddable(e["video_id"]):
            if verbose:
                print(f"    ✗ tắt nhúng: {e['title'][:60]}")
            continue
        parsed.update({
            "channel": ch["key"],
            "channel_name": ch["name"],
            "region": ch["region"],
            "video_id": e["video_id"],
            "url": e["url"],
            "raw_title": e["title"],
            "published": e["published"],
            "views": e.get("views", 0),
            "duration": e.get("duration"),
        })
        out.append(parsed)
        if verbose:
            print(f"    ✓ ep{str(parsed['episode']).rjust(3)} · {parsed['series'][:52]}")
    return out


def collect(limit_per_channel: int = 25, check_embed: bool = True,
            verbose: bool = True, deep: bool = False,
            max_per_channel: int = 5000) -> List[Dict]:
    """
    Gom video official từ mọi kênh, parse tiêu đề, kiểm tra cho nhúng.

    deep=False → chỉ RSS (15 video mới nhất/kênh): nhanh, dùng cho cron 6h.
    deep=True  → YouTube Data API: lấy TOÀN BỘ lịch sử kênh (cần YOUTUBE_API_KEY).
                 Dùng cho lần backfill đầu tiên — đây là cách có hàng nghìn tập.
    """
    if deep and not youtube_api.has_key():
        print("  ⚠ deep=True nhưng thiếu YOUTUBE_API_KEY → quay về RSS (chỉ 15 video/kênh)")
    result, failures = [], []
    for ch in CHANNELS:
        try:
            result.extend(collect_channel(ch, limit_per_channel, check_embed,
                                          verbose, deep, max_per_channel))
        except Exception as e:
            print(f"  ! lỗi lấy video {ch['name']}: {e}")
            failures.append(ch["name"])
    if failures:
        raise RuntimeError("Không lấy được RSS/API: " + ", ".join(failures))
    return result
