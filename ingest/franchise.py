"""franchise.py — Muse VN đánh số tập **CỘNG DỒN** qua nhiều mùa.

VÌ SAO CẦN (đo thật 03/11/2026, đọc tiêu đề qua oEmbed — không cần API key):

    https://youtu.be/iry712JcyDc
    → "Lúc đó tôi đã chuyển sinh thành Slime - Tập 13"   ← KHÔNG có chữ "S3"

Kênh đăng mùa 3 nhưng tiêu đề chỉ còn tên bộ + số tập, và số tập **chạy tiếp từ
mùa trước**: Slime S1 = tập 1–24, S2 = 25–48, S3 = 49–72. Bằng chứng trong DB:
`ingest_unmatched.max_episode` của tên "…Slime" là **72**, của "…Slime S3" là 72,
"…Slime S2" là 48. Cùng quy luật với Re:Zero (S4 bắt đầu ở tập 86 → thấy 85),
Frieren (Phần 2 = tập 29–38), SPY×FAMILY S3 (tới 50), 100 cô bạn gái S3 (36),
Wistoria S2 (24), Shangri-La S2 (50), One Punch Man S2 (24), Vong linh… phần 2 (24).

Hệ quả nếu chỉ ghép theo TÊN: 45 video "Đại chiến người Khổng Lồ S3" (Muse đánh
1–22 vì S3 gồm 2 phần) bị chặn 10 video; 25 video "…Slime S2" rơi vào `review`
hoặc — tệ hơn — **vào nhầm mùa** (tập 13 của Slime là tập 13 của *mùa 1*, không
phải tập 13 của mùa 3).

Cách giải: dựng **chuỗi thương hiệu** từ quan hệ AniList (PREQUEL/SEQUEL), cộng
dồn số tập theo thứ tự phát sóng, rồi định tuyến số tập của video về đúng entry
+ số tập cục bộ của entry đó.

Hai kiểu đánh số đều được xử lý, chọn theo DỮ LIỆU chứ không đoán:

* ``fill``       — Muse đánh lại từ 1 mỗi mùa, nhưng một "mùa" của Muse có thể gồm
                   nhiều entry AniList (Shingeki S3 = Season 3 12 tập + Season 3
                   Part 2 10 tập ⇒ Muse đánh 1–22). Điền tiếp từ entry đã ghép.
* ``cumulative`` — Muse đánh tiếp qua cả thương hiệu (Slime, Re:Zero, Frieren…).

``plan()`` thử ``fill`` trước, chỉ nhận nếu nó phủ HẾT khoảng [lo, hi] quan sát
được trên kênh; không phủ thì thử ``cumulative``; cả hai không phủ ⇒ trả None và
job C giữ nguyên hành vi cũ (thà bỏ + báo còn hơn gán bừa).
"""
from typing import Dict, List, Optional, Tuple

from . import anilist

# Chỉ những dạng này mới nằm chung một dãy số tập. MOVIE/SPECIAL/OVA có đánh số
# riêng nên chen vào là lệch toàn bộ các mùa phía sau.
DANG_SERIES = ("TV", "TV_SHORT", "ONA")


def _eps(node: Dict) -> Optional[int]:
    n = (node or {}).get("episodes")
    return n if isinstance(n, int) and n > 0 else None


def _slim(node: Dict) -> Dict:
    return {
        "id": node.get("id"),
        "title": node.get("title") or {},
        "episodes": _eps(node),
        "format": node.get("format"),
        "startDate": node.get("startDate"),
    }


def _lien_quan(media_id: int, loai: str, cache: Optional[Dict]) -> List[Dict]:
    """Các entry ``loai`` (PREQUEL/SEQUEL) — có cache (kể cả kết quả rỗng)."""
    key = f"franchise:{loai}:{media_id}"
    if cache is not None and key in cache:
        return list(cache[key] or [])
    try:
        nodes = anilist.related(int(media_id), (loai,))
    except Exception:                       # noqa: BLE001 — AniList lỗi ≠ job chết
        return []
    nodes = [_slim(n) for n in nodes
             if n.get("id") and _eps(n)
             and (n.get("format") or "").upper() in DANG_SERIES]
    if cache is not None:
        cache[key] = nodes
    return nodes


def chain_of(anchor: Dict, cache: Optional[Dict] = None,
             depth: int = 12) -> List[Dict]:
    """Chuỗi thương hiệu chứa `anchor`, theo thứ tự phát sóng + mốc cộng dồn.

    Mỗi phần tử có thêm ``start``/``end`` = khoảng số tập CỘNG DỒN của entry đó
    trong cả thương hiệu (tập đầu tiên của mùa 1 = 1).
    """
    a = _slim(anchor or {})
    if not a.get("id") or not a.get("episodes"):
        return []

    # 1) đi ngược về mùa đầu tiên. Chỉ đi khi có ĐÚNG MỘT prequel dạng series —
    #    nhiều nhánh (spin-off, Alternative) thì dừng, không đoán.
    cur, da_nguoc = a, {a["id"]}
    for _ in range(depth):
        truoc = [p for p in _lien_quan(cur["id"], "PREQUEL", cache)
                 if p["id"] not in da_nguoc]
        if len(truoc) != 1:
            break
        cur = truoc[0]
        da_nguoc.add(cur["id"])

    # 2) đi xuôi theo SEQUEL (đánh dấu RIÊNG: mọi entry phía xuôi đều đã nằm
    #    trong `da_nguoc`, dùng chung tập đánh dấu thì bước này dừng ngay).
    chain = [cur]
    da_xuoi = {cur["id"]}
    for _ in range(depth):
        sau = [s for s in _lien_quan(cur["id"], "SEQUEL", cache)
               if s["id"] not in da_xuoi]
        if len(sau) != 1:
            break
        cur = sau[0]
        da_xuoi.add(cur["id"])
        chain.append(cur)

    # 3) mốc cộng dồn
    acc = 1
    for e in chain:
        e["start"] = acc
        e["end"] = acc + e["episodes"] - 1
        acc = e["end"] + 1
    return chain


def _fill(chain: List[Dict], i: int, hi: int) -> Dict[int, Tuple[Dict, int]]:
    out: Dict[int, Tuple[Dict, int]] = {}
    acc = 0
    for e in chain[i:]:
        for n in range(1, min(e["episodes"], hi) + 1):
            out[acc + n] = (e, n)
        acc += e["episodes"]
        if acc >= hi:
            break
    return out


def _cumulative(chain: List[Dict]) -> Dict[int, Tuple[Dict, int]]:
    out: Dict[int, Tuple[Dict, int]] = {}
    for e in chain:
        for n in range(1, e["episodes"] + 1):
            out[e["start"] + n - 1] = (e, n)
    return out


def _phu(plan: Dict[int, Tuple[Dict, int]], lo: int, hi: int) -> bool:
    return all(n in plan for n in range(max(1, lo), hi + 1))


def plan(anchor: Dict, lo: int, hi: int,
         cache: Optional[Dict] = None) -> Optional[Tuple[Dict[int, Tuple[Dict, int]], str]]:
    """Kế hoạch ``{số tập trên kênh: (entry, số tập cục bộ)}`` cho [lo, hi].

    Trả ``(plan, "fill"|"cumulative")`` hoặc ``None`` nếu không mô hình nào phủ
    hết khoảng quan sát được (khi đó job C KHÔNG được đoán).
    """
    chain = chain_of(anchor, cache)
    if not chain:
        return None
    ids = [e["id"] for e in chain]
    if anchor.get("id") not in ids:
        return None
    i = ids.index(anchor["id"])
    lo, hi = max(1, int(lo or 1)), int(hi or 0)
    if hi <= 0:
        return None

    for ten, ke in (("fill", _fill(chain, i, hi)),
                    ("cumulative", _cumulative(chain))):
        if _phu(ke, lo, hi):
            return ke, ten
    return None


def route(anchor: Dict, episode: int, lo: int, hi: int,
          cache: Optional[Dict] = None) -> Optional[Tuple[Dict, int, str]]:
    """Một video (số tập `episode`) → ``(entry, số tập cục bộ, kiểu đánh số)``."""
    kq = plan(anchor, lo, hi, cache)
    if not kq:
        return None
    ke, kieu = kq
    dich = ke.get(int(episode or 0))
    if not dich:
        return None
    return dich[0], dich[1], kieu


def goc(anchor: Dict, cache: Optional[Dict] = None) -> Optional[Dict]:
    """Entry ĐẦU TIÊN của thương hiệu (để gắn tên không kèm mùa vào đúng gốc)."""
    chain = chain_of(anchor, cache)
    return chain[0] if chain else None


def phu_hop(anchor: Dict, hi: int, cache: Optional[Dict] = None) -> Tuple[bool, str]:
    """Tập lớn nhất `hi` của kênh có nằm trong "mùa" của `anchor` không?

    Dùng cho job K: `ingest_unmatched.max_episode` là số tập CỘNG DỒN (Slime S3
    thấy tới tập 72 trong khi entry mùa 3 chỉ có 24 tập) nên `choose_entry` sẽ
    loại sạch ứng viên. Ở đây chấp nhận khi:

    * ``fill``       — dãy số bắt đầu từ chính `anchor` (Muse gộp nhiều part của
                       cùng một mùa, vd Shingeki S3 = 1–22) ⇒ hợp lệ.
    * ``cumulative`` — tập `hi` phải rơi đúng vào `anchor`; rơi vào mùa khác thì
                       `anchor` KHÔNG phải mùa của tên này ⇒ loại.
    """
    kq = plan(anchor, 1, int(hi or 0), cache)
    if not kq:
        return False, "không dựng được mô hình đánh số"
    ke, kieu = kq
    dich = ke.get(int(hi or 0))
    if not dich:
        return False, "không định tuyến được tập lớn nhất"
    node, local_ep = dich
    if kieu == "fill":
        return True, f"gộp phần trong mùa (tập {hi} → {local_ep})"
    if node.get("id") == anchor.get("id"):
        return True, f"cộng dồn qua mùa (tập {hi} → tập {local_ep} của mùa này)"
    return False, "tập lớn nhất thuộc mùa khác"
