"""
match.py — Ghép tên series (từ tiêu đề YouTube) → anime trên AniList.

Đây là phần khó nhất và cũng là chỗ tạo ra giá trị riêng của app.
Ví dụ thật gặp phải:
  "A Certain Scientific Railgun"   (YouTube) ↔ "Toaru Kagaku no Railgun"     (AniList)
  "A Returner's Magic ... Special" (YouTube) ↔ "Kikansha no Mahou wa ..."     (AniList)
  "擅長捉弄人的高木同學"            (Ani-One, phồn thể) ↔ "Karakai Jouzu no Takagi-san"

Chiến lược 4 lớp (rẻ → đắt):
  1. Bảng alias tay (aliases.json)          — chính xác 100%, do người biên tập
  2. Search nguyên tên                       — được với tên Latinh/romaji
  3. Chuyển phồn thể → giản thể rồi search   — Ani-One đăng bằng phồn thể
  4. Cắt bớt từ rồi search lại               — "擅长捉弄人的高木同学" → "高木同学"
Sau mỗi lần search: chấm điểm mờ trên 3 trường tên + ưu tiên TV-series và độ phổ biến.
"""
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from . import anilist

THRESHOLD = 0.72
ALIAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aliases.json")

# ── Phồn thể → giản thể (các ký tự hay gặp trong tên anime). Thiếu thì bổ sung.
T2S = str.maketrans(
    "學習戀這模樣嗎時間們個為說對麼裡會來開關門車話與無東樂園戰記劇場電視畫動變態願夢龍鳳術師應該頭體實現從於還進過發內兩幾誰"
    "兒體育鬥劍騎聲點數歲萬聽寫讀圖書館遊戲劇終級給帶愛選擇戰爭業當經濟會發現實學問開啟門問題",
    "学习恋这模样吗时间们个为说对么里会来开关门车话与无东乐园战记剧场电视画动变态愿梦龙凤术师应该头体实现从于还进过发内两几谁"
    "儿体育斗剑骑声点数岁万听写读图书馆游戏剧终级给带爱选择战争业当经济会发现实学问开启门问题"
)

ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u9fff]")


# ─────────────────────────────────────────── chuẩn hoá
def simplify(text: str) -> str:
    """Phồn thể → giản thể (bảng map nội bộ, không cần thư viện ngoài)."""
    return (text or "").translate(T2S)


# "Mùa 2"/"Phần 2" (Muse VN dùng tiếng Việt) và "Season 2"/"(S2)". Phải bỏ TRƯỚC
# khi normalize, vì norm() xoá dấu tiếng Việt → "mùa 2" thành "m a 2" và số "2"
# còn lại làm lệch điểm giữa "One Punch Man" và "One Punch Man - Mùa 2".
_SEASON_MARK = re.compile(
    r"(?:^|[\s\-–—:|])(?:mùa|mua|phần|phan|season)\s*\d{1,2}\b|\(s\d{1,2}\)",
    re.IGNORECASE,
)


def norm(s: str) -> str:
    s = _SEASON_MARK.sub(" ", s or "")
    s = unicodedata.normalize("NFKC", s).lower()
    s = ARTICLES.sub("", s)
    s = re.sub(r"\b(season|phần|part|s)\s*\d+\b", " ", s)
    s = re.sub(r"\b\d+(st|nd|rd|th)\s*season\b", " ", s)
    s = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def has_cjk(s: str) -> bool:
    return bool(_CJK.search(s or ""))


def _compact(s: str) -> str:
    return norm(s).replace(" ", "")


def similarity(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    # "shin-chan" ↔ "shinchan", "re:zero" ↔ "rezero"
    ratio = max(ratio, SequenceMatcher(None, _compact(a), _compact(b)).ratio())
    if na in nb or nb in na:                 # "railgun" ⊂ "toaru kagaku no railgun"
        ratio = max(ratio, 0.80)
    return ratio


# ─────────────────────────────────────────── chấm điểm
def score_media(name: str, media: Dict) -> float:
    """Điểm 0–1 giữa tên series và 1 media AniList (xét cả 3 trường tên)."""
    t = media.get("title") or {}
    titles = [t.get("romaji"), t.get("english"), t.get("native")]
    best = max((similarity(name, x) for x in titles if x), default=0.0)

    # thưởng nhẹ nếu các từ khoá dài của tên xuất hiện trong tên ứng viên
    tnorm = norm(" ".join(x for x in titles if x))
    for w in [w for w in norm(name).split() if len(w) >= 4]:
        if w in tnorm:
            best = max(best, 0.78)
    return best


def pick_best(name: str, candidates: List[Dict], want_series: bool = True
              ) -> Tuple[Optional[Dict], float]:
    """Chọn ứng viên tốt nhất: điểm cao nhất, hoà thì ưu tiên TV-series rồi popularity."""
    if not candidates:
        return None, 0.0

    def fmt_rank(m: Dict) -> int:
        f = (m.get("format") or "").upper()
        if not want_series:
            return 0
        return {"TV": 3, "TV_SHORT": 2, "ONA": 1, "OVA": 0, "MOVIE": -1, "SPECIAL": -1}.get(f, 0)

    scored = [(m, score_media(name, m)) for m in candidates]
    scored.sort(key=lambda x: (round(x[1], 2), fmt_rank(x[0]), x[0].get("popularity") or 0),
                reverse=True)
    return scored[0]


# ─────────────────────────────────────────── alias
def alias_key(name: str) -> str:
    """Keep season numbers and Vietnamese accents in editorial alias keys."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name or "").casefold()).strip()


# ─────────────────────────────────────────── cache ra ĐĨA
# Vì sao: mỗi tên chưa khớp tốn tới 4 request AniList (nguyên tên → phản thể →
# 3 từ cuối → 2 từ cuối). Backfill 5.000 video có thể cần hàng trăm tên; mất
# mạng/Ctrl+C là mất sạch kết quả vì cache cũ chỉ nằm trong RAM. Lưu xuống đĩa
# để lần sau chạy tiếp thay vì search lại từ đầu.
CACHE_VERSION = 1


def default_cache_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, ".cache", "match_cache.json")


def _aliases_mtime() -> float:
    try:
        return os.path.getmtime(ALIAS_PATH)
    except OSError:
        return 0.0


def load_disk_cache(path: Optional[str] = None) -> Dict[str, Optional[Dict]]:
    """Đọc cache ghép tên. File hỏng/không có → cache rỗng (không bao giờ nổ).

    Nếu `aliases.json` đã bị sửa sau lần lưu cache thì BỎ các mục âm (None):
    người biên tập vừa thêm alias thì phải được thử lại, không kẹt vì
    "đã từng không khớp".
    """
    p = path or default_cache_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    entries = data.get("entries") or {}
    out: Dict[str, Optional[Dict]] = {}
    aliases_changed = data.get("aliases_mtime") != _aliases_mtime()
    for k, v in entries.items():
        if v is None:
            if aliases_changed:
                continue                  # có alias mới → thử lại
            out[k] = None
        elif isinstance(v, dict):
            out[k] = v
    return out


def save_disk_cache(cache: Dict[str, Optional[Dict]], path: Optional[str] = None) -> str:
    """Ghi cache nguyên tử (tmp + rename): Ctrl+C giữa lúc ghi không làm hỏng file."""
    p = path or default_cache_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "aliases_mtime": _aliases_mtime(),
        "entries": {k: v for k, v in cache.items()},
    }
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, p)
    return p


def load_aliases() -> Dict[str, int]:
    try:
        with open(ALIAS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {alias_key(k): v for k, v in (data.get("aliases") or {}).items() if v}
    except Exception:
        return {}


_ALIASES = load_aliases()
_ALIAS_MEDIA: Dict[int, Dict] = {}


def _media_by_id(anilist_id: int) -> Optional[Dict]:
    """Lấy media theo id (cache) — dùng khi match bằng alias."""
    if anilist_id in _ALIAS_MEDIA:
        return _ALIAS_MEDIA[anilist_id]
    q = "query($id:Int){ Media(id:$id, type:ANIME){ %s } }" % anilist.MEDIA_FIELDS
    try:
        m = anilist.gql(q, {"id": anilist_id}).get("Media")
    except Exception:
        m = None
    _ALIAS_MEDIA[anilist_id] = m
    return m


# ─────────────────────────────────────────── resolve
def _short_variants(name: str) -> List[str]:
    """Các biến thể rút gọn để search lại khi tên đầy đủ thất bại."""
    out = []
    if has_cjk(name):
        # tên tiếng Trung: phần phân biệt thường nằm ở đuôi → thử 6, 5, 4 ký tự cuối
        clean = re.sub(r"[\s\d]+$", "", name)
        for n in (6, 5, 4):
            if len(clean) > n:
                out.append(clean[-n:])
    else:
        # tên Latinh: bỏ mạo từ, rồi thử 3 từ cuối / 2 từ cuối
        words = norm(name).split()
        if len(words) > 3:
            out.append(" ".join(words[-3:]))
        if len(words) > 2:
            out.append(" ".join(words[-2:]))
    return out


def resolve(name: str, cache: Dict[str, Optional[Dict]],
            want_series: bool = True) -> Tuple[Optional[Dict], float, str]:
    """
    Trả (media | None, confidence, cách khớp: 'alias'|'search'|'simplified'|'short'|'—')
    """
    key = alias_key(name)
    if not key:
        return None, 0.0, "—"
    if key in cache:
        m = cache[key]
        return m, (1.0 if m else 0.0), ("cached" if m else "—")

    # 1) alias tay
    alias = alias_key(name)
    if alias in _ALIASES:
        m = _media_by_id(_ALIASES[alias])
        if m:
            cache[key] = m
            return m, 1.0, "alias"

    def _ok(m, sc):
        """Chấp nhận hay không: video tập phim thì không nhận MOVIE/SPECIAL nếu chưa chắc."""
        if m is None or sc < THRESHOLD:
            return False
        if want_series and (m.get("format") or "").upper() in ("MOVIE", "SPECIAL") and sc < 0.95:
            return False
        return True

    # 2) search nguyên tên
    best, score = pick_best(name, anilist.search_media(name, per_page=6), want_series)
    if _ok(best, score):
        cache[key] = best
        return best, score, "search"

    # 3) phồn thể → giản thể
    if has_cjk(name):
        simp = simplify(name)
        if simp != name:
            b2, s2 = pick_best(simp, anilist.search_media(simp, per_page=6), want_series)
            if _ok(b2, s2) and s2 > score:
                cache[key] = b2
                return b2, s2, "simplified"

    # 4) rút gọn tên rồi search lại
    for variant in _short_variants(name):
        b3, s3 = pick_best(variant, anilist.search_media(variant, per_page=6), want_series)
        if _ok(b3, s3):
            cache[key] = b3
            return b3, s3, "short"

    cache[key] = None
    return None, score, "—"


# ─────────────────────────────────────────── chọn đúng BỘ / MÙA cho Muse VN
# Muse VN đăng theo mùa: "One Punch Man - Mùa 2 - Tập 5", "Fairy Tail (S3) - Tập 51".
# AniList tách mỗi mùa thành entry riêng, và entry mùa 1 KHÔNG chứa tập của mùa 2.
# Trước đây mọi link được gán vào entry khớp tên nhất → "Hunter x Hunter (bản 2011,
# 148 tập)" bị nhét vào entry 1999 (62 tập), "Fairy Tail 277 tập" vào entry 175 tập.
SEASON_IN_TITLE = {
    2: re.compile(r"(?:2nd\s+season|season\s*2|mùa\s*2|\bii\b|\b2$)", re.I),
    3: re.compile(r"(?:3rd\s+season|season\s*3|mùa\s*3|\biii\b|\b3$)", re.I),
    4: re.compile(r"(?:4th\s+season|season\s*4|mùa\s*4|\biv\b|\b4$)", re.I),
}


def _titles(media: Dict) -> List[str]:
    t = media.get("title") or {}
    return [x for x in (t.get("romaji"), t.get("english"), t.get("native")) if x]


def _year(media: Dict) -> Optional[int]:
    sd = media.get("startDate") or {}
    if isinstance(sd.get("year"), int):
        return sd["year"]
    for k in ("seasonYear", "year"):
        if isinstance(media.get(k), int):
            return media[k]
    return None


def looks_like_season(media: Dict, season: int) -> bool:
    """Tên của media có ghi đây là mùa `season` không?"""
    rx = SEASON_IN_TITLE.get(season)
    if not rx:
        rx = re.compile(rf"(?:season\s*{season}|mùa\s*{season})", re.I)
    return any(rx.search(t) for t in _titles(media))


def fits_episode(media: Dict, max_episode: int, tolerance: int = 0) -> bool:
    """Bộ này CÓ thể chứa tập `max_episode` không? (chưa biết tổng → cho qua)"""
    total = media.get("episodes")
    if not isinstance(total, int) or total <= 0:
        return True
    return max_episode <= total + tolerance


def choose_entry(
    candidates: List[Dict],
    base: str,
    season: Optional[int] = None,
    max_episode: int = 0,
    year_hint: Optional[int] = None,
) -> Tuple[Optional[Dict], str]:
    """Chọn entry AniList cho 1 series của Muse, có xét MÙA / NĂM / SỐ TẬP.

    Thứ tự:
      1. Đúng mùa (tên có "Season 2"/"Mùa 2"/"II") VÀ đủ chỗ cho tập lớn nhất.
         Nhiều ứng viên → ưu tiên năm khớp `year_hint`, rồi popularity.
      2. Không có mùa trong tiêu đề → entry khớp tên nhất mà **đủ chỗ chứa tập**.
         (Đây là chỗ sửa lỗi Hunter x Hunter/Fairy Tail: entry 62 tập bị loại vì
         Muse có tập 148, chọn entry 148 tập.)
      3. Không có ứng viên nào đủ chỗ → None (job sẽ báo "cần xác định", KHÔNG ghi bừa).
    """
    if not candidates:
        return None, "không có ứng viên"

    def score(m: Dict) -> float:
        return max((similarity(base, t) for t in _titles(m)), default=0.0)

    pool = [c for c in candidates if fits_episode(c, max_episode)]

    if season and season > 1:
        same_season = [c for c in pool if looks_like_season(c, season)]
        if same_season:
            same_season.sort(key=lambda m: (-
                (1 if year_hint and _year(m) == year_hint else 0),
                -(m.get("popularity") or 0)))
            return same_season[0], f"mùa {season}"
        # Chưa có entry mùa đó trên AniList → thà báo thiếu còn hơn gán vào mùa 1
        return None, f"chưa có entry mùa {season} (AniList)"

    if not pool:
        totals = sorted({c.get("episodes") for c in candidates
                         if isinstance(c.get("episodes"), int)})
        return None, (f"không entry nào đủ {max_episode} tập "
                      f"(các bộ cùng tên có: {totals or 'không rõ'})")

    ranked = sorted(pool, key=score, reverse=True)
    best = ranked[0]
    if score(best) < THRESHOLD:
        return None, f"tên không khớp (điểm {score(best):.2f})"
    return best, f"khớp tên {score(best):.2f}"


def search_candidates(name: str, per_page: int = 10) -> List[Dict]:
    """Ứng viên AniList cho 1 tên: thử nguyên tên, rồi giản thể, rồi rút gọn.

    Khác `resolve`: trả về CẢ danh sách để `choose_entry` còn xét mùa/số tập.
    """
    out: List[Dict] = []
    seen = set()
    variants = [name]
    if has_cjk(name):
        variants.append(simplify(name))
    variants.extend(_short_variants(name))
    for v in variants:
        if not alias_key(v):
            continue
        for m in anilist.search_media(v, per_page=per_page) or []:
            mid = m.get("id")
            if mid in seen:
                continue
            seen.add(mid)
            out.append(m)
        if out:
            break
    return out


def resolve_series(name: str, season: Optional[int] = None, max_episode: int = 0,
                   year_hint: Optional[int] = None, cache: Optional[Dict] = None,
                   min_score: float = 0.0) -> Tuple[Optional[Dict], float, str]:
    """Ghép MỘT series của Muse VN → đúng entry AniList (bộ + mùa).

    Đây là đường ghép ĐÚNG cho job C. `choose_entry` xét mùa ("S3"/"Mùa 2"),
    xét tổng số tập (loại entry 62 tập khi video là tập 148) và xét năm — nhưng
    từ 02/11/2026 nó **không được gọi ở đâu cả** (chỉ có test): job C vẫn dùng
    `resolve` → `pick_best`, tức chỉ so tên mờ rồi lấy bộ giống nhất. Hệ quả đo
    được: "Đại chiến người Khổng Lồ S3", "Thất hình đại tội S2", "One-Punch Man
    S3" không vào được DB dù AniList có đủ entry.

    `cache` (dict trên đĩa) chỉ lưu kết quả CUỐI cho tên gốc, dùng khoá riêng
    để không lẫn với `resolve`.
    """
    key = alias_key(name)
    if not key:
        return None, 0.0, "—"

    def _done(media: Optional[Dict], score: float, why: str):
        return media, score, why

    # 0) cache trên đĩa: tên đã ghép ở lần chạy trước → chỉ còn kiểm mùa/tập
    if cache is not None and isinstance(cache.get(key), dict):
        best, why = choose_entry([cache[key]], name, season, max_episode, year_hint)
        if best:
            return _done(best, 1.0, f"cache · {why}")

    # 1) alias biên tập: chính xác 100%, vẫn phải kiểm mùa/tập
    if key in _ALIASES:
        m = _media_by_id(_ALIASES[key])
        if m:
            best, why = choose_entry([m], name, season, max_episode, year_hint)
            if best:
                return _done(best, 1.0, f"alias · {why}")

    cands = search_candidates(name)
    best, why = choose_entry(cands, name, season, max_episode, year_hint)
    if not best:
        return _done(None, 0.0, why)
    if cache is not None:
        cache[key] = best          # lần sau chỉ cần kiểm mùa/tập, không search lại

    score = max((similarity(name, t) for t in _titles(best)), default=0.0)
    if score < min_score:
        # Tên đến từ MÔ TẢ video (không phải tiêu đề) → đòi hỏi chặt hơn, tránh
        # gán bừa một câu văn trong mô tả vào một bộ nào đó.
        return _done(None, score, f"điểm {score:.2f} < {min_score:.2f}")
    return _done(best, score, why)


def rank_candidates(name: str, candidates: List[Dict]) -> List[Tuple[Dict, float]]:
    return sorted(((c, score_media(name, c)) for c in candidates), key=lambda x: -x[1])
