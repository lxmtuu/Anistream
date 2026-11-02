"""Test `python3 -m ingest.audit` — soi link gán sai số tập.

Bối cảnh: `parse_title` cũ lấy số đầu tiên sau "Tập" nên video gộp
`[Bản Lồng Tiếng] One Punch Man - Tập 01-24` bị lưu thành episode 1. Bản mới đã
sửa, nhưng dữ liệu CŨ vẫn sai và không có `source_title` để biết video nào.
Audit lấy lại tiêu đề qua oEmbed rồi đối chiếu.
"""
import io
import unittest
from contextlib import redirect_stdout

from ingest import audit, db as dbmod, youtube

ROW = {
    "id": 1, "episode_number": 1, "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
    "source_title": None, "anime": {"slug": "one-punch-man", "episodes_total": 12},
}


class TestVideoId(unittest.TestCase):
    def test_cac_dang_url(self):
        self.assertEqual(audit.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                         "dQw4w9WgXcQ")
        self.assertEqual(audit.video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertIsNone(audit.video_id("https://example.com/x"))
        self.assertIsNone(audit.video_id(""))


class TestClassify(unittest.TestCase):
    def test_ban_gop_ca_bo_bi_luu_thanh_tap(self):
        # Ca thật: One Punch Man "Tập 01-24"
        parsed = youtube.parse_title("[Bản Lồng Tiếng] One Punch Man - Tập 01-24")
        action, why = audit.classify(1, parsed, 12)
        self.assertEqual(action, "gop_ca_bo")
        self.assertIn("bản gộp", why)

    def test_tieu_de_khong_dung_duoc_thi_xoa(self):
        action, _ = audit.classify(1, None, 12)
        self.assertEqual(action, "xoa")

    def test_dai_tap_mot_phan_cung_bi_xoa(self):
        # "Tập 1000-1099" → parse_title trả None → xoá, không gán bừa
        parsed = youtube.parse_title("Crayon Shin-chan Tập 1000-1099")
        self.assertIsNone(parsed)
        self.assertEqual(audit.classify(1000, parsed, 60)[0], "xoa")

    def test_so_tap_khac_thi_sua(self):
        parsed = youtube.parse_title("One Punch Man - Tập 7")
        self.assertEqual(audit.classify(1, parsed, 12)[0], "sai_so_tap")

    def test_vuot_tong_so_tap(self):
        # Ca thật: fairy-tail 277 link nhưng AniList nói 175 tập
        parsed = youtube.parse_title("Fairy Tail - Tập 277")
        action, why = audit.classify(277, parsed, 175)
        self.assertEqual(action, "vuot_tong")
        self.assertIn("175", why)

    def test_link_dung_thi_ok(self):
        parsed = youtube.parse_title("One Punch Man - Tập 3")
        self.assertEqual(audit.classify(3, parsed, 12), ("ok", ""))

    def test_khong_biet_tong_thi_khong_bao_vuot(self):
        parsed = youtube.parse_title("One Punch Man - Tập 500")
        self.assertEqual(audit.classify(500, parsed, None)[0], "ok")


class TestAuditRows(unittest.TestCase):
    def test_dung_tieu_de_co_san_khong_goi_mang(self):
        called = []
        rows = [dict(ROW, source_title="One Punch Man - Tập 1")]
        findings, counts = audit.audit_rows(
            rows, lambda r: called.append(1) or r.get("source_title"))
        self.assertEqual(called, [])
        self.assertEqual(counts["ok"], 1)
        self.assertEqual(findings, [])

    def test_gop_nhieu_loi_theo_slug(self):
        rows = [
            dict(ROW, id=1, episode_number=1,
                 source_title="[Bản Lồng Tiếng] One Punch Man - Tập 01-24"),
            dict(ROW, id=2, episode_number=5, source_title="One Punch Man - Tập 5"),
            dict(ROW, id=3, episode_number=277, source_title="Fairy Tail - Tập 277",
                 anime={"slug": "fairy-tail", "episodes_total": 175}),
        ]
        findings, counts = audit.audit_rows(rows, lambda r: r.get("source_title"))
        self.assertEqual(counts["gop_ca_bo"], 1)
        self.assertEqual(counts["ok"], 1)
        self.assertEqual(counts["vuot_tong"], 1)
        grouped = audit.group_by_slug(findings)
        self.assertIn("fairy-tail", grouped)
        self.assertIn("one-punch-man", grouped)

    def test_sap_xep_theo_muc_do_nang(self):
        rows = [
            dict(ROW, id=1, episode_number=277, source_title="Fairy Tail - Tập 277",
                 anime={"slug": "x", "episodes_total": 175}),
            dict(ROW, id=2, episode_number=1, source_title=None),   # xoa
            dict(ROW, id=3, episode_number=1,
                 source_title="[Bản Lồng Tiếng] X - Tập 01-12"),
        ]
        findings, _ = audit.audit_rows(rows, lambda r: r.get("source_title"))
        self.assertEqual(findings[0]["action"], "xoa")


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.patches, self.deletes, self.logs, self.queries = [], [], [], []
        self.dry = False

    def select(self, table, query):
        self.queries.append(query)
        return list(self.rows)

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return self.select(table, query)

    def patch(self, table, filters, values):
        self.patches.append((table, filters, values))
        return 1

    def delete(self, table, filters):
        self.deletes.append((table, filters))
        return 1

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


class TestRun(unittest.TestCase):
    def _run(self, rows, titles=None, fix=False, prune=False, slug=""):
        db = FakeDB(rows)
        titles = titles or {}
        fetch = lambda vid: titles.get(vid)      # noqa: E731
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = audit.run(db, slug=slug, fix=fix, prune_over_total=prune,
                            title_fetcher=fetch)
        return db, out, buf.getvalue()

    def test_chi_doc_thi_khong_ghi_gi(self):
        db, out, txt = self._run([dict(ROW)], {"AAAAAAAAAAA": "One Punch Man - Tập 1"})
        self.assertEqual(db.patches, [])
        self.assertEqual(db.deletes, [])
        self.assertIn("chỉ đọc", txt)

    def test_fix_luu_source_title_va_xoa_link_rac(self):
        rows = [
            dict(ROW, id=1, episode_number=1, url="https://youtu.be/AAAAAAAAAAA"),
            dict(ROW, id=2, episode_number=9, url="https://youtu.be/BBBBBBBBBBB"),
        ]
        titles = {"AAAAAAAAAAA": "One Punch Man - Tập 1",
                  "BBBBBBBBBBB": "Crayon Shin-chan Tập 1000-1099"}
        db, out, txt = self._run(rows, titles, fix=True)
        patched_ids = [f["id"] for _, f, _ in db.patches]
        self.assertIn(1, patched_ids, "link cũ phải được lưu source_title")
        self.assertIn(2, patched_ids, "link cũ phải được lưu source_title")
        self.assertEqual(db.deletes[0][1], {"id": 2}, "tiêu đề rác → xoá")
        self.assertEqual(out["deleted"], 1)
        self.assertFalse(db.logs[-1][3] < 0)

    def test_fix_sua_so_tap_cho_ban_gop(self):
        rows = [dict(ROW, id=1, episode_number=1,
                     url="https://youtu.be/AAAAAAAAAAA")]
        db, out, txt = self._run(
            rows, {"AAAAAAAAAAA": "[Bản Lồng Tiếng] One Punch Man - Tập 01-24"},
            fix=True)
        ep_patch = [v for _, _, v in db.patches if "episode_number" in v]
        self.assertEqual(ep_patch[0]["episode_number"], 0)
        self.assertEqual(out["fixed_ep"], 1)

    def test_vuot_tong_chi_xoa_khi_bat_prune(self):
        rows = [dict(ROW, id=1, episode_number=277,
                     url="https://youtu.be/AAAAAAAAAAA",
                     anime={"slug": "fairy-tail", "episodes_total": 175})]
        titles = {"AAAAAAAAAAA": "Fairy Tail - Tập 277"}
        db, out, _ = self._run(rows, titles, fix=True)
        self.assertEqual(db.deletes, [], "mặc định KHÔNG xoá (cần xem tay)")
        db2, out2, _ = self._run(rows, titles, fix=True, prune=True)
        self.assertEqual(db2.deletes[0][1], {"id": 1})
        self.assertEqual(out2["pruned"], 1)

    @staticmethod
    def _hunter_rows(n=8):
        """hunter-hunter: entry 1999 (62 tập) giữ video bản 2011 (tập > 62)."""
        return [dict(ROW, id=i, episode_number=62 + i,
                     url=f"https://youtu.be/AAAAAAAAAAA",
                     source_title=f"Hunter x Hunter - Tập {62 + i}",
                     anime={"slug": "hunter-hunter", "episodes_total": 62})
                for i in range(1, n + 1)]

    def test_chan_xoa_hang_loat_vi_nghi_sai_bo(self):
        """Ca thật 02/11/2026: 86 link "vượt tổng" của hunter-hunter đều là video
        THẬT của bản 2011 → `--prune-over-total` không được xoá."""
        db, out, txt = self._run(self._hunter_rows(), fix=True, prune=True)
        self.assertEqual(db.deletes, [], "quá 5 link/bộ → KHÔNG xoá")
        self.assertEqual(out["pruned"], 0)
        self.assertIn("GÁN SAI BỘ", txt)

    def test_van_xoa_khi_duoi_nguong(self):
        rows = [dict(ROW, id=1, episode_number=277,
                     url="https://youtu.be/AAAAAAAAAAA",
                     source_title="Fairy Tail - Tập 277",
                     anime={"slug": "fairy-tail", "episodes_total": 175})]
        db, out, _ = self._run(rows, fix=True, prune=True)
        self.assertEqual(len(db.deletes), 1)
        self.assertEqual(out["pruned"], 1)

    def test_force_prune_thi_xoa_du_bi_chan(self):
        db = FakeDB(self._hunter_rows())
        with redirect_stdout(io.StringIO()):
            audit.run(db, fix=True, prune_over_total=True, force_prune=True)
        self.assertEqual(len(db.deletes), 8)

    def test_loc_theo_slug_trong_query(self):
        db, _, _ = self._run([dict(ROW)], slug="one-punch-man")
        self.assertIn("anime.slug=eq.one-punch-man", db.queries[0])

    def test_khong_co_link_nao_thi_bao_ro(self):
        db, out, txt = self._run([])
        self.assertEqual(out, {"link": 0})
        self.assertIn("không đọc được link nào", txt)


class TestDeleteSafety(unittest.TestCase):
    def test_delete_bat_buoc_co_bo_loc(self):
        db = dbmod.DB(dry_run=True)
        with self.assertRaises(RuntimeError):
            db.delete("streaming_links", {})

    def test_delete_dry_run_khong_goi_mang(self):
        db = dbmod.DB(dry_run=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = db.delete("streaming_links", {"id": 5})
        self.assertEqual(n, 0)
        self.assertIn("[dry-run] delete", buf.getvalue())


class TestChiMuseVN(unittest.TestCase):
    """Chỉ giữ nội dung Muse VN: lọc region và xoá link kênh khác."""

    def test_kenh_map_dung_region(self):
        self.assertEqual(audit.CHANNEL_REGION["muse_vn"], "VN")
        self.assertEqual(audit.CHANNEL_REGION["ani_one_asia"], "AS")

    def test_loc_region_trong_query(self):
        db = FakeDB([dict(ROW)])
        with redirect_stdout(io.StringIO()):
            audit.run(db, channel="muse_vn", title_fetcher=lambda v: None)
        self.assertIn("region=eq.VN", db.queries[0])

    def test_fix_channel_muse_xoa_link_kenh_khac(self):
        db = FakeDB([dict(ROW, source_title="One Punch Man - Tập 1")])
        # lần select thứ 2 trả về link kênh khác
        calls = {"n": 0}

        def select(table, query):
            db.queries.append(query)
            calls["n"] += 1
            if "region=neq.VN" in query:
                return [{"id": 90}, {"id": 91}]
            return list(db.rows)

        db.select = select
        with redirect_stdout(io.StringIO()) as buf:
            audit.run(db, channel="muse_vn", fix=True, title_fetcher=lambda v: None)
        deleted = [f["id"] for _, f in db.deletes]
        self.assertEqual(deleted, [90, 91])
        self.assertIn("đã xoá 2 link kênh khác", buf.getvalue())

    def test_khong_bat_channel_thi_khong_xoa_gi(self):
        db = FakeDB([dict(ROW, source_title="One Punch Man - Tập 1")])
        with redirect_stdout(io.StringIO()):
            audit.run(db, fix=True, title_fetcher=lambda v: None)
        self.assertEqual(db.deletes, [])


if __name__ == "__main__":
    unittest.main()
