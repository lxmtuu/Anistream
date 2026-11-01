"""
youtube_api.py — YouTube Data API v3 (miễn phí 10.000 quota/ngày).

Vì sao cần: RSS (`feeds/videos.xml`) chỉ trả **15 video mới nhất** của mỗi kênh.
Đó là lý do app chỉ thấy 1–4 tập của mỗi bộ. API cho phép lấy **toàn bộ lịch sử**
của kênh (playlist "uploads"), nên có thể backfill hàng nghìn tập.

Chi phí quota (rất rẻ):
  channels.list      1 unit  → lấy uploads playlist id (1 lần/kênh)
  playlistItems.list 1 unit  → 50 video  → 1.000 video = 20 unit
  videos.list        1 unit  → 50 video  → kiểm tra `status.embeddable` + thời lượng
  → 10.000 unit/ngày đủ index ~150.000 video. Không bao giờ chạm trần.

Không có key thì `collect()` tự quay về RSS (hành vi cũ).

Tạo key (2 phút): https://console.cloud.google.com → New project →
APIs & Services → Library → "YouTube Data API v3" → Enable →
Credentials → Create credentials → API key. Rồi thêm vào .env:
    YOUTUBE_API_KEY=AIza...
"""
import json
import re
from typing import Dict, List, Optional

import requests

from . import config

API = "https://www.googleapis.com/youtube/v3"
RE_DURATION = re.compile(
    r"^P(?:(?P<d>\d+)D)?T?(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?$"
)


def has_key() -> bool:
    return bool(config.YOUTUBE_API_KEY)


def parse_iso8601_duration(value: str) -> int:
    """'PT1H24M10S' → 5050 (giây). Trả 0 nếu không hiểu."""
    if not value:
        return 0
    m = RE_DURATION.match(value)
    if not m:
        return 0
    d = int(m.group("d") or 0)
    h = int(m.group("h") or 0)
    mi = int(m.group("m") or 0)
    s = int(m.group("s") or 0)
    return d * 86400 + h * 3600 + mi * 60 + s


# 3 lỗi gặp nhiều nhất khi mới tạo key, mỗi lỗi cần một cách xử lý KHÁC nhau.
# Google chỉ trả JSON `error.errors[0].reason`, không nói tiếng Việt — nên dịch.
_KEY_ERRORS = {
    "keyInvalid": (
        "API key không hợp lệ. Sao chép lại key ở Google Cloud Console → "
        "APIs & Services → Credentials (đừng copy thừa dấu cách/xuống dòng)."
    ),
    "API_KEY_INVALID": "API key không hợp lệ (kiểm lại chuỗi key).",
    "accessNotConfigured": (
        "Dự án CHƯA BẬT \"YouTube Data API v3\". Vào console.cloud.google.com → "
        "APIs & Services → Library → tìm \"YouTube Data API v3\" → Enable. "
        "Đợi ~1 phút rồi chạy lại (key cũ vẫn dùng được, không cần tạo key mới)."
    ),
    "SERVICE_DISABLED": (
        "API chưa được bật cho dự án này → Library → \"YouTube Data API v3\" → Enable."
    ),
    "quotaExceeded": (
        "Hết quota 10.000 unit/ngày (reset 00:00 giờ Thái Bình Dương). "
        "Chạy lại sau, hoặc bỏ cờ --deep cho lần chạy này."
    ),
    "dailyLimitExceeded": "Hết quota ngày hôm nay — chạy lại sau (reset 00:00 PT).",
    "ipRefererBlocked": (
        "Key bị giới hạn theo IP/referrer. Sửa ở Credentials → chọn key → "
        "Application restrictions → None (hoặc thêm IP máy bạn)."
    ),
    "forbidden": "Bị từ chối (403). Kiểm tra key + xem API đã bật chưa.",
}


def _explain_error(status: int, body: str) -> str:
    """Đổi body lỗi JSON của Google thành câu người đọc hiểu được."""
    reason, message = "", ""
    try:
        err = (json.loads(body).get("error") or {})
        message = err.get("message") or ""
        errs = err.get("errors") or []
        if errs:
            reason = errs[0].get("reason") or ""
        if not reason:
            reason = err.get("status") or ""
    except Exception:
        pass

    hint = _KEY_ERRORS.get(reason)
    if not hint:
        low = f"{reason} {message}".lower()
        for k, v in _KEY_ERRORS.items():
            if k.lower() in low:
                hint = v
                break
    if not hint:
        hint = "Xem chi tiết ở body bên dưới (thường gặp: key sai, chưa bật API, hết quota)."
    return f"YouTube API lỗi {status} [{reason or 'unknown'}]: {hint}\n  body: {body[:300]}"


def _get(path: str, **params) -> Dict:
    if not config.YOUTUBE_API_KEY:
        raise RuntimeError(
            "Thiếu YOUTUBE_API_KEY.\n"
            "  → Lấy key miễn phí: https://console.cloud.google.com → New project →\n"
            "    APIs & Services → Library → \"YouTube Data API v3\" → Enable →\n"
            "    Credentials → Create credentials → API key\n"
            "  → Thêm vào .env:  YOUTUBE_API_KEY=AIza...\n"
            "  → Không có key thì bỏ cờ --deep (chỉ dùng RSS: 15 video/kênh)."
        )
    params["key"] = config.YOUTUBE_API_KEY
    r = requests.get(
        f"{API}/{path}",
        params=params,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(_explain_error(r.status_code, r.text))
    return r.json()


def uploads_playlist_id(channel_id: str) -> Optional[str]:
    """Lấy playlist chứa TẤT CẢ video đã đăng của kênh."""
    data = _get("channels", part="contentDetails", id=channel_id)
    items = data.get("items") or []
    if not items:
        return None
    return (
        items[0].get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )


def list_videos(playlist_id: str, max_videos: int = 200) -> List[Dict]:
    """Liệt kê video trong playlist 'uploads', tự phân trang."""
    out: List[Dict] = []
    page_token = None
    while len(out) < max_videos:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_videos - len(out)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get("playlistItems", **params)
        for it in data.get("items") or []:
            sn = it.get("snippet") or {}
            cd = it.get("contentDetails") or {}
            vid = cd.get("videoId") or sn.get("resourceId", {}).get("videoId")
            if not vid:
                continue
            out.append({
                "video_id": vid,
                "title": sn.get("title") or "",
                "published": sn.get("publishedAt") or cd.get("videoPublishedAt") or "",
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def video_details(video_ids: List[str]) -> Dict[str, Dict]:
    """
    Kiểm tra `embeddable` + thời lượng theo lô 50 video (1 unit/lô).
    Trả {video_id: {embeddable: bool, duration: int, live: bool}}
    """
    out: Dict[str, Dict] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        data = _get(
            "videos",
            part="status,contentDetails",
            id=",".join(chunk),
            maxResults=50,
        )
        for it in data.get("items") or []:
            vid = it.get("id")
            if not vid:
                continue
            status = it.get("status") or {}
            cd = it.get("contentDetails") or {}
            out[vid] = {
                "embeddable": bool(status.get("embeddable", True)),
                "privacy": status.get("privacyStatus"),
                "duration": parse_iso8601_duration(cd.get("duration", "")),
                "live": bool(((it.get("snippet") or {}).get("liveBroadcastContent")
                              or cd.get("definition") == "live")),
            }
    return out
