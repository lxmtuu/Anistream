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
from typing import Any, Callable, Dict, List, Optional, Tuple

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


# Bộ đã hỏi TMDB cách đây bao lâu thì bỏ qua (tránh quét lại mãi thứ không đổi).
# Đo 02/11/2026: 161 bộ × ~5s = 792 giây cho **0 bản ghi** vì 44 bộ TMDB không có
# và 13 bộ không có bản dịch vi luôn thoả `title_vi.is.null`.
STALE_DAYS = 7
STALE_DAYS_RELEASING = 1


def stale_cutoff(days: int, now: Optional[dt.datetime] = None) -> str:
    """Mốc ISO (UTC) để so với `tmdb_checked_at`."""
    base = now or dt.datetime.now(dt.timezone.utc)
    return (base - dt.timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%S")


def now_iso() -> str:
    """Thời điểm hiện tại (UTC, ISO) để ghi `anime.tmdb_checked_at`."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def is_stale(checked_at: Optional[str], cutoff: str) -> bool:
    """Bộ này đã lâu chưa hỏi TMDB? (None = chưa từng hỏi → luôn xử lý)."""
    if not checked_at:
        return True
    # Supabase trả '2026-11-02T05:12:33.123456+00:00'; so sánh chuỗi ISO là đủ
    # khi cùng múi giờ, nhưng cắt về 19 ký tự cho chắc (bỏ microsecond + offset).
    return checked_at[:19] < cutoff[:19]


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


def pick_all(
    results: List[Dict[str, Any]],
    titles: List[str],
    year: Optional[int],
    limit: int = 5,
) -> List[Tuple[Dict[str, Any], float]]:
    """NHIỀU kết quả đạt ngưỡng, điểm giảm dần (khử trùng theo id).

    Vì sao cần: cùng một bộ, TMDB có thể trả **nhiều series** — đo 02/11/2026,
    "The Apothecary Diaries" trả cả 220542 (series chính, chỉ 1 mùa) và 333686.
    Trước đây chỉ thử kết quả điểm cao nhất; nếu series đó không có mùa cần tìm
    thì bộ bị bỏ trắng dù ứng viên khác có đủ mùa.
    """
    scored: List[Tuple[Dict[str, Any], float]] = []
    for r in results or []:
        score = title_score(titles, r, year)
        if score < TITLE_THRESHOLD:
            continue
        ry = _year_of(r.get("first_air_date"))
        if year and ry and abs(ry - year) > YEAR_TOLERANCE:
            continue
        if year and ry and abs(ry - year) <= 1:
            score += 0.05
        score += min(r.get("popularity") or 0, 100) / 10000.0
        scored.append((r, round(min(score, 1.0), 3)))
    scored.sort(key=lambda x: -x[1])
    out, seen = [], set()
    for r, sc in scored:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append((r, sc))
    return out[:limit]


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
# Ký tự CHỈ có trong tiếng Việt (dấu thanh + chữ đặc trưng). Dùng để phân biệt
# "tên Việt" với tên gốc TMDB trả về khi chưa có bản dịch (`name` fallback).
_VI_CHARS = set(
    "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữựỳýỷỹỵ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"
    "ÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
)


def looks_vietnamese(text: str) -> bool:
    """Chuỗi có dấu tiếng Việt? (Không dùng để đoán ngôn ngữ nói chung.)"""
    return any(ch in _VI_CHARS for ch in (text or ""))


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

    # Không coi "bản dịch" trùng y nguyên tên TMDB trả về là tiếng Việt
    # (test: translations vi ghi đúng "Frieren" → không phải tên Việt).
    original = (detail.get("name") or "").strip()
    if name and original and norm(name) == norm(original):
        name = None

    # `_get` LUÔN gửi `language=vi-VN` ⇒ `detail["name"]` đã là tên ĐÃ BẢN ĐỊA
    # HOÁ (TMDB trả tên gốc khi chưa có bản dịch). Trước đây hàm này chỉ đọc khối
    # `translations` + alternative title VN nên **0/119 bộ có tmdb_id nhận được
    # title_vi** (đo 02/11/2026), dù TMDB có tên Việt cho phần lớn bộ phổ biến:
    # bản dịch `vi` thường chỉ có `overview`, còn `name` nằm ở bản địa hoá.
    # Chỉ nhận khi chuỗi CÓ DẤU tiếng Việt — "One Piece"/"Frieren" (TMDB trả
    # nguyên tên gốc) không được coi là tên Việt.
    if not name:
        loc = (detail.get("name") or "").strip()
        orig = (detail.get("original_name") or "").strip()
        if loc and looks_vietnamese(loc) and norm(loc) != norm(orig):
            name = loc

    return name or None, overview or None


# Tên Việt lấy từ TMDB là tên của CẢ SERIES, không phải của mùa. Đo 02/11/2026:
# 18 cặp bộ/mùa trùng y nguyên title_vi ("Thánh Phồng Tôm" cho cả One-Punch Man
# mùa 1 và mùa 2) ⇒ trong tìm kiếm có 2 thẻ không phân biệt được.
_SEASON_IN_TITLE = re.compile(
    r"(?:ph\u1ea7n|phan|m\u00f9a|mua|season|ss)\s*\d+"
    r"|\u7b2c\s*\d+\s*(?:\u671f|\u30b7\u30fc\u30ba\u30f3)",
    re.IGNORECASE,
)


def _bo_nhan_mua(title: str) -> str:
    """Bỏ hậu tố "(Phần N)" ở cuối tên — để biết tên cũ có phải bản TRẦN không."""
    return re.sub(r"\s*\(Ph\u1ea7n\s*\d+\)\s*$", "", (title or "").strip())


def with_season_label(title_vi: Optional[str],
                      season_no: Optional[int]) -> Optional[str]:
    """Gắn "(Phần N)" vào tên Việt của mùa thứ 2 trở đi (nếu chưa có).

    Không bịa tên — chỉ thêm hậu tố mùa vào đúng tên TMDB đã trả. Mùa 1 giữ
    nguyên. Tên đã ghi "Phần 2"/"Season 2" thì không thêm lần nữa.
    """
    t = (title_vi or "").strip()
    if not t:
        return None                  # chuỗi rỗng cũng coi như không có tên
    if not isinstance(season_no, int) or season_no < 2:
        return title_vi
    if _SEASON_IN_TITLE.search(t):
        return title_vi
    return f"{t} (Phần {season_no})"


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

    cu = (row.get("title_vi") or "").strip()
    if not cu and title_vi:
        patch["title_vi"] = title_vi
    elif cu and title_vi and cu != title_vi and cu == _bo_nhan_mua(title_vi):
        # Tên cũ là tên TRẦN (chưa có "(Phần N)") của chính tên mới ⇒ nâng cấp.
        # Chỉ đúng trường hợp này: không bao giờ ghi đè một bản dịch khác.
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


def first_season_cut(
    detail: Dict[str, Any],
    season_no: Optional[int],
    season_hint: Optional[int],
    year: Optional[int],
    episodes_total: Optional[int],
    season_count: Optional[int] = None,
) -> Optional[int]:
    """Có an toàn để **cắt bớt** danh sách tập của mùa này không? Trả số tập tối đa.

    Ca thật 02/11/2026 — 9 bộ bị bỏ vì "TMDB 37 tập > AniList 25":
    TMDB gộp cả series (hoặc 2 cour) vào MỘT mùa, còn AniList tách entry.
    Với entry **mùa đầu** thì tập 1..N của TMDB đúng là tập 1..N của AniList,
    nên cắt phần dư là an toàn.

    Chỉ cho phép khi CHẮC đây là mùa đầu:
      · tên bộ không ghi mùa (hint None/1);
      · `season_no` là mùa nhỏ nhất của series;
      · năm chiếu của mùa đó **trùng** năm AniList (bộ bắt đầu đúng năm đó);
      · TMDB nhiều hơn **tối đa 2 lần** (2 mùa/2 cour gộp). Nhiều hơn hẳn —
        Fool Night: AniList 3 vs TMDB 12 = 4× — là nghi lấy nhầm series.
    Không thoả → trả None (thà để trống còn hơn gán tập mùa khác).
    """
    if not isinstance(episodes_total, int) or episodes_total <= 0:
        return None
    if season_hint not in (None, 1):
        return None
    seasons = season_candidates(detail)
    if not seasons or season_no is None:
        return None
    if season_no != seasons[0]["number"]:
        return None
    if year and _year_of(seasons[0]["air_date"]) not in (None, int(year)):
        return None
    count = season_count if isinstance(season_count, int) else seasons[0].get("count")
    if isinstance(count, int) and count > 2 * int(episodes_total) + 1:
        return None
    return int(episodes_total)


def split_season_offset(
    detail: Dict[str, Any],
    season_hint: Optional[int],
    episodes_total: Optional[int],
    season_count: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """TMDB gộp NHIỀU mùa AniList vào MỘT season → trả mùa + số tập cần trừ.

    Ca thật 02/11/2026: `dandadan-2nd-season` (AniList 12 tập, tên ghi mùa 2) trỏ
    tới TMDB 240411 "DAN DA DAN" — TMDB chỉ có **một** season 24 tập (mùa 1 + mùa 2
    gộp). `pick_season` từ chối (12 ≠ 24) nên bộ **lặng lẽ** không có tập nào.

    Nay: khi TMDB chỉ có 1 mùa và số tập của nó ≈ `season_hint × tổng` (lệch ≤2),
    lấy nửa thứ `season_hint` và **trừ offset** `(hint−1) × tổng` rồi đánh số lại.

    Bảo thủ: chỉ nhận khi số mùa của AniList và bội số tập khớp nhau; lệch là bỏ.
    """
    if not isinstance(season_hint, int) or season_hint < 2:
        return None
    if not isinstance(episodes_total, int) or episodes_total <= 0:
        return None
    seasons = season_candidates(detail)
    if len(seasons) != 1:
        return None                      # nhiều mùa riêng → dùng pick_season
    count = season_count if isinstance(season_count, int) else seasons[0]["count"]
    if not isinstance(count, int):
        return None
    if abs(count - season_hint * episodes_total) > 2:
        return None
    return {"season": seasons[0]["number"],
            "offset": (season_hint - 1) * episodes_total,
            "count": count}


def merged_year_candidate(
    detail: Dict[str, Any],
    season_hint: Optional[int],
    year: Optional[int],
    episodes_total: Optional[int],
) -> Optional[int]:
    """TMDB dồn nhiều mùa vào 1 season → mùa TMDB nào cần xét theo NĂM.

    Ca thật 02/11/2026: `kusuriya-no-hitorigoto-2nd-season` (AniList mùa 2, 24
    tập, năm 2025) → TMDB 220542 có **một** mùa **60 tập** (mùa 1+2+3 dồn lại).
    `split_season_offset` đòi 60 ≈ 2×24 (lệch ≤2) nên trượt; nhưng tập của mùa 2
    **nằm trong đó**, phân biệt được bằng NGÀY CHIẾU.

    Trả số mùa TMDB cần đọc, hoặc None. Chỉ nhận khi:
      · tên bộ ghi mùa ≥ 2 (nếu không thì mùa 1 đã đủ);
      · TMDB chỉ có ĐÚNG MỘT mùa;
      · số tập của mùa đó **nhiều hơn hẳn** tổng của AniList (dồn nhiều mùa).
    Việc tách theo năm do `episode_rows_by_year` làm và tự kiểm số lượng.
    """
    if not isinstance(season_hint, int) or season_hint < 2:
        return None
    if not year or not isinstance(episodes_total, int) or episodes_total <= 0:
        return None
    seasons = season_candidates(detail)
    if len(seasons) != 1:
        return None
    count = seasons[0].get("count")
    if not isinstance(count, int) or count <= episodes_total:
        return None                      # không nhiều hơn → không phải ca dồn mùa
    return seasons[0]["number"]


def episode_rows_by_year(
    anime_id: int,
    season: Dict[str, Any],
    year: int,
    episodes_total: int,
    tolerance: int = 2,
) -> List[Dict[str, Any]]:
    """Lấy các tập có NGÀY CHIẾU thuộc `year`, rồi đánh số lại 1..N.

    Dùng cho ca TMDB dồn nhiều mùa vào 1 season. An toàn vì:
      · số tập tìm được phải ≈ `episodes_total` (lệch ≤ `tolerance`), nếu không
        trả rỗng — mùa vắt qua 2 năm (12 tập năm trước + 12 tập năm sau) sẽ bị
        loại thay vì ghép bừa;
      · chỉ cắt theo đúng năm, không đoán thứ tự khác.
    """
    picked = []
    for e in season.get("episodes") or []:
        num = e.get("episode_number")
        air = e.get("air_date") or ""
        if not isinstance(num, int) or num <= 0 or not air[:4].isdigit():
            continue
        if int(air[:4]) == int(year):
            picked.append(e)
    if abs(len(picked) - int(episodes_total)) > tolerance:
        return []
    picked.sort(key=lambda e: e["episode_number"])
    out = []
    for new_num, e in enumerate(picked, 1):
        row = {
            "anime_id": anime_id,
            "number": new_num,
            "airing_at": dt.datetime.fromisoformat(e["air_date"]).replace(
                tzinfo=dt.timezone.utc).isoformat(),
        }
        title = clean_episode_title(e.get("name"))
        if title:
            row["title"] = title
        out.append(row)
    return out


def episode_rows_in_window(
    anime_id: int,
    season: Dict[str, Any],
    start: Optional[dt.date],
    end: Optional[dt.date],
    episodes_total: Optional[int],
    tolerance: int = 2,
    slack_days: int = 2,
) -> List[Dict[str, Any]]:
    """Lấy tập của season nằm trong KHOẢNG CHIẾU của entry AniList, đánh số lại.

    Ca thật 02/11/2026 — TMDB 216467: mùa 2 có **24 tập** (12/04/2026 → …), còn
    AniList tách thành "2nd Season" (12 tập) + "2nd Season Part 2" (12 tập).
    Luật theo NĂM không tách được (cả hai đều 2026) và luật trừ offset cũng
    không (TMDB có season riêng). Ngày chiếu của chính entry AniList mới là ranh
    giới đúng: cour 1 nằm trong 04→06/2026, cour 2 nằm trong 07→09/2026.

    An toàn:
      · không có `start` → trả rỗng (không đoán);
      · có `end` mà số tập trong khoảng lệch `episodes_total` quá `tolerance`
        → trả rỗng;
      · không có `end` (đang chiếu) → lấy các tập ĐẦU TIÊN kể từ `start`,
        tối đa `episodes_total`.
    """
    if not isinstance(start, dt.date):
        return []
    total = int(episodes_total) if isinstance(episodes_total, int) and episodes_total > 0 else 0
    lo = start - dt.timedelta(days=slack_days)
    hi = (end + dt.timedelta(days=slack_days)) if isinstance(end, dt.date) else None

    picked = []
    for e in season.get("episodes") or []:
        air = e.get("air_date") or ""
        if not isinstance(e.get("episode_number"), int) or not air[:10]:
            continue
        try:
            d = dt.date.fromisoformat(air[:10])
        except ValueError:
            continue
        if d < lo or (hi is not None and d > hi):
            continue
        picked.append((d, e))
    picked.sort(key=lambda t: (t[0], t[1]["episode_number"]))

    if hi is not None:
        if total and abs(len(picked) - total) > tolerance:
            return []              # khoảng chiếu không khớp số tập → không ghép bừa
    elif total and len(picked) > total:
        picked = picked[:total]     # đang chiếu, season TMDB dài hơn → lấy phần đầu
    if not picked:
        return []

    out = []
    for new_num, (_, e) in enumerate(picked, 1):
        air = e["air_date"]
        row = {
            "anime_id": anime_id,
            "number": new_num,
            "airing_at": dt.datetime.fromisoformat(air[:10]).replace(
                tzinfo=dt.timezone.utc).isoformat(),
        }
        title = clean_episode_title(e.get("name"))
        if title:
            row["title"] = title
        out.append(row)
    return out


def season_first_year(season: Dict[str, Any]) -> Optional[int]:
    """Năm chiếu của tập ĐẦU TIÊN có ngày trong season TMDB (None nếu không có)."""
    years = []
    for e in season.get("episodes") or []:
        air = (e.get("air_date") or "")[:4]
        if air.isdigit():
            years.append(int(air))
    return min(years) if years else None


def episode_rows(
    anime_id: int,
    season: Dict[str, Any],
    single_season: bool,
    max_number: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Đổi season TMDB → rows cho bảng `episodes`. Bỏ qua nếu không đủ tin cậy."""
    if not single_season:
        return []   # chưa xác định được mùa → không ghi tập (tránh gán tập mùa khác)
    out = []
    for e in season.get("episodes") or []:
        num = e.get("episode_number")
        if not isinstance(num, int) or num <= 0:
            continue
        if offset:
            num -= int(offset)            # TMDB gộp mùa → đánh số lại (xem
            if num <= 0:                  # `split_season_offset`)
                continue
        if isinstance(max_number, int) and max_number > 0 and num > max_number:
            continue                      # cắt phần dư (xem `first_season_cut`)
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


_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
SEASON_IN_TITLE = (
    re.compile(r"(\d+)(?:st|nd|rd|th)\s*season", re.IGNORECASE),
    # "Second Season" viết bằng chữ (Diamond no Ace act II: Second Season)
    re.compile(
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s*season",
        re.IGNORECASE,
    ),
    re.compile(r"season\s*(\d+)", re.IGNORECASE),
    re.compile(r"m[ùu]a\s*(\d+)", re.IGNORECASE),
)

# Dạng ngắn mà AniList hay dùng cho mùa 2/3: "One Punch Man 2", "Mob Psycho 100 II",
# "Karakai Jouzu no Takagi-san 2". Đây là các entry MÙA, không phải bộ khác.
_ROMAN = {"II": 2, "III": 3, "IV": 4, "V": 5}
_TRAILING_NUM = re.compile(r"\s(\d{1,2})$")
_TRAILING_ROMAN = re.compile(r"\s(II|III|IV|V)$")


def season_from_title(*titles: Optional[str]) -> Optional[int]:
    """Đọc số mùa từ TÊN bộ: "… 2nd Season", "Season 2", "Mùa 2" → 2.

    Vì sao cần: AniList tách mỗi mùa thành entry riêng ("Kusuriya no Hitorigoto
    2nd Season"), còn TMDB gộp cả series vào một id. `pick_season` cũ chỉ dựa vào
    năm/số tập nên với bộ nhiều mùa giống nhau (12–13 tập/mùa) nó bó tay → 30 bộ
    đã chiếu xong mà KHÔNG có tập nào (đo 02/11/2026).

    KHÔNG đọc "Part 2" — đó là phần trong cùng một mùa TMDB, không phải mùa mới.
    """
    for t in titles:
        if not t:
            continue
        for rx in SEASON_IN_TITLE:
            m = rx.search(t)
            if m:
                g = m.group(1)
                n = _ORDINALS.get(g.lower()) if g.isalpha() else int(g)
                if n and 1 <= n <= 30:
                    return n
        # "… 2" / "… II" ở CUỐI tên. Chỉ nhận 2..9 (mùa 1 viết "… 1" gần như
        # không có) và bỏ qua số > 30 để "Mob Psycho 100" không thành mùa 100.
        # Có dấu ":" là tên phim/phần đặc biệt ("Girls und Panzer: Saishuushou 5"
        # là PHẦN 5 của phim điện ảnh, không phải mùa TV) → không đoán.
        if ":" in t:
            continue
        # "Part 2"/"Phần 2" là cour trong CÙNG một mùa TMDB → không phải mùa mới.
        if re.search(r"\b(part|phần)\s*\d+\s*$", t, re.IGNORECASE):
            continue
        m = _TRAILING_ROMAN.search(t)
        if m:
            return _ROMAN[m.group(1)]
        m = _TRAILING_NUM.search(t)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 9:
                return n
    return None


def pick_season(
    detail: Dict[str, Any],
    year: Optional[int] = None,
    episodes_total: Optional[int] = None,
    season_hint: Optional[int] = None,
) -> Tuple[Optional[int], str]:
    """Chọn mùa TMDB ứng với 1 entry AniList. Trả (season_number | None, lý do).

    Thứ tự tin cậy:
      0. `season_hint` (đọc từ tên bộ) trùng số mùa có thật → mùa đó (chắc nhất)
      1. TMDB chỉ có 1 mùa            → mùa đó (chắc chắn)
      2. đúng 1 mùa có NĂM = năm AniList → mùa đó (Takagi-san 2018 → S1, không phải S3)
      3. đúng 1 mùa có SỐ TẬP = số tập AniList → mùa đó
      4. còn lại → None. KHÔNG đoán: thà trống còn hơn gán tập của mùa khác.
    """
    seasons = season_candidates(detail)
    if not seasons:
        return None, "TMDB không có mùa nào"

    if season_hint:
        hit = [s for s in seasons if s["number"] == season_hint]
        if hit:
            return hit[0]["number"], f"theo tên (mùa {season_hint})"
        # TMDB CÓ entry riêng cho từng mùa (vd "The Apothecary Diaries Season 2",
        # id 220542) → entry đó chỉ có 1 "mùa" số 1, dù tên AniList ghi mùa 2.
        # Chỉ nhận khi số tập của mùa duy nhất đó XẤP XỈ số tập AniList (lệch ≤2),
        # nếu không thì vẫn từ chối — tránh gán tập mùa 1 cho entry mùa 2.
        if len(seasons) == 1 and episodes_total:
            only = seasons[0]
            cnt = only["count"]
            if isinstance(cnt, int) and abs(cnt - int(episodes_total)) <= 2:
                return only["number"], (
                    f"tên ghi mùa {season_hint} nhưng TMDB là entry riêng của mùa "
                    f"({cnt} tập ≈ {episodes_total}) → dùng mùa {only['number']}"
                )
        # Còn lại: KHÔNG rơi xuống đoán mò, vì dễ gán tập mùa 1 cho entry mùa 2.
        return None, f"tên ghi mùa {season_hint} nhưng TMDB chỉ có mùa " + \
            ", ".join(str(s["number"]) for s in seasons)

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


# Hậu tố chỉ mùa mà TMDB KHÔNG có trong tên series: "… Season 2", "… 2nd Season",
# "… Mùa 2", "… 2", "… II". TMDB đặt tên series gộp cả bộ ("One-Punch Man"), nên
# tìm nguyên chuỗi có hậu tố sẽ ra 0 kết quả (đo 02/11/2026: 56 bộ không tìm thấy).
_SEASON_SUFFIX = (
    re.compile(r"\s*[:\-–]?\s*\d+(?:st|nd|rd|th)\s*season\s*$", re.IGNORECASE),
    re.compile(r"\s*[:\-–]?\s*season\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\s*[:\-–]?\s*m[ùu]a\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\s+(?:II|III|IV|V)$"),
    re.compile(r"\s+\d{1,2}$"),
)


def base_title(title: Optional[str]) -> Optional[str]:
    """Bỏ hậu tố mùa để tìm được series gộp trên TMDB.

    `"One-Punch Man Season 2"` → `"One-Punch Man"`, `"Mob Psycho 100 II"` →
    `"Mob Psycho 100"`. Trả None khi không cắt được gì (hoặc tên quá ngắn).
    """
    t = (title or "").strip()
    if not t:
        return None
    for rx in _SEASON_SUFFIX:
        cut = rx.sub("", t).strip(" :-–")
        if cut and cut != t and len(cut) >= 3:
            return cut
    return None


# ─────────────────────────────────────────── API mức cao (1 anime)
def match_anime(
    row: Dict[str, Any],
    accept: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """Tìm phim trên TMDB cho 1 row `anime`. Trả (result|None, điểm, cách thử).

    `accept(result)` — tuỳ chọn: chỉ nhận kết quả mà hàm này trả True. Dùng để
    thử **ứng viên kế tiếp** khi kết quả điểm cao nhất không có mùa cần tìm
    (xem `pick_all`). Tối đa 3 ứng viên mỗi chuỗi tìm.
    """
    titles = [row.get("title_english"), row.get("title_romaji"), row.get("title_native")]
    titles = [t for t in titles if t]
    year = row.get("year")

    # Bộ có tên ghi mùa 2/3 ("One Punch Man 2", "Dandadan 2nd Season") thì NĂM của
    # AniList là năm mùa đó, còn `first_air_date` của TMDB là năm MÙA 1 → lọc theo
    # năm sẽ loại sạch (đo 02/11/2026: "One Punch Man 2" 2019 vs TMDB 2015, lệch 4
    # > tolerance 2 → 25 bộ FINISHED không khớp được TMDB nên 0 tập).
    hint = season_from_title(*titles)
    year_filter = None if (hint and hint > 1) else year

    # Thêm biến thể "tên gốc": tìm "One Punch Man 2" trên TMDB trả 0 kết quả, còn
    # "One Punch Man" thì ra ngay series gộp cả 3 mùa → pick_season chọn mùa 2.
    queries: list = []
    for t in titles:
        if t not in queries:
            queries.append(t)
    for t in titles:
        b = base_title(t)
        if b and b not in queries:
            queries.append(b)

    tried = []
    tried_ids: set = set()
    for t in queries:
        params: Dict[str, Any] = {"query": t}
        if year and year_filter is not None:
            params["first_air_date_year"] = year
        res = _get("/search/tv", params).get("results") or []
        tried.append(f"search[{t[:24]}]")
        fresh = [r for r in res if r.get("id") not in tried_ids]
        cands = pick_all(fresh, titles, year_filter)
        for cand, sc in cands[:3]:
            if accept is None:
                return cand, sc, tried[-1]
            if accept(cand):
                return cand, sc, tried[-1]
            tried_ids.add(cand.get("id"))     # đã xét, chuỗi sau đừng thử lại
        # lần 2: bỏ ràng buộc năm (TMDB hay lệch năm với AniList). Nếu đã bỏ lọc
        # năm từ đầu (hint mùa ≥2) thì lần 2 là request y hệt → không gọi lại.
        if year and year_filter is not None:
            time.sleep(SLEEP_BETWEEN)
            res2 = _get("/search/tv", {"query": t}).get("results") or []
            tried.append(f"search-noyear[{t[:24]}]")
            for cand, sc in pick_all(res2, titles, year_filter)[:3]:
                if accept is None or accept(cand):
                    return cand, sc, tried[-1]
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


# ─────────────────────────────────────────── soi 1 bộ (chạy tay)
def explain(row: Dict[str, Any], limit: int = 5) -> int:
    """In ra TMDB trả về GÌ cho 1 bộ — để chẩn đoán "không tìm được trên TMDB".

    Không đoán: in đủ tên + năm + điểm của từng kết quả để người đọc tự thấy
    vì sao bị loại (lệch tên? lệch năm? TMDB không có bộ đó?).
    """
    titles = [t for t in (row.get("title_english"), row.get("title_romaji"),
                          row.get("title_native")) if t]
    hint = season_from_title(*titles)
    year_filter = None if (hint and hint > 1) else row.get("year")
    print(f"\n▶ {row.get('slug') or row.get('title_romaji')}")
    print(f"  tên : {titles}")
    print(f"  năm : {row.get('year')} · mùa đoán từ tên: {hint} "
          f"· lọc năm khi tìm: {year_filter}")
    print(f"  tổng tập AniList: {row.get('episodes_total')} "
          f"· tmdb_id: {row.get('tmdb_id')}")

    queries: list = []
    for t in titles:
        if t not in queries:
            queries.append(t)
    for t in titles:
        b = base_title(t)
        if b and b not in queries:
            queries.append(b)

    seen: set = set()
    for q in queries:
        params: Dict[str, Any] = {"query": q}
        if year_filter is not None:
            params["first_air_date_year"] = year_filter
        try:
            res = _get("/search/tv", params).get("results") or []
        except TmdbError as e:
            print(f"\n  query {q!r} → LỖI: {e}")
            continue
        print(f"\n  query {q!r} → {len(res)} kết quả")
        for r in res[:limit]:
            sc = title_score(titles, r, year_filter)
            ok = "✓" if sc >= TITLE_THRESHOLD else "✗"
            print(f"    {ok} {sc:.3f}  {r.get('id')}  {r.get('name')!r} "
                  f"({r.get('first_air_date') or '?'})")
            # In LUÔN các mùa của ứng viên đạt ngưỡng + quyết định chọn mùa.
            # Thiếu phần này thì log chỉ nói "TMDB chỉ có mùa 1" mà không cho
            # biết mùa đó bao nhiêu tập → không thể biết vì sao bị từ chối.
            if sc < TITLE_THRESHOLD or r.get("id") in seen:
                continue
            seen.add(r.get("id"))
            try:
                det = fetch_detail(r["id"])
            except TmdbError as e:
                print(f"        ↳ không đọc được chi tiết: {e}")
                continue
            seasons = season_candidates(det)
            if not seasons:
                print("        ↳ TMDB: KHÔNG có mùa nào")
                continue
            for sn in seasons:
                print(f"        ↳ mùa {sn['number']}: {sn['count']} tập "
                      f"({sn['air_date'] or '?'})")
            # Phân bố NGÀY CHIẾU của mùa đầu: cần để biết vì sao "tách theo năm"
            # không chạy (TMDB thiếu ngày? tập nằm ở năm khác?).
            try:
                first = fetch_season(r["id"], seasons[0]["number"])
            except TmdbError as e:
                print(f"        ↳ không đọc được danh sách tập: {e}")
                first = {}
            buckets: Dict[str, int] = {}
            no_date = 0
            for e in first.get("episodes") or []:
                air = (e.get("air_date") or "")[:4]
                if air.isdigit():
                    buckets[air] = buckets.get(air, 0) + 1
                else:
                    no_date += 1
            if buckets or no_date:
                detail_txt = " · ".join(f"{y}: {c} tập"
                                        for y, c in sorted(buckets.items()))
                print(f"        ↳ ngày chiếu: {detail_txt or '—'}"
                      + (f" · {no_date} tập KHÔNG có ngày" if no_date else ""))
            no, why = pick_season(det, row.get("year"),
                                  row.get("episodes_total"), hint)
            extra = ""
            if no is None:
                sp = split_season_offset(det, hint, row.get("episodes_total"))
                if sp:
                    no, extra = sp["season"], f" · gộp mùa, trừ {sp['offset']} tập"
            if no is None:
                yno = merged_year_candidate(det, hint, row.get("year"),
                                            row.get("episodes_total"))
                if yno is not None:
                    no, extra = yno, (f" · dồn mùa, tách theo năm "
                                      f"{row.get('year')}")
            if no is None:
                print(f"        ✗ TỪ CHỐI: {why}")
            else:
                print(f"        ✓ CHỌN mùa {no} ({why}){extra}")
        if not res:
            print("    (TMDB không trả gì cho chuỗi này — thử tên khác)")
        time.sleep(SLEEP_BETWEEN)
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Soi TMDB trả gì cho 1 bộ (chẩn đoán 'không tìm được trên TMDB')")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug", help="slug trong DB, vd: the-ramparts-of-ice-season-2")
    g.add_argument("--title", help='tên bất kỳ, vd: "Dandadan 2nd Season"')
    ap.add_argument("--year", type=int, default=None, help="kèm --title")
    ap.add_argument("--total", type=int, default=None,
                    help="episodes_total, kèm --title")
    args = ap.parse_args(argv)

    if args.title:
        row = {"slug": args.title, "title_romaji": args.title,
               "year": args.year, "episodes_total": args.total}
        return explain(row)

    from . import db as dbmod
    DB = dbmod.DB()
    rows = DB.select("anime",
                     "select=id,slug,title_romaji,title_english,title_native,"
                     f"year,episodes_total,tmdb_id&slug=eq.{args.slug}&limit=1")
    if not rows:
        print(f"✗ không thấy anime slug={args.slug}")
        return 2
    return explain(rows[0])


if __name__ == "__main__":
    raise SystemExit(main())
