#!/usr/bin/env python3
"""
gen_codebook.py — Gom TOÀN BỘ mã nguồn thành 1 file HTML xem được trong trình duyệt
(không cần tải zip, không cần cài gì).

Dùng khi: bạn muốn đọc/copy code ngay trên điện thoại hoặc máy không tải được .zip.

Chạy: python3 tools/gen_codebook.py
"""
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ANISTREAM_CODEBOOK.html")

# thứ tự nhóm hiển thị
GROUPS = [
    ("📌 Bắt đầu", ["BAT_DAU_TU_DAY.md", "HUONG_DAN_CHAY.md", "VIEC_CAN_LAM.md", "VI_SAO_CHI_XEM_DUOC_MOT_SO.md", "README.md"]),
    ("🧭 Quyết định & lộ trình", ["DECISION.md", "CHON_MO_HINH.md",
                                   "LO_TRINH_ANIME_APP.md", "anime_sources.md"]),
    ("📱 Flutter app", ["app/pubspec.yaml", "app/README.md", "app/lib"]),
    ("🗄️ Database", ["db/schema.sql"]),
    ("⚡ Backend (Edge Functions)", ["supabase/"]),
    ("🐍 Ingest worker", ["ingest/"]),
    ("🛠 Tools & scripts", ["tools/", "scripts/"]),
]

TEXT_EXT = {".md", ".dart", ".ts", ".py", ".sql", ".yaml", ".yml", ".toml",
            ".sh", ".ps1", ".json", ".example", ".gitignore"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".dart_tool", "build"}
SKIP_FILES = {"ANISTREAM_CODEBOOK.html", "mock_data.dart", "mock_data_pretty.txt"}

MAX_BYTES = 120_000          # file lớn hơn → cắt bớt


def collect():
    files = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith('.')]
        for f in sorted(fns):
            if f in SKIP_FILES:
                continue
            if os.path.splitext(f)[1] not in TEXT_EXT:
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
            files.append(rel)
    return sorted(files)


def read(rel):
    p = os.path.join(ROOT, rel)
    try:
        src = open(p, encoding="utf-8").read()
    except Exception as e:
        return f"// không đọc được: {e}"
    if len(src) > MAX_BYTES:
        src = src[:MAX_BYTES] + f"\n\n… (đã cắt — file gốc {len(src)/1024:.0f} KB)"
    return src


def badge(rel):
    ext = os.path.splitext(rel)[1]
    return {
        ".dart": ("Dart", "#54c5f8"), ".ts": ("TS", "#3178c6"),
        ".py": ("Py", "#ffd43b"), ".sql": ("SQL", "#e38c00"),
        ".md": ("MD", "#a0aec0"), ".sh": ("sh", "#89e051"),
        ".ps1": ("ps1", "#89e051"), ".json": ("json", "#cbcb41"),
        ".yaml": ("yaml", "#cb171e"), ".toml": ("toml", "#9c4221"),
    }.get(ext, (ext.lstrip(".") or "txt", "#8b94a8"))


def main():
    files = collect()
    sections = []
    used = set()

    def render_file(rel):
        src = read(rel)
        label, color = badge(rel)
        size = os.path.getsize(os.path.join(ROOT, rel))
        lines = src.count("\n") + 1
        esc = html.escape(src)
        # đánh số dòng
        numbered = "\n".join(
            f'<span class="ln">{i+1:>4}</span> {l}'
            for i, l in enumerate(esc.split("\n"))
        )
        return f'''
<details class="file" id="{html.escape(rel).replace('/','_').replace('.','_')}">
  <summary>
    <span class="tag" style="color:{color};border-color:{color}44">{label}</span>
    <span class="path">{html.escape(rel)}</span>
    <span class="meta">{size/1024:.1f} KB · {lines} dòng</span>
  </summary>
  <pre><code>{numbered}</code></pre>
</details>'''

    for title, targets in GROUPS:
        chunks = []
        for t in targets:
            if t.endswith("/"):
                for rel in files:
                    if rel.startswith(t) and rel not in used:
                        used.add(rel)
                        chunks.append(render_file(rel))
            elif os.path.isdir(os.path.join(ROOT, t)):
                for rel in files:
                    if rel.startswith(t + "/") and rel not in used:
                        used.add(rel)
                        chunks.append(render_file(rel))
            elif t in files and t not in used:
                used.add(t)
                chunks.append(render_file(t))
        if chunks:
            sections.append(f'<h2>{title}</h2>' + "".join(chunks))

    rest = [f for f in files if f not in used]
    if rest:
        sections.append('<h2>📦 Khác</h2>' + "".join(render_file(f) for f in rest))

    with open(os.path.join(ROOT, "app/lib/data/mock_data.dart"), encoding="utf-8") as f:
        mock_lines = f.read().count("\n")

    html_doc = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AniStream — Codebook ({len(files)} file)</title>
<style>
  :root{{--bg:#0b0e14;--panel:#141926;--line:#252d40;--tx:#e8ecf4;--mut:#8b94a8;--acc:#7c5cff}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--tx);padding:22px 16px 70px;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
       -webkit-text-size-adjust:100%}}
  .wrap{{max-width:1000px;margin:0 auto}}
  h1{{font-size:20px;margin:0 0 6px}}
  .sub{{color:var(--mut);font-size:12.5px;line-height:1.7;margin-bottom:22px}}
  h2{{font-size:14px;margin:28px 0 10px;padding-left:9px;border-left:3px solid var(--acc);
      text-transform:uppercase;letter-spacing:.06em;color:#c9cee0}}
  details.file{{background:var(--panel);border:1px solid var(--line);border-radius:9px;
                margin-bottom:7px;overflow:hidden}}
  summary{{padding:9px 12px;cursor:pointer;display:flex;align-items:center;gap:9px;
           font-size:12.5px;list-style:none;user-select:none}}
  summary::-webkit-details-marker{{display:none}}
  summary:hover{{background:#1a2030}}
  .tag{{font-size:9.5px;font-weight:800;border:1px solid;border-radius:4px;
        padding:1px 5px;flex:0 0 auto;text-transform:uppercase}}
  .path{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;flex:1;
         overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .meta{{color:var(--mut);font-size:10.5px;flex:0 0 auto}}
  pre{{margin:0;padding:12px;background:#0d1119;overflow:auto;max-height:560px;
       border-top:1px solid var(--line)}}
  code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
        line-height:1.62;color:#cfd8e8;white-space:pre}}
  .ln{{color:#3b4559;user-select:none}}
  .note{{background:#171d2b;border:1px solid var(--line);border-radius:9px;padding:12px 14px;
         font-size:12.5px;color:#b9c2d6;line-height:1.7;margin-bottom:18px}}
  footer{{margin-top:34px;color:#5d6577;font-size:11.5px;line-height:1.8}}
  code.inl{{background:#171d2b;padding:1px 5px;border-radius:4px;font-size:11px}}
</style></head><body><div class="wrap">
  <h1>📖 AniStream — Codebook</h1>
  <div class="sub">
    Toàn bộ <b>{len(files)} file mã nguồn + tài liệu</b> trong một trang, để bạn đọc/copy ngay
    (không cần tải zip, không cần cài gì). Bấm vào từng dòng để mở.
  </div>
  <div class="note">
    <b>Cần tải về để chạy?</b> Dùng file <code class="inl">anistream-v0.1.zip</code> (1.4 MB) ở danh sách file.
    Trang này chỉ để <i>đọc</i>.<br>
    <b>Muốn thấy UI ngay?</b> Mở <code class="inl">app/UI_PREVIEW.html</code>.<br>
    <b>Dữ liệu mẫu</b> <code class="inl">app/lib/data/mock_data.dart</code> ({mock_lines} dòng JSON thật
    từ AniList + YouTube) không in ở đây để trang nhẹ — có trong zip.
  </div>
  {''.join(sections)}
  <footer>
    Sinh tự động bởi <code class="inl">tools/gen_codebook.py</code> · {len(files)} file<br>
    AniStream không lưu trữ / không trích xuất video bên thứ ba — xem <code class="inl">DECISION.md</code> §2.
  </footer>
</div></body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"✅ {OUT} ({len(html_doc)/1024:.0f} KB) · {len(files)} file")


if __name__ == "__main__":
    main()
