"""qa.py — kiểm tra BẤT BIẾN của dữ liệu sau mỗi lần ingest.

Vì sao có file này: các lỗi tệ nhất trong dự án đều là "dữ liệu sai nhưng không
ai biết" — 23 bộ có video mà 0 tập, 8 bộ có 12 tập nhưng `episodes_total` = NULL,
1 bộ có 12 tập trong khi AniList ghi 3. Không có chỗ nào kiểm lại sau khi ghi.

Phân loại:
  · **cứng (hard)** — dữ liệu tự mâu thuẫn, phải làm đỏ job: tập vượt tổng, tập
    đánh số ≤ 0, slug trùng, cùng một URL gắn cho 2 bộ, dòng mồ côi.
  · **mềm (soft)** — thiếu nội dung nhưng không mâu thuẫn: link vượt tổng (nghi
    ghép sai mùa), bộ có link mà 0 tập, bộ không biết tổng số tập.

Chỉ đọc bằng `select_all` (tự phân trang) — PostgREST cắt ở 1000 dòng, đọc thiếu
thì "kiểm tra" cũng thành vô nghĩa.
"""
from typing import Any, Dict, List


def collect(DB) -> Dict[str, Any]:
    """Gom dữ liệu tối thiểu rồi tính vi phạm. Không in, không ghi DB."""
    anime = DB.select_all("anime", "select=id,slug,episodes_total,status")
    eps = DB.select_all("episodes", "select=anime_id,number")
    links = DB.select_all(
        "streaming_links",
        "select=anime_id,episode_number,url,platform,region,kind,is_verified",
    )

    by_id = {a["id"]: a for a in anime}
    slug_seen, slug_dup = {}, []
    for a in anime:
        slug = a.get("slug")
        if slug in slug_seen:
            slug_dup.append(slug)
        slug_seen[slug] = True

    eps_by_anime: Dict[int, List[int]] = {}
    for e in eps:
        eps_by_anime.setdefault(e["anime_id"], []).append(e.get("number"))

    hard: Dict[str, List[str]] = {
        "tap_vuot_tong": [],
        "tap_danh_so_sai": [],
        "slug_trung": slug_dup,
        "url_trung": [],
        "dong_mo_coi": [],
    }
    soft: Dict[str, Any] = {
        "link_vuot_tong": [],
        "bo_co_link_0_tap": [],
        "bo_khong_biet_tong": 0,
    }

    for aid, numbers in eps_by_anime.items():
        a = by_id.get(aid)
        if not a:
            hard["dong_mo_coi"].append(f"episodes.anime_id={aid}")
            continue
        bad = [n for n in numbers if not isinstance(n, int) or n <= 0]
        if bad:
            hard["tap_danh_so_sai"].append(f"{a.get('slug')}: {bad[:5]}")
        total = a.get("episodes_total")
        if isinstance(total, int) and total > 0:
            over = [n for n in numbers if isinstance(n, int) and n > total]
            if over:
                hard["tap_vuot_tong"].append(
                    f"{a.get('slug')}: {len(over)} tập > tổng {total}")

    seen_urls = {}
    link_by_anime: Dict[int, List[int]] = {}
    # Bộ có link (kể cả chỉ có "bản gộp" episode_number = 0) nhưng bảng tập trống:
    # app vẫn hiện entry 0, nhưng danh sách tập thật thì rỗng → phải cảnh báo.
    has_link: Dict[int, bool] = {}
    for l in links:
        aid = l.get("anime_id")
        if aid not in by_id:
            hard["dong_mo_coi"].append(f"streaming_links.anime_id={aid}")
            continue
        key = (l.get("platform"), l.get("url"))
        if key in seen_urls and seen_urls[key] != aid:
            hard["url_trung"].append(f"{l.get('url')} → anime {seen_urls[key]} & {aid}")
        seen_urls[key] = aid
        has_link[aid] = True
        n = l.get("episode_number")
        if isinstance(n, int) and n > 0:
            link_by_anime.setdefault(aid, []).append(n)
        a = by_id[aid]
        total = a.get("episodes_total")
        if isinstance(n, int) and isinstance(total, int) and total > 0 and n > total:
            soft["link_vuot_tong"].append(f"{a.get('slug')}: tập {n} > {total}")

    for aid in has_link:
        if not eps_by_anime.get(aid):
            soft["bo_co_link_0_tap"].append(by_id[aid].get("slug"))

    soft["bo_khong_biet_tong"] = sum(
        1 for a in anime if not a.get("episodes_total"))
    soft["link_vuot_tong"] = sorted(set(soft["link_vuot_tong"]))
    return {
        "tong_bo": len(anime),
        "tong_tap": len(eps),
        "tong_link": len(links),
        "hard": {k: v for k, v in hard.items() if v},
        "soft": soft,
    }


def has_hard(violations: Dict[str, Any]) -> bool:
    return bool(violations.get("hard"))


def report(violations: Dict[str, Any]) -> str:
    """Chuỗi báo cáo (để in ra log/CI)."""
    hard, soft = violations["hard"], violations["soft"]
    lines = [
        f"  · {violations['tong_bo']} bộ · {violations['tong_tap']} tập · "
        f"{violations['tong_link']} link",
    ]
    if hard:
        lines.append("  ✗ VI PHẠM CỨNG (dữ liệu tự mâu thuẫn):")
        for kind, items in hard.items():
            lines.append(f"      - {kind}: {len(items)}")
            for it in items[:5]:
                lines.append(f"          · {it}")
    else:
        lines.append("  ✓ không có vi phạm cứng")
    if soft["link_vuot_tong"]:
        lines.append(f"  ⚠ link vượt tổng số tập: {len(soft['link_vuot_tong'])} "
                     f"(nghi ghép sai mùa — chạy `python3 -m ingest.audit` để soi)")
        for it in soft["link_vuot_tong"][:5]:
            lines.append(f"      · {it}")
    if soft["bo_co_link_0_tap"]:
        lines.append(f"  ⚠ bộ có link nhưng 0 tập: {len(soft['bo_co_link_0_tap'])} "
                     f"({', '.join(str(x) for x in soft['bo_co_link_0_tap'][:5])})")
    if soft["bo_khong_biet_tong"]:
        lines.append(f"  ⚠ bộ không rõ tổng số tập: {soft['bo_khong_biet_tong']}")
    return "\n".join(lines)
