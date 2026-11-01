"""
jikan.py — Danh sách tập từ Jikan v4 (gương công khai của MyAnimeList).

Vì sao cần: AniList chỉ trả TỔNG số tập, không trả danh sách từng tập. TMDB có
danh sách tập nhưng hay thiếu bản dịch và đôi khi lệch mùa. Jikan lấp chỗ trống:
**miễn phí, không cần API key**, có `title` + `aired` cho từng tập, và tra theo
`mal_id` mà bảng `anime` đã lưu sẵn (`idMal` từ AniList) → không phải search tên.

Giới hạn của Jikan (ghi ở docs.jikan.moe): 3 request/giây, 60 request/phút.
Script tự giãn nhịp 0,4s/request và tôn trọng `Retry-After` khi bị 429.

Không dùng Jikan để lấy ảnh/nhân vật/thống kê — chỉ danh sách tập, đúng phạm vi
"metadata hợp pháp" của dự án.
"""
import datetime as dt
import time
from typing import Any, Dict, List, Optional

import requests

from . import config

API = "https://api.jikan.moe/v4"
MIN_INTERVAL = 0.4      # 3 req/s theo giới hạn Jikan
MAX_PAGES = 20          # 20 trang × 100 tập = quá đủ cho mọi bộ
_last_call = 0.0


class JikanError(RuntimeError):
    """Lỗi gọi Jikan — nổi lên để job biết mà báo, không nuốt."""


def _throttle() -> None:
    global _last_call
    wait = _last_call + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _get(path: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Dict:
    for attempt in range(retries):
        _throttle()
        r = requests.get(
            f"{API}{path}",
            params=params or {},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code == 429:
            raw = r.headers.get("Retry-After", "2")
            try:
                wait = int(float(raw))
            except (TypeError, ValueError):
                wait = 2
            time.sleep(wait)
            continue
        if r.status_code == 404:
            raise JikanError(f"Jikan 404: không có {path} (mal_id sai?)")
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.status_code != 200:
            raise JikanError(f"Jikan {path} → {r.status_code}: {r.text[:200]}")
        return r.json()
    raise JikanError(f"Jikan {path}: hết lượt thử lại (429/5xx liên tục)")


def episodes(mal_id: int) -> List[Dict]:
    """Toàn bộ tập của 1 bộ theo `mal_id`. Tự phân trang."""
    out: List[Dict] = []
    page = 1
    while page <= MAX_PAGES:
        data = _get(f"/anime/{int(mal_id)}/episodes", {"page": page})
        rows = data.get("data") or []
        out.extend(rows)
        paging = data.get("pagination") or {}
        if not paging.get("has_next_page") or not rows:
            break
        page += 1
    return out


def parse_aired(value: Optional[str]) -> Optional[str]:
    """'2018-01-08T00:00:00+00:00' → ISO có timezone (Postgres cần)."""
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.isoformat()


def episode_rows(
    anime_id: int,
    items: List[Dict],
    episodes_total: Optional[int] = None,
    skip_filler: bool = True,
) -> List[Dict]:
    """Đổi dữ liệu Jikan → rows cho bảng `episodes`.

    · bỏ tập `filler` (tập không có trong truyện) — AniList/TMDB cũng không tính
    · bỏ tập vượt `episodes_total` nếu biết tổng (chống lệch bộ/mùa)
    · tên placeholder ("Episode 5") bị loại, dùng `tmdb.clean_episode_title`
    """
    from .tmdb import clean_episode_title      # tránh import vòng

    out: List[Dict] = []
    for e in items:
        num = e.get("mal_id")
        if not isinstance(num, int) or num <= 0:
            continue
        if skip_filler and e.get("filler"):
            continue
        if episodes_total and num > int(episodes_total):
            continue
        out.append({
            "anime_id": anime_id,
            "number": num,
            "title": clean_episode_title(e.get("title")),
            "airing_at": parse_aired(e.get("aired")),
        })
    out.sort(key=lambda r: r["number"])
    return out


def is_configured() -> bool:
    """Jikan KHÔNG cần key — chỉ cần mạng."""
    return True
