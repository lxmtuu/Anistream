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


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
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


def rank_candidates(name: str, candidates: List[Dict]) -> List[Tuple[Dict, float]]:
    return sorted(((c, score_media(name, c)) for c in candidates), key=lambda x: -x[1])
