"""
audit.py — Soi lại `streaming_links` đã ghi: có link nào bị gán SAI SỐ TẬP không?

Vì sao cần: `parse_title` cũ lấy số đầu tiên sau chữ "Tập", nên video gộp
`[Bản Lồng Tiếng] One Punch Man - Tập 01-24` (1 video = 24 tập) bị lưu thành
`episode_number = 1`. Bản mới đã sửa, nhưng dữ liệu CŨ vẫn còn sai và không có
cách nào biết nếu không đọc lại tiêu đề gốc của từng video.

Cách làm (không cần YouTube API key, không trích xuất stream):
  1. Đọc mọi link `free_legal`
  2. Link chưa có `source_title` → hỏi oEmbed công khai
     (`https://www.youtube.com/oembed?url=…&format=json`) để lấy tiêu đề
  3. Parse lại tiêu đề bằng `youtube.parse_title` (bản mới) và so với số tập đã lưu
  4. In báo cáo theo bộ; `--fix` thì ghi lại `source_title`, sửa số tập, xoá link
     không nhận dạng được

Chạy thử (không ghi gì):

    python3 -m ingest.audit

Sửa thật:

    python3 -m ingest.audit --fix

Chỉ một bộ / giới hạn số link:

    python3 -m ingest.audit --slug one-punch-man
    python3 -m ingest.audit --limit 50
"""
import argparse
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from . import config, youtube
from . import db as dbmod

RE_YT = re.compile(r"(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})")
OEMBED = "https://www.youtube.com/oembed"
SLEEP = 0.15          # lịch sự với YouTube, không phải giới hạn cứng


def video_id(url: str) -> Optional[str]:
    m = RE_YT.search(url or "")
    return m.group(1) if m else None


def fetch_title(video_id_: str) -> Optional[str]:
    """Tiêu đề video qua oEmbed công khai. None nếu không lấy được."""
    try:
        r = requests.get(
            OEMBED,
            params={"url": f"https://www.youtube.com/watch?v={video_id_}", "format": "json"},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return (r.json() or {}).get("title") or None
    except Exception:
        return None


# ─────────────────────────────────────────── phân loại (phần thuần, dễ test)
# Mức độ: "xoa" nặng nhất (link không dùng được) → "sai_so_tap" → "vuot_tong" → "ok"
SEVERITY = {"xoa": 0, "gop_ca_bo": 1, "sai_so_tap": 2, "vuot_tong": 3, "ok": 4}


def classify(
    episode_number: int,
    parsed: Optional[Dict],
    episodes_total: Optional[int],
) -> Tuple[str, str]:
    """Quyết định phải làm gì với 1 link. Trả (hành_động, giải_thích).

    · `xoa`        — tiêu đề không nhận dạng được / là bản gộp MỘT PHẦN → không có
                     số tập nào đúng, giữ lại chỉ gây sai.
    · `gop_ca_bo`  — tiêu đề là bản gộp CẢ BỘ (đã parse ra 0) nhưng DB đang lưu > 0.
    · `sai_so_tap` — parse ra số khác số đang lưu.
    · `vuot_tong`  — số tập lớn hơn `episodes_total` của AniList → nghi link thuộc
                     bộ/mùa khác (vd Fairy Tail 277 tập gắn vào entry 175 tập).
    """
    if not parsed:
        return "xoa", "tiêu đề không nhận dạng được (hoặc bản gộp một phần)"
    new = parsed.get("episode") or 0
    if new == 0 and episode_number > 0:
        return "gop_ca_bo", f"đang lưu tập {episode_number}, thật ra là bản gộp cả bộ"
    if new != episode_number:
        return "sai_so_tap", f"đang lưu tập {episode_number}, tiêu đề nói tập {new}"
    if episodes_total and episode_number > episodes_total:
        return "vuot_tong", (f"tập {episode_number} > tổng {episodes_total} của AniList "
                             f"→ nghi thuộc bộ/mùa khác")
    return "ok", ""


def audit_rows(
    rows: List[Dict],
    title_of: Callable[[Dict], Optional[str]],
    parse_fn: Callable[[str], Optional[Dict]] = youtube.parse_title,
) -> Tuple[List[Dict], Dict[str, int]]:
    """Duyệt rows, trả (danh sách phát hiện, đếm theo hành động).

    `rows`: [{id, episode_number, url, source_title, anime:{slug, episodes_total}}]
    `title_of(row)`: lấy tiêu đề — cho phép test truyền hàm giả.
    """
    findings: List[Dict] = []
    counts: Dict[str, int] = {k: 0 for k in SEVERITY}
    for row in rows:
        anime = row.get("anime") or {}
        # Ưu tiên tiêu đề đã có trong DB → không gọi mạng vô ích
        title = row.get("source_title") or title_of(row)
        parsed = parse_fn(title) if title else None
        action, why = classify(
            int(row.get("episode_number") or 0), parsed,
            anime.get("episodes_total"),
        )
        counts[action] = counts.get(action, 0) + 1
        if action == "ok":
            continue
        findings.append({
            "id": row.get("id"),
            "slug": anime.get("slug") or "",
            "episode_number": int(row.get("episode_number") or 0),
            "new_episode": (parsed or {}).get("episode"),
            "episodes_total": anime.get("episodes_total"),
            "action": action,
            "why": why,
            "title": title or "",
            "url": row.get("url") or "",
            "source_title": row.get("source_title"),
        })
    # Nặng nhất lên đầu để đọc báo cáo là thấy việc cần làm trước
    findings.sort(key=lambda f: (SEVERITY.get(f["action"], 9), f["slug"],
                                 f["episode_number"]))
    return findings, counts


def group_by_slug(findings: List[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for f in findings:
        out.setdefault(f["slug"] or "(không rõ)", []).append(f)
    for v in out.values():
        v.sort(key=lambda f: (SEVERITY.get(f["action"], 9), f["episode_number"]))
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


# ─────────────────────────────────────────── chạy thật
SQL_COLS = ("id, episode_number, url, source_title, "
            "anime(id, slug, episodes_total)")


# Kênh → mã vùng dùng trong `streaming_links.region`
CHANNEL_REGION = {"muse_vn": "VN", "ani_one_asia": "AS"}


def load_links(DB, slug: str = "", limit: int = 0, region: str = "") -> List[Dict]:
    q = (f"select={SQL_COLS}&kind=eq.free_legal&is_verified=eq.true"
         f"&order=anime_id.asc,episode_number.asc")
    if slug:
        # PostgREST: lọc theo bảng nhúng bằng `anime.slug`
        q += f"&anime.slug=eq.{slug}"
    if region:
        q += f"&region=eq.{region}"
    if limit:
        q += f"&limit={int(limit)}"
    return DB.select("streaming_links", q)


def count_other_regions(DB, keep: str) -> int:
    """Số link của kênh KHÁC (dùng để báo trước khi xoá)."""
    rows = DB.select_all("streaming_links",
                         "select=id&kind=eq.free_legal&region=neq." + keep)
    return len(rows)


def run(DB, slug: str = "", limit: int = 0, fix: bool = False,
        prune_over_total: bool = False, channel: str = "",
        title_fetcher: Callable[[str], Optional[str]] = fetch_title) -> Dict[str, int]:
    print("\n▶ Audit streaming_links — có link nào gán sai số tập?")
    region = CHANNEL_REGION.get(channel, channel)
    if region:
        print(f"  · chỉ xét kênh {channel or region} (region={region})")
    rows = load_links(DB, slug, limit, region)
    print(f"  · {len(rows)} link free_legal"
          + (f" (slug={slug})" if slug else ""))
    if not rows:
        print("  ⚠ không đọc được link nào (kiểm SUPABASE_URL/SERVICE_KEY)")
        return {"link": 0}

    missing = sum(1 for r in rows if not r.get("source_title"))
    had_title = {r["id"] for r in rows if r.get("source_title")}
    print(f"  · {missing} link chưa có source_title → sẽ lấy tiêu đề qua oEmbed")

    def title_of(row: Dict) -> Optional[str]:
        if row.get("source_title"):
            return row["source_title"]
        vid = video_id(row.get("url") or "")
        if not vid:
            return None
        t = title_fetcher(vid)
        time.sleep(SLEEP)
        if t:
            row["source_title"] = t      # nhớ lại để bước --fix ghi được
        return t

    # In tiến độ, vì 500 link × 0.15s ≈ 1,5 phút
    done = {"n": 0}
    raw_title_of = title_of

    def with_progress(row: Dict) -> Optional[str]:
        done["n"] += 1
        if done["n"] % 50 == 0:
            print(f"    … đọc tiêu đề {done['n']}/{len(rows)}")
        return raw_title_of(row)

    findings, counts = audit_rows(rows, with_progress)
    total = len(rows)
    bad = total - counts.get("ok", 0)

    print(f"\n  Kết quả: {counts.get('ok', 0)}/{total} link đúng, {bad} cần xử lý")
    for action, label in (("xoa", "XOÁ (tiêu đề không dùng được)"),
                          ("gop_ca_bo", "sửa thành bản gộp cả bộ (tập 0)"),
                          ("sai_so_tap", "sửa số tập"),
                          ("vuot_tong", "vượt tổng số tập AniList (cần xem tay)")):
        if counts.get(action):
            print(f"    · {counts[action]:>4}  {label}")

    if findings:
        print("\n  Theo bộ:")
        for slug_, items in group_by_slug(findings).items():
            acts = {}
            for f in items:
                acts[f["action"]] = acts.get(f["action"], 0) + 1
            detail = ", ".join(f"{k}={v}" for k, v in acts.items())
            tong = next((f["episodes_total"] for f in items if f["episodes_total"]), None)
            print(f"    - {slug_}  ({len(items)} link; {detail}"
                  + (f"; tổng {tong} tập)" if tong else ")"))
        print("\n  Chi tiết (tối đa 25 dòng):")
        for f in findings[:25]:
            print(f"    [{f['action']}] {f['slug']} ep{f['episode_number']}"
                  f" — {f['why']}")
            if f["title"]:
                print(f"        ↳ {f['title'][:90]}")

    if not fix:
        print("\n  (chỉ đọc, không ghi gì. Thêm --fix để sửa.)")
        DB.log_ingest("audit", "links", True, bad)
        return {"link": total, "bad": bad, **counts}

    # ── ghi thật ──
    fixed_title = fixed_ep = deleted = pruned = 0
    for row in rows:
        if row.get("source_title") and row["id"] not in had_title:
            DB.patch("streaming_links", {"id": row["id"]},
                     {"source_title": row["source_title"][:300]})
            fixed_title += 1

    for f in findings:
        if f["action"] == "xoa":
            DB.delete("streaming_links", {"id": f["id"]})
            deleted += 1
        elif f["action"] in ("gop_ca_bo", "sai_so_tap") and f["new_episode"] is not None:
            DB.patch("streaming_links", {"id": f["id"]},
                     {"episode_number": int(f["new_episode"])})
            fixed_ep += 1
        elif f["action"] == "vuot_tong" and prune_over_total:
            DB.delete("streaming_links", {"id": f["id"]})
            pruned += 1

    if region:
        others = count_other_regions(DB, region)
        if others:
            print(f"\n  · {others} link của kênh khác (region ≠ {region}) — xoá vì "
                  f"chỉ giữ kênh {channel or region}")
            # Lấy id rồi xoá từng dòng (PostgREST không có DELETE … WHERE IN qua
            # query string an toàn; số lượng nhỏ nên xoá từng dòng là ổn)
            extra = DB.select_all("streaming_links",
                                  f"select=id&kind=eq.free_legal&region=neq.{region}")
            for r in extra:
                DB.delete("streaming_links", {"id": r["id"]})
            print(f"  ✓ đã xoá {len(extra)} link kênh khác")

    print(f"\n  ✓ đã ghi source_title: {fixed_title}")
    print(f"  ✓ sửa số tập: {fixed_ep}")
    print(f"  ✓ xoá (tiêu đề không dùng được): {deleted}")
    if prune_over_total:
        print(f"  ✓ xoá (vượt tổng số tập): {pruned}")
    DB.log_ingest("audit", "links", True, fixed_title + fixed_ep + deleted + pruned)
    return {"link": total, "bad": bad, "fixed_title": fixed_title,
            "fixed_ep": fixed_ep, "deleted": deleted, "pruned": pruned}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Soi streaming_links xem có link gán sai số tập không")
    ap.add_argument("--slug", default="", help="chỉ kiểm 1 bộ")
    ap.add_argument("--limit", type=int, default=0, help="giới hạn số link đọc")
    ap.add_argument("--fix", action="store_true",
                    help="GHI: lưu source_title, sửa số tập, xoá link rác")
    ap.add_argument("--prune-over-total", action="store_true",
                    help="kèm --fix: xoá luôn link vượt tổng số tập AniList")
    ap.add_argument("--channel", default="",
                    help="chỉ xét 1 kênh: muse_vn | ani_one_asia "
                         "(kèm --fix sẽ XOÁ link của kênh khác)")
    args = ap.parse_args(argv)

    try:
        DB = dbmod.DB()
    except RuntimeError as e:
        print(f"\n✗ {e}")
        return 2
    try:
        run(DB, args.slug, args.limit, args.fix, args.prune_over_total,
            args.channel)
    except KeyboardInterrupt:
        print("\n… dừng theo yêu cầu")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
