"""
tmdb.py — Bổ sung dữ liệu TIẾNG VIỆT từ TMDB: tên, tóm tắt, danh sách tập.

Vì sao cần: AniList không có tiếng Việt, nên app toàn hiện `Kusuriya no Hitorigoto`
thay vì "Dược Sư Tự Sự", và 79/104 anime không có tập nào để bấm.

Cách làm (rẻ → đắt, ~3 request/anime):
    /search/tv        tìm theo tên (english → romaji → native) + năm
    /tv/{id}          chi tiết + alternative_titles + translations (vi, VN)
    /tv/{id}/season/1 danh sách tập (CHỈ khi phim có đúng 1 mùa)

Quy tắc chống rác (quan trọng — thà thiếu còn hơn sai):
  · Nếu không chắc tên/năm thì BỎ QUA, đếm vào `chưa khớp`, không đoán bừa.
  · KHÔNG ghi đè dữ liệu đã có (title_vi/synopsis_vi do người biên tập).
  · TMDB gộp cả series vào 1 id, AniList tách từng mùa. Phải CHỌN ĐÚNG MÙA
    (`pick_season`: mùa duy nhất → khớp năm → khớp số tập → bỏ) rồi mới lấy
    `episodes_total` + danh sách tập. Không chắc thì để trống, không đoán.
  · TMDB trả nhiều tập hơn hẳn AniList (`episodes_plausible`) → không ghi.
"""
import datetime as dt
import re
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests

from . import config

ENDPOINT = "https://api.themoviedb.org/3"

# Ngưỡng ghép tên. Thấp hơn match.THRESHOLD của YouTube vì ở đây ta còn ràng
# buộc thêm NĂM phát sóng, nên rủi ro nhầm bộ khác là thấp.
TITLE_THRESHOLD = 0.80
YEAR_TOLERANCE = 2
SLEEP_BETWEEN = 0.06          # TMDB cho ~50 req/s; 0.06s là lịch sự


class TmdbError(RuntimeError):
    """Lỗi gọi TMDB — luôn nổi lên (không nuốt), kèm mã HTTP."""


def is_configured() -> bool:
    return bool(config.TMDB_API_KEY)


# ─────────────────────────────────────────── HTTP
def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not is_configured():
        raise TmdbError(
            "Thiếu TMDB_API_KEY.\n"
            "  → Lấy key miễn phí: https://www.themoviedb.org/settings/api\n"
            "  → Thêm vào .env:  TMDB_API_KEY=xxxxxxxx\n"
            "  → Hoặc chạy `python3 -m ingest.main all` (job tmdb sẽ được bỏ qua kèm cảnh báo)."
        )
    q = {"api_key": config.TMDB_API_KEY, "language": "vi-VN"}
    q.update(params or {})
    r = requests.get(f"{ENDPOINT}{path}", params=q, timeout=config.HTTP_TIMEOUT)
    if r.status_code == 401:
        raise TmdbError(
            "TMDB_API_KEY không hợp lệ (401). Kiểm lại key trong .env — "
            "phải là API Key (v3), không phải Read Access Token (v4)."
        )
    if r.status_code == 429:
        raise TmdbError("TMDB trả 429 (quá nhiều request). Chạy lại sau vài phút.")
    if r.status_code != 200:
        raise TmdbError(f"TMDB {path} → HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


# ─────────────────────────────────────────── chuẩn hoá để so tên
_ARTICLES = re.compile(r"^(the|a|an)\s+", re.I)


def norm(s: str) -> str:
    """Bỏ dấu câu, chữ thường, bỏ 'season N'/'2nd season' — để so tên cho công bằng."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = _ARTICLES.sub("", s)
    s = re.sub(r"\b\d+(st|nd|rd|th)\s+season\b", " ", s)
    s = re.sub(r"\b(season|part|phần)\s*\d+\b", " ", s)
    s = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _year_of(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    m = re.match(r"(\d{4})", date_str)
    return int(m.group(1)) if m else None


# Từ nối quá phổ biến để coi là "dấu hiệu nhận dạng" tên phim
_STOP = {
    "no", "the", "a", "an", "of", "and", "to", "in", "on", "wa", "ga", "wo",
    "ni", "de", "to", "mo", "ka", "san", "kun", "chan", "sama", "season",
}


def _tokens(s: str) -> set:
    return set(norm(s).split())


def _distinctive(s: str) -> set:
    """Token đủ dài để coi là tên riêng (bỏ 'no', 'the', 'season'…)."""
    return {t for t in norm(s).split() if len(t) >= 4 and t not in _STOP}


def title_score(titles: List[str], result: Dict[str, Any], year: Optional[int]) -> float:
    """Điểm giống tên giữa row của ta và 1 kết quả TMDB.

    Ngoài tỉ lệ ký tự (SequenceMatcher), còn nhận 2 trường hợp mờ (đều BẮT BUỘC
    đúng năm, vì đó là thứ chặn nhầm "Naruto" với "Naruto Shippuden"):
    thực tế AniList ghi `Sousou no Frieren`, TMDB ghi
    `Frieren: Beyond Journey's End` — tỉ lệ ký tự chỉ ~0.38 nên nếu chỉ dùng
    SequenceMatcher sẽ trượt gần hết.

    NHƯNG chứa-trong rất dễ nhầm phần tiếp theo (`Naruto` ⊂ `Naruto Shippuden`),
    nên nó **chỉ được tính khi năm khớp** (±1). Sai năm → không nhận.
    """
    names = [result.get("name"), result.get("original_name")]
    pairs = [(t, n) for t in titles for n in names if t and n]
    best = max((similarity(t, n) for t, n in pairs), default=0.0)
    if best >= TITLE_THRESHOLD:
        return best

    ry = _year_of(result.get("first_air_date"))
    if not (year and ry and abs(ry - year) <= 1):
        return best                     # các luật "mờ" dưới đây BẮT BUỘC đúng năm

    for t in titles:
        tt_all, tt = _tokens(t), _distinctive(t)
        if not tt_all:
            continue
        for n in names:
            if not n:
                continue
            nn_all, nn = _tokens(n), _distinctive(n)
            if not nn_all:
                continue

            # (a) một tên nằm trọn trong tên kia: "Frieren" ⊂ "Frieren: Beyond…"
            short_all, long_all = ((tt_all, nn_all) if len(tt_all) <= len(nn_all)
                                   else (nn_all, tt_all))
            if short_all <= long_all:
                return 0.86

            # (b) tên khác trật tự/khác phần phụ nhưng trùng ≥50% từ khoá riêng:
            #     AniList "Sousou no Frieren" ↔ TMDB "Frieren: Beyond Journey's End"
            if tt and nn:
                chung = tt & nn
                if chung and len(chung) / min(len(tt), len(nn)) >= 0.5:
                    return 0.84
    return best


def pick_best(
    results: List[Dict[str, Any]],
    titles: List[str],
    year: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], float]:
    """Chọn kết quả TMDB khớp nhất. Trả (result | None, điểm).

    `titles` = các tên ta có (english, romaji, native) — lấy điểm cao nhất.
    """
    best, best_score = None, 0.0
    for r in results or []:
        score = title_score(titles, r, year)
        if score < TITLE_THRESHOLD:
            continue
        ry = _year_of(r.get("first_air_date"))
        if year and ry and abs(ry - year) > YEAR_TOLERANCE:
            continue                      # khác năm quá xa → gần như chắc chắn khác bộ
        if year and ry and abs(ry - year) <= 1:
            score += 0.05                 # ưu tiên đúng năm
        score += min(r.get("popularity") or 0, 100) / 10000.0
        if score > best_score:
            best, best_score = r, score
    return best, round(min(best_score, 1.0), 3)


# ─────────────────────────────────────────── lấy dữ liệu tiếng Việt
def extract_vietnamese(detail: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Trả (title_vi, overview_vi) — ưu tiên bản dịch `vi`, rồi tên thay thế VN.

    TMDB rất hay trả bản dịch tiếng Việt RỖNG (`name: ""`), nên phải kiểm nội dung
    chứ không chỉ kiểm sự tồn tại của mục `vi`.
    """
    name = overview = None

    tr = (detail.get("translations") or {}).get("translations") or []
    for t in tr:
        if t.get("iso_639_1") != "vi":
            continue
        data = t.get("data") or {}
        if (data.get("name") or "").strip():
            name = data["name"].strip()
        if (data.get("overview") or "").strip():
            overview = data["overview"].strip()
        break

    if not name:
        alt = (detail.get("alternative_titles") or {}).get("results") or []
        for a in alt:
            if a.get("iso_3166_1") == "VN" and (a.get("title") or "").strip():
                name = a["title"].strip()
                break

    # Không coi "bản dịch" trùng y nguyên tên gốc là tiếng Việt
    original = (detail.get("name") or "").strip()
    if name and original and norm(name) == norm(original):
        name = None
    return name or None, overview or None


# ─────────────────────────────────────────── ghép kết quả thành patch DB
def build_anime_patch(
    row: Dict[str, Any],
    detail: Dict[str, Any],
    title_vi: Optional[str],
    overview_vi: Optional[str],
    single_season: bool,
    episodes_total_hint: Optional[int] = None,
) -> Dict[str, Any]:
    """Chỉ điền chỗ TRỐNG. Không bao giờ ghi đè dữ liệu đã có."""
    patch: Dict[str, Any] = {}

    if not row.get("tmdb_id"):
        patch["tmdb_id"] = detail.get("id")

    if not (row.get("title_vi") or "").strip() and title_vi:
        patch["title_vi"] = title_vi

    if not (row.get("synopsis_vi") or "").strip() and overview_vi:
        patch["synopsis_vi"] = overview_vi

    # Chỉ tin số tập khi đã xác định được ĐÚNG mùa ứng với entry AniList.
    # `number_of_episodes` là tổng của CẢ series → sai với entry "mùa 2";
    # nên ưu tiên số tập của mùa đã chọn (`episodes_total_hint`).
    total = episodes_total_hint if isinstance(episodes_total_hint, int) and episodes_total_hint > 0 \
        else detail.get("number_of_episodes")
    if single_season and not row.get("episodes_total") and isinstance(total, int) and total > 0:
        patch["episodes_total"] = total

    return {k: v for k, v in patch.items() if v is not None}


# TMDB trả tên placeholder khi chưa có bản dịch: "Episode 7", "Ep. 7", "Tập 7",
# "第7話". Đo trên DB thật: 429/526 tên tập là dạng này → app hiện dòng chữ vô
# nghĩa trùng với con số to ở trên. Thà để trống (ô chỉ hiện số tập).
GENERIC_EP_TITLE = re.compile(
    r"^\s*(?:episode|ep\.?|tập|tap|第)?\s*\d+\s*(?:話|话|集)?\s*$",
    re.IGNORECASE,
)


def clean_episode_title(name: Optional[str]) -> Optional[str]:
    """Tên tập dùng được? Placeholder ("Episode 7") → None."""
    t = (name or "").strip()
    if not t or GENERIC_EP_TITLE.match(t):
        return None
    return t


def episode_rows(
    anime_id: int,
    season: Dict[str, Any],
    single_season: bool,
) -> List[Dict[str, Any]]:
    """Đổi season TMDB → rows cho bảng `episodes`. Bỏ qua nếu không đủ tin cậy."""
    if not single_season:
        return []   # chưa xác định được mùa → không ghi tập (tránh gán tập mùa khác)
    out = []
    for e in season.get("episodes") or []:
        num = e.get("episode_number")
        if not isinstance(num, int) or num <= 0:
            continue
        air = e.get("air_date")
        if not air:
            continue                      # chưa có ngày chiếu → đừng bịa
        row = {
            "anime_id": anime_id,
            "number": num,
            "airing_at": dt.datetime.fromisoformat(air).replace(
                tzinfo=dt.timezone.utc).isoformat(),
        }
        # Tên placeholder ("Episode 7") → KHÔNG gửi khoá `title`. Gửi None sẽ
        # ghi NULL đè lên tên thật do Jikan điền (upsert merge-duplicates).
        title = clean_episode_title(e.get("name"))
        if title:
            row["title"] = title
        out.append(row)
    out.sort(key=lambda r: r["number"])
    return out


def real_seasons(detail: Dict[str, Any]) -> List[int]:
    """Số mùa thật (bỏ season 0 = specials)."""
    return sorted(
        s["season_number"] for s in (detail.get("seasons") or [])
        if isinstance(s.get("season_number"), int) and s["season_number"] > 0
    )


def season_candidates(detail: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Các mùa thật (bỏ specials) kèm số tập + ngày chiếu.

    AniList tách mỗi mùa thành MỘT entry riêng ("… 2nd Season"), còn TMDB gộp
    cả series vào một id nhiều mùa. Muốn lấy đúng danh sách tập thì phải biết
    entry AniList đang nói tới mùa nào — xem `pick_season`.
    """
    out = []
    for s in detail.get("seasons") or []:
        n = s.get("season_number")
        if not isinstance(n, int) or n <= 0:
            continue
        out.append({
            "number": n,
            "count": s.get("episode_count"),
            "air_date": (s.get("air_date") or ""),
        })
    return sorted(out, key=lambda x: x["number"])


def _year_of(date_str: str) -> Optional[int]:
    m = re.match(r"^(\d{4})", date_str or "")
    return int(m.group(1)) if m else None


def pick_season(
    detail: Dict[str, Any],
    year: Optional[int] = None,
    episodes_total: Optional[int] = None,
) -> Tuple[Optional[int], str]:
    """Chọn mùa TMDB ứng với 1 entry AniList. Trả (season_number | None, lý do).

    Thứ tự tin cậy:
      1. TMDB chỉ có 1 mùa            → mùa đó (chắc chắn)
      2. đúng 1 mùa có NĂM = năm AniList → mùa đó (Takagi-san 2018 → S1, không phải S3)
      3. đúng 1 mùa có SỐ TẬP = số tập AniList → mùa đó
      4. còn lại → None. KHÔNG đoán: thà trống còn hơn gán tập của mùa khác.
    """
    seasons = season_candidates(detail)
    if not seasons:
        return None, "TMDB không có mùa nào"
    if len(seasons) == 1:
        return seasons[0]["number"], "mùa duy nhất"

    if year:
        by_year = [s for s in seasons if _year_of(s["air_date"]) == int(year)]
        if len(by_year) == 1:
            return by_year[0]["number"], f"khớp năm {year}"

    if episodes_total:
        by_count = [s for s in seasons if s["count"] == int(episodes_total)]
        if len(by_count) == 1:
            return by_count[0]["number"], f"khớp {episodes_total} tập"

    return None, f"{len(seasons)} mùa, không xác định được mùa nào"


def episodes_plausible(
    episodes_total: Optional[int],
    season_count: int,
    tolerance: int = 2,
) -> bool:
    """Danh sách tập của mùa có hợp với số tập AniList biết không?

    - AniList biết tổng (vd 12) mà mùa TMDB trả 12  → hợp
    - phim đang chiếu: AniList ghi 12, TMDB mới có 8 → hợp (còn thiếu)
    - TMDB trả NHIỀU HƠN hẳn tổng (vd AniList 3, TMDB 12) → nghi lấy nhầm
      mùa/series → KHÔNG ghi, để trống (xem "Fool Night" trong BAN_LAM_TIEP).
    """
    if not episodes_total or season_count <= 0:
        return True
    return season_count <= int(episodes_total) + tolerance


# ─────────────────────────────────────────── API mức cao (1 anime)
def match_anime(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """Tìm phim trên TMDB cho 1 row `anime`. Trả (result|None, điểm, cách thử)."""
    titles = [row.get("title_english"), row.get("title_romaji"), row.get("title_native")]
    titles = [t for t in titles if t]
    year = row.get("year")

    tried = []
    for t in titles:
        params: Dict[str, Any] = {"query": t}
        if year:
            params["first_air_date_year"] = year
        res = _get("/search/tv", params).get("results") or []
        tried.append(f"search[{t[:24]}]")
        best, score = pick_best(res, titles, year)
        if best:
            return best, score, tried[-1]
        # lần 2: bỏ ràng buộc năm (TMDB hay lệch năm với AniList)
        if year:
            time.sleep(SLEEP_BETWEEN)
            res2 = _get("/search/tv", {"query": t}).get("results") or []
            tried.append(f"search-noyear[{t[:24]}]")
            best2, score2 = pick_best(res2, titles, year)
            if best2:
                return best2, score2, tried[-1]
        time.sleep(SLEEP_BETWEEN)
    return None, 0.0, "+".join(tried) or "—"


def fetch_detail(tv_id: int) -> Dict[str, Any]:
    d = _get(f"/tv/{tv_id}", {"append_to_response": "alternative_titles,translations"})
    time.sleep(SLEEP_BETWEEN)
    return d


def fetch_season(tv_id: int, season_number: int = 1) -> Dict[str, Any]:
    s = _get(f"/tv/{tv_id}/season/{season_number}")
    time.sleep(SLEEP_BETWEEN)
    return s
