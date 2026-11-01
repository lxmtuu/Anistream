#!/usr/bin/env python3
"""
gen_preview.py — Dựng `app/UI_PREVIEW.html`: bản mô phỏng tĩnh 3 màn hình chính,
dùng ĐÚNG dữ liệu trong mock_data.dart (poster/tiêu đề thật), ảnh nhúng base64
để xem được trong trình xem không có mạng.

Mục đích: duyệt UX trước khi build Flutter (nhanh hơn nhiều so với sửa code).

Chạy: python3 tools/gen_preview.py
"""
import base64
import io
import json
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK = os.path.join(ROOT, "app", "lib", "data", "mock_data.dart")
OUT = os.path.join(ROOT, "app", "UI_PREVIEW.html")


def load_mock() -> dict:
    src = open(MOCK, encoding="utf-8").read()
    js = re.search(r"r'''\n(.*)\n'''", src, re.S).group(1)
    return json.loads(js)


def img_b64(url: str, w: int = 220) -> str:
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "AniStreamPreview/1.0"})
        r.raise_for_status()
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((w, w * 3))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=76)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def main():
    d = load_mock()
    by_id = {a["id"]: a for a in d["anime"]}
    shelves = d["shelves"]
    free = [by_id[i] for i in shelves[0]["ids"] if i in by_id]
    # chọn bộ có nhiều tập nhất làm hero để màn Detail trông đầy đủ
    hero = max(free, key=lambda a: len(a.get("episodes") or [])) if free else d["anime"][0]

    print("· tải poster…", file=sys.stderr)
    posters = {}
    for a in (free[:8] + [hero] + d["anime"][:6]):
        key = a["id"]
        if key not in posters:
            posters[key] = img_b64(a.get("cover"))
    banner = img_b64(hero.get("banner") or hero.get("cover"), 420)

    def card(a, w=104):
        img = posters.get(a["id"], "")
        badge = ('<span class="free">FREE</span>' if a.get("is_free") else "")
        score = (f'<span class="sc">★ {a["score"]:.1f}</span>'
                 if a.get("score") else "")
        return f'''
        <div class="card" style="width:{w}px">
          <div class="poster" style="height:{int(w*1.45)}px">
            {f'<img src="{img}" alt="">' if img else ''}
            {badge}{score}
          </div>
          <div class="ctitle">{a["title"][:34]}</div>
        </div>'''

    shelf_html = ""
    for s in shelves[:3]:
        items = [by_id[i] for i in s["ids"] if i in by_id][:8]
        shelf_html += f'''
        <div class="shelf">
          <div class="shelf-t">{s["title"]}</div>
          <div class="row">{"".join(card(a) for a in items)}</div>
        </div>'''

    # chi tiết
    detail = hero
    eps = detail.get("episodes") or []
    cells = []
    for e in eps[:8]:
        num = e["number"] if e["number"] else "FULL"
        cells.append(f'<div class="ep">{num}{"<i>▶</i>" if e.get("video_id") else ""}</div>')
    # bù cho đủ 8 ô để thấy đúng layout grid (ô không ▶ = chưa có bản phát chính thức)
    n = (max([e["number"] for e in eps] or [0])) + 1
    while len(cells) < 8:
        cells.append(f'<div class="ep" style="border-color:#252D40;color:#8B94A8">{n}</div>')
        n += 1
    ep_cells = "".join(cells)
    platforms = "".join(
        f'<span class="plat">{p["name"]}</span>' for p in detail.get("platforms", [])
    )

    # lịch
    slots = d["schedule"][:8]
    sched_rows = ""
    for s in slots:
        a = by_id.get(s["anime_id"])
        if not a:
            continue
        img = posters.get(a["id"], "")
        hhmm = s["airing_at"][11:16]
        sched_rows += f'''
        <div class="slot">
          <div class="time">{hhmm}</div>
          <div class="thumb">{f'<img src="{img}" alt="">' if img else ''}</div>
          <div class="sinfo">
            <div class="stitle">{a["title"][:26]}</div>
            <div class="smeta">Tập {s["episode"]} · sắp chiếu</div>
          </div>
          {('<span class="free sm">FREE</span>' if a.get("is_free") else "")}
        </div>'''

    html = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AniStream — UI Preview</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;padding:26px 20px 50px;background:radial-gradient(900px 500px at 60% -10%,#1c1a3d,#0b0e14 60%);
       color:#E8ECF4;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
  h1{{font-size:19px;margin:0 0 4px;text-align:center}}
  .sub{{text-align:center;color:#8B94A8;font-size:12px;margin-bottom:26px;line-height:1.6}}
  .frames{{display:flex;gap:26px;justify-content:center;align-items:flex-start;flex-wrap:wrap}}
  .phone{{width:308px;border-radius:26px;background:#0B0E14;border:1px solid #2b3448;
          box-shadow:0 24px 60px -20px #000;overflow:hidden;position:relative}}
  .notch{{height:22px;display:flex;align-items:center;justify-content:center}}
  .notch i{{width:56px;height:5px;border-radius:3px;background:#222a3a;display:block}}
  .screen{{height:596px;overflow:hidden;position:relative}}
  .cap{{text-align:center;font-size:11px;color:#7a8399;padding:9px 0 12px;border-top:1px solid #1b2231}}
  .cap b{{color:#c9cee0}}

  /* home */
  .hero{{position:relative;height:250px}}
  .hero img{{width:100%;height:100%;object-fit:cover;display:block}}
  .hero .grad{{position:absolute;inset:0;background:linear-gradient(180deg,
      rgba(11,14,20,.55),rgba(11,14,20,.35) 45%,#0B0E14)}}
  .hero .txt{{position:absolute;left:14px;right:14px;bottom:10px}}
  .pills{{display:flex;gap:5px;margin-bottom:7px}}
  .pill{{font-size:8.5px;font-weight:800;letter-spacing:.4px;padding:2px 6px;border-radius:4px;
         background:#3DDC97;color:#06281B}}
  .pill.g{{background:#1B2131;color:#E8ECF4}}
  .htitle{{font-size:20px;font-weight:800;line-height:1.15;letter-spacing:-.02em}}
  .hmeta{{font-size:10px;color:#8B94A8;margin-top:3px}}
  .btns{{display:flex;gap:8px;margin-top:11px}}
  .btn{{flex:1;text-align:center;font-size:11.5px;font-weight:700;padding:9px 0;border-radius:9px;
        background:#7C5CFF;color:#fff}}
  .btn.o{{background:transparent;border:1px solid #2b3448;color:#E8ECF4;flex:0 0 88px;font-weight:600}}
  .shelf{{margin-top:14px}}
  .shelf-t{{font-size:11.5px;font-weight:700;padding:0 14px 8px}}
  .row{{display:flex;gap:8px;padding:0 14px;overflow:hidden}}
  .card{{flex:0 0 auto}}
  .poster{{position:relative;border-radius:8px;overflow:hidden;background:#1B2131}}
  .poster img{{width:100%;height:100%;object-fit:cover;display:block}}
  .free{{position:absolute;top:4px;left:4px;font-size:7.5px;font-weight:800;background:#3DDC97;
         color:#06281B;padding:1px 4px;border-radius:3px}}
  .free.sm{{position:static;font-size:7.5px;padding:1px 4px}}
  .sc{{position:absolute;bottom:4px;right:4px;font-size:8px;font-weight:700;background:rgba(0,0,0,.72);
       padding:1px 4px;border-radius:3px}}
  .ctitle{{font-size:9.5px;line-height:1.25;margin-top:4px;height:24px;overflow:hidden;color:#cfd6e4}}

  /* tabs */
  .tabs{{position:absolute;bottom:0;left:0;right:0;height:52px;background:#141926;
         border-top:1px solid #252D40;display:flex;align-items:center}}
  .tab{{flex:1;text-align:center;font-size:8.5px;color:#8B94A8;line-height:1.5}}
  .tab.on{{color:#7C5CFF;font-weight:700}}
  .tab .ic{{font-size:14px;display:block}}

  /* detail */
  .dbanner{{height:150px;position:relative}}
  .dbanner img{{width:100%;height:100%;object-fit:cover}}
  .dbanner .grad{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,14,20,.5),#0B0E14)}}
  .dbody{{padding:0 14px;margin-top:-42px;position:relative}}
  .drow{{display:flex;gap:11px}}
  .dposter{{width:82px;height:120px;border-radius:9px;overflow:hidden;flex:0 0 auto;
            border:1px solid #2b3448}}
  .dposter img{{width:100%;height:100%;object-fit:cover}}
  .dtitle{{font-size:15px;font-weight:800;line-height:1.2}}
  .chips{{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px}}
  .chip{{font-size:8.5px;padding:2px 5px;border-radius:4px;background:#1B2131;border:1px solid #252D40}}
  .chip.g{{color:#3DDC97}}
  .fullbtn{{margin-top:12px;background:#7C5CFF;border-radius:9px;text-align:center;
            font-size:12px;font-weight:700;padding:11px 0}}
  .platrow{{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}}
  .plat{{font-size:9px;border:1px solid #2b3448;border-radius:6px;padding:4px 8px;color:#cfd6e4}}
  .lab{{font-size:9.5px;color:#8B94A8;margin-top:13px;font-weight:700}}
  .syn{{font-size:10px;line-height:1.6;color:#C3CBDC;margin-top:6px;height:46px;overflow:hidden}}
  .epgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}}
  .ep{{background:#1B2131;border:1px solid #7C5CFFaa;border-radius:7px;height:38px;
       display:flex;flex-direction:column;align-items:center;justify-content:center;
       font-size:11px;font-weight:800}}
  .ep i{{font-size:6px;color:#7C5CFF;font-style:normal}}

  /* schedule */
  .shead{{padding:14px 14px 6px;font-size:15px;font-weight:800}}
  .sday{{font-size:10px;font-weight:800;color:#7C5CFF;padding:12px 14px 6px;letter-spacing:.3px}}
  .slot{{display:flex;align-items:center;gap:9px;padding:6px 14px}}
  .time{{font-size:10.5px;font-weight:700;width:34px;color:#cfd6e4}}
  .thumb{{width:32px;height:44px;border-radius:5px;overflow:hidden;background:#1B2131;flex:0 0 auto}}
  .thumb img{{width:100%;height:100%;object-fit:cover}}
  .sinfo{{flex:1;min-width:0}}
  .stitle{{font-size:10.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .smeta{{font-size:8.5px;color:#8B94A8;margin-top:2px}}
  footer{{text-align:center;color:#5d6577;font-size:11px;margin-top:26px;line-height:1.7}}
  code{{background:#171d2b;padding:1px 5px;border-radius:4px}}
</style></head><body>
  <h1>AniStream — UI Preview</h1>
  <div class="sub">
    Mô phỏng layout 3 màn hình chính, dùng <b>dữ liệu thật</b> từ <code>mock_data.dart</code>
    (poster AniList nhúng base64). Code thật: <code>app/lib/</code> · chạy: <code>flutter run</code>
  </div>

  <div class="frames">
    <!-- HOME -->
    <div>
      <div class="phone">
        <div class="notch"><i></i></div>
        <div class="screen">
          <div class="hero">
            {f'<img src="{banner}" alt="">' if banner else '<div style="height:100%;background:#1B2131"></div>'}
            <div class="grad"></div>
            <div class="txt">
              <div class="pills">
                <span class="pill">MIỄN PHÍ · HỢP PHÁP</span>
                <span class="pill g">★ {detail.get("score") or "—"}</span>
              </div>
              <div class="htitle">{detail["title"][:30]}</div>
              <div class="hmeta">Tập {eps[0]["number"] if eps else 1} · {len(eps)} tập xem được</div>
              <div class="btns"><div class="btn">▶ Xem ngay</div><div class="btn o">Chi tiết</div></div>
            </div>
          </div>
          {shelf_html}
        </div>
        <div class="tabs">
          <div class="tab on"><span class="ic">⌂</span>Trang chủ</div>
          <div class="tab"><span class="ic">▤</span>Lịch phát</div>
          <div class="tab"><span class="ic">⌕</span>Tìm</div>
          <div class="tab"><span class="ic">◈</span>Thư viện</div>
        </div>
      </div>
      <div class="cap"><b>Home</b> — hero + shelf, skeleton khi tải, pull-to-refresh</div>
    </div>

    <!-- DETAIL -->
    <div>
      <div class="phone">
        <div class="notch"><i></i></div>
        <div class="screen">
          <div class="dbanner">
            {f'<img src="{banner}" alt="">' if banner else ''}
            <div class="grad"></div>
          </div>
          <div class="dbody">
            <div class="drow">
              <div class="dposter">{f'<img src="{posters.get(detail["id"], "")}" alt="">' if posters.get(detail["id"]) else ''}</div>
              <div style="flex:1;padding-top:44px">
                <div class="dtitle">{detail["title"][:24]}</div>
                <div class="chips">
                  <span class="chip">★ {detail.get("score") or "—"}</span>
                  <span class="chip">{detail.get("year") or "—"}</span>
                  <span class="chip">{detail.get("format") or "TV"}</span>
                  <span class="chip g">Đang chiếu</span>
                </div>
              </div>
            </div>
            <div class="fullbtn">▶ Xem tập {eps[0]["number"] if eps else 1} · miễn phí</div>
            <div class="lab">Xem trên nền tảng chính thức</div>
            <div class="platrow">{platforms or '<span class="plat">Crunchyroll</span>'}</div>
            <div class="lab">Nội dung</div>
            <div class="syn">{detail.get("synopsis", "")[:260]}</div>
            <div class="lab">Tập phim</div>
            <div class="epgrid">{ep_cells}</div>
          </div>
        </div>
        <div class="tabs">
          <div class="tab"><span class="ic">⌂</span>Trang chủ</div>
          <div class="tab"><span class="ic">▤</span>Lịch phát</div>
          <div class="tab"><span class="ic">⌕</span>Tìm</div>
          <div class="tab on"><span class="ic">◈</span>Thư viện</div>
        </div>
      </div>
      <div class="cap"><b>Detail</b> — nền tảng chính thức + grid tập (chỉ tập có ▶ phát được)</div>
    </div>

    <!-- SCHEDULE -->
    <div>
      <div class="phone">
        <div class="notch"><i></i></div>
        <div class="screen">
          <div class="shead">Lịch phát</div>
          <div class="sday">HÔM NAY</div>
          {sched_rows}
        </div>
        <div class="tabs">
          <div class="tab"><span class="ic">⌂</span>Trang chủ</div>
          <div class="tab on"><span class="ic">▤</span>Lịch phát</div>
          <div class="tab"><span class="ic">⌕</span>Tìm</div>
          <div class="tab"><span class="ic">◈</span>Thư viện</div>
        </div>
      </div>
      <div class="cap"><b>Schedule</b> — nhóm theo ngày, đếm ngược, badge FREE</div>
    </div>
  </div>

  <footer>
    Bản mô phỏng tĩnh để duyệt UX. App thật: <code>app/lib/features/…</code> ·
    Sinh lại: <code>python3 tools/gen_preview.py</code><br>
    Video trong app phát qua <b>IFrame Player API chính thức của YouTube</b> — không host, không trích xuất stream.
  </footer>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ {OUT} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
