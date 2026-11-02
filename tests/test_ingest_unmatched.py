"""Chẩn đoán "tên chưa khớp" phải nằm trong DB, không chỉ trong log terminal.

Lỗi thật 02/11/2026: 163 bộ / 2028 tập metadata nhưng chỉ **30 bộ có video**;
`youtube --deep` ghi `rows=293` mà tổng link KHÔNG đổi (toàn upsert đè) ⇒ không
ai trả lời được "Muse VN không có bộ đó" hay "hỏng ghép tên", vì danh sách chỉ
được `print` ra terminal.
"""
import io
import unittest
from contextlib import redirect_stdout

from ingest import main as ingest_main


class FakeDB:
    def __init__(self, rows=()):
        self.upserted = []
        self.deleted = []
        self.rows = [dict(r) for r in rows]
        self.dry = False
        self.fail_upsert = False

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        if self.fail_upsert:
            raise RuntimeError("409 conflict")
        self.upserted.append((table, list(rows), on_conflict))
        return list(rows)

    def delete(self, table, filters):
        self.deleted.append((table, dict(filters)))
        return 0

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return list(self.rows)

    def log_ingest(self, *a, **k):
        return None


class TestLuuChuaKhop(unittest.TestCase):

    def test_ghi_ca_hai_kind_va_don_ten_cu(self):
        db = FakeDB()
        n = ingest_main._luu_chua_khop(
            db, "muse_vn", {"Bộ Lạ A": 12}, {"Bộ B": 3}, "2026-11-03T00:00:00Z")
        self.assertEqual(n, 2)
        table, rows, conflict = db.upserted[0]
        self.assertEqual(table, "ingest_unmatched")
        self.assertEqual(conflict, "source,channel,series_name,kind")
        kinds = {r["kind"]: r for r in rows}
        self.assertEqual(kinds["unmatched"]["series_name"], "Bộ Lạ A")
        self.assertEqual(kinds["unmatched"]["videos"], 12)
        self.assertEqual(kinds["review"]["videos"], 3)
        self.assertEqual(kinds["unmatched"]["last_seen_at"], "2026-11-03T00:00:00Z")
        # dọn tên đã khớp ở lần chạy này
        self.assertEqual(db.deleted[0][0], "ingest_unmatched")
        self.assertEqual(db.deleted[0][1]["channel"], "muse_vn")
        self.assertEqual(db.deleted[0][1]["last_seen_at"], "lt.2026-11-03T00:00:00Z")

    def test_loi_ghi_chan_doan_khong_lam_chet_job(self):
        """Link đã ghi xong trước đó — hỏng phần chẩn đoán KHÔNG được ném."""
        db = FakeDB()
        db.fail_upsert = True
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ingest_main._luu_chua_khop(db, "muse_vn", {"X": 1}, {}, "t")
        self.assertEqual(n, 0)
        self.assertIn("link vẫn đã ghi xong", buf.getvalue())

    def test_dry_run_khong_ghi(self):
        db = FakeDB()
        db.dry = True
        with redirect_stdout(io.StringIO()):
            n = ingest_main._luu_chua_khop(db, "muse_vn", {"X": 1}, {}, "t")
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])
        self.assertEqual(db.deleted, [])


class TestJobUnmatched(unittest.TestCase):

    def _run(self, rows, limit=40):
        db = FakeDB(rows)
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ingest_main.job_unmatched(db, limit=limit)
        return n, buf.getvalue()

    def test_in_danh_sach_theo_so_video(self):
        rows = [{"channel": "muse_vn", "series_name": "Bộ Lạ", "kind": "unmatched",
                 "videos": 25},
                {"channel": "muse_vn", "series_name": "Bộ Dư Tập", "kind": "review",
                 "videos": 4}]
        n, out = self._run(rows)
        self.assertEqual(n, 1)
        self.assertIn("Bộ Lạ", out)
        self.assertIn("(25 video", out)
        self.assertIn("VƯỢT tổng", out)
        self.assertIn("Bộ Dư Tập", out)

    def test_bang_trong_thi_bao_ro(self):
        n, out = self._run([])
        self.assertEqual(n, 0)
        self.assertIn("không có tên nào chưa khớp", out)

    def test_gioi_han_so_dong_in(self):
        rows = [{"channel": "muse_vn", "series_name": f"Bộ {i}", "kind": "unmatched",
                 "videos": 100 - i} for i in range(10)]
        n, out = self._run(rows, limit=3)
        self.assertEqual(n, 10)
        self.assertIn("còn 7 tên nữa", out)


if __name__ == "__main__":
    unittest.main()
