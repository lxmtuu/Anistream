"""reassign.py — chuyển link bị gán SAI MÙA sang đúng entry mùa của nó.

Vì sao cần: Muse đánh số tập **tiếp nối qua các mùa**. Ví dụ FAIRY TAIL: Muse đăng
liên tục tập 1–277, nhưng AniList tách "FAIRY TAIL" (175 tập) và "FAIRY TAIL
(2014)" (102 tập). Ingest cũ gán tất cả vào entry mùa 1 → 102 link có số tập
176–277 vượt quá tổng 175, bị chốt chặn loại bỏ ⇒ 102 video nằm im, không ai xem
được (`fairy-tail` 66 tập trong khi Muse có 277).

Quy tắc (cố tình bảo thủ, thà bỏ sót còn hơn gán bừa):
  · chỉ xét link có `episode_number > episodes_total` của bộ đang giữ;
  · offset = `episodes_total` của bộ cũ (vì Muse đánh số tiếp nối);
  · entry đích phải là "mùa sau" theo slug (`<slug mẹ>-...`), CHƯA có link/tập nào;
  · MỌI link vượt phải ánh xạ vào [1, episodes_total của đích] — nếu lệch một cái
    là bỏ toàn bộ (không để lại nửa vời);
  · `confidence="exact"` khi số link liên tục và ánh xạ đúng bằng tổng của đích
    (ca Fairy Tail: 102 link 176–277 → 1–102, đích có 102 tập).

Dùng:
  python3 -m ingest.reassign            # chỉ in kế hoạch (không ghi)
  python3 -m ingest.reassign --apply    # ghi DB + tạo tập từ link
  python3 -m ingest.reassign --apply --only-exact   # chỉ ca khớp tuyệt đối
"""
import argparse
from typing import Any, Dict, List, Optional

from . import db as dbmod


def _candidates(parent: Dict, all_anime: List[Dict],
                busy: Dict[int, bool]) -> List[Dict]:
    """Entry có thể là 'mùa sau' của `parent` theo quy ước slug."""
    base = parent["slug"]
    out = []
    for a in all_anime:
        if a["id"] == parent["id"]:
            continue
        if not (a.get("slug") or "").startswith(base + "-"):
            continue
        if busy.get(a["id"]):
            continue                      # đã có link/tập → không đụng
        out.append(a)
    return out


def plan(DB) -> List[Dict[str, Any]]:
    """Tính kế hoạch chuyển link. Không ghi gì."""
    anime = DB.select_all(
        "anime", "select=id,slug,title_romaji,episodes_total")
    by_id = {a["id"]: a for a in anime}
    links = DB.select_all(
        "streaming_links",
        "select=id,anime_id,episode_number&kind=eq.free_legal&episode_number=gt.0",
    )

    busy: Dict[int, bool] = {a["id"]: False for a in anime}
    over: Dict[int, List[Dict]] = {}
    for l in links:
        aid = l.get("anime_id")
        if aid in busy:
            busy[aid] = True
        a = by_id.get(aid)
        total = (a or {}).get("episodes_total")
        if not a or not isinstance(total, int) or total <= 0:
            continue
        if (l.get("episode_number") or 0) > total:
            over.setdefault(aid, []).append(l)

    plans: List[Dict[str, Any]] = []
    for aid, bad in sorted(over.items(), key=lambda kv: -len(kv[1])):
        parent = by_id[aid]
        offset = int(parent["episodes_total"])
        nums = sorted(int(l["episode_number"]) for l in bad)

        # đích phải "trống" (không link, không tập) — `busy` đủ vì mọi bộ có link
        # hoặc có tập đều đã được đánh dấu ở trên/ dưới.
        cands = _candidates(parent, anime, busy)
        chosen: Optional[Dict] = None
        for c in cands:
            total_c = c.get("episodes_total")
            mapped = [n - offset for n in nums]
            if min(mapped) < 1:
                continue
            if isinstance(total_c, int) and total_c > 0 and max(mapped) > total_c:
                continue
            chosen = c
            break

        entry: Dict[str, Any] = {
            "from_id": aid,
            "from_slug": parent["slug"],
            "offset": offset,
            "links": [l["id"] for l in bad],
            "nums": nums,
            "mapped": [n - offset for n in nums],
            "to_id": None, "to_slug": None, "to_total": None,
            "confidence": "none",
            "reason": "",
        }
        if not chosen:
            entry["reason"] = "không có entry mùa sau trống để nhận"
            plans.append(entry)
            continue

        total_c = chosen.get("episodes_total")
        contiguous = len(set(nums)) == len(nums) and nums[-1] - nums[0] + 1 == len(nums)
        exact = (contiguous and isinstance(total_c, int) and total_c > 0
                 and entry["mapped"][0] == 1 and entry["mapped"][-1] == total_c)
        entry.update({
            "to_id": chosen["id"],
            "to_slug": chosen["slug"],
            "to_total": total_c,
            "confidence": "exact" if exact else "probable",
        })
        plans.append(entry)
    return plans


def report(plans: List[Dict]) -> str:
    if not plans:
        return "  ✓ không có link nào vượt tổng số tập"
    lines = []
    for p in plans:
        if p["to_id"]:
            lines.append(
                f"  → {p['from_slug']}: {len(p['links'])} link tập "
                f"{p['nums'][0]}–{p['nums'][-1]} → {p['to_slug']} "
                f"(tập {p['mapped'][0]}–{p['mapped'][-1]} / {p['to_total'] or '?'} tập) "
                f"[{p['confidence']}]")
        else:
            lines.append(f"  ✗ {p['from_slug']}: {len(p['links'])} link vượt tổng "
                         f"({p['nums'][0]}–{p['nums'][-1]}) — {p['reason']}")
    return "\n".join(lines)


def apply(DB, plans: List[Dict], only_exact: bool = False) -> int:
    """Ghi thay đổi. Trả số link đã chuyển."""
    moved = 0
    for p in plans:
        if not p["to_id"]:
            continue
        if only_exact and p["confidence"] != "exact":
            print(f"  · bỏ qua {p['from_slug']} (độ tin cậy {p['confidence']})")
            continue
        for link_id, new_num in zip(p["links"], p["mapped"]):
            DB.patch("streaming_links", {"id": link_id},
                     {"anime_id": p["to_id"], "episode_number": new_num})
            moved += 1

    if moved:
        # Link đã sang đúng mùa → tạo danh sách tập cho mùa đó.
        from .main import job_link_episodes      # import muộn, tránh vòng lặp
        job_link_episodes(DB)
    return moved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Chuyển link bị gán sai mùa sang đúng entry mùa của nó")
    ap.add_argument("--apply", action="store_true", help="ghi vào DB (mặc định chỉ in)")
    ap.add_argument("--only-exact", action="store_true",
                    help="chỉ chuyển ca khớp tuyệt đối (an toàn nhất)")
    args = ap.parse_args(argv)

    DB = dbmod.DB()
    print("\n▶ Chuyển link vượt tổng số tập sang mùa đúng")
    plans = plan(DB)
    print(report(plans))
    if not args.apply:
        print("\n  (chưa ghi gì — thêm --apply để thực hiện)")
        return 0
    n = apply(DB, plans, args.only_exact)
    DB.log_ingest("links", "reassign", True, n)
    print(f"\n  ✓ đã chuyển {n} link")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
