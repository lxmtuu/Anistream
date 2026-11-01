"""Test job D (`python3 -m ingest.main tmdb`) với DB giả + TMDB giả.

Khoá các hành vi quan trọng:
  · không match được → KHÔNG ghi gì (không đoán bừa)
  · nhiều mùa → không tạo episodes (tránh gán sai số tập)
  · chưa có episodes_total + đúng 1 mùa → tạo episodes
  · lỗi cấu hình TMDB (TmdbError) → NỔ, không bị nuốt
  · thiếu key → RuntimeError kèm hướng dẫn
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import tmdb


class FakeDB:
    def __init__(self, anime_rows, existing_episodes=None):
        self.anime_rows = anime_rows
        self.existing_episodes = existing_episodes or {}
        self.patched = []
        self.upserted = []
        self.logs = []
        self.dry = False

    def select(self, table, query):
        if table == "anime":
            return list(self.anime_rows)
        if table == "episodes":
            # query chứa anime_id=eq.<id>
            for aid, eps in self.existing_episodes.items():
                if f"anime_id=eq.{aid}" in query:
                    return eps
            return []
        return []

    def patch(self, table, filters, values):
        self.patched.append((table, filters, values))
        return 1

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {
    "id": 5, "slug": "kusuriya", "title_romaji": "Kusuriya no Hitorigoto",
    "title_english": "The Apothecary Diaries", "title_native": None,
    "title_vi": None, "synopsis_vi": None, "year": 2023,
    "episodes_total": None, "tmdb_id": None,
}

MATCH = ({"id": 12345, "name": "Kusuriya no Hitorigoto"}, 0.93, "search[Kusuriya]")


def _detail(seasons=(1,), total=24):
    return {
        "id": 12345, "name": "Kusuriya no Hitorigoto", "number_of_episodes": total,
        "seasons": [{"season_number": s} for s in (0,) + tuple(seasons)],
        "translations": {"translations": [
            {"iso_639_1": "vi", "data": {"name": "Dược Sư Tự Sự", "overview": "Maomao."}}]},
        "alternative_titles": {"results": []},
    }


class TestJobTmdb(unittest.TestCase):
    def _run(self, db, seasons=(1,), total=24, match=None):
        """Chạy job với TMDB giả. `match` cho phép mô phỏng không-khớp hoặc lỗi."""
        match_fn = match or (lambda row: MATCH)
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "match_anime", side_effect=match_fn), \
             patch.object(tmdb, "fetch_detail",
                          side_effect=lambda tv: _detail(seasons=seasons, total=total)), \
             patch.object(tmdb, "fetch_season", side_effect=lambda tv, n: {"episodes": [
                 {"episode_number": 1, "name": "Tập 1", "air_date": "2023-10-01"},
                 {"episode_number": 2, "name": "Tập 2", "air_date": "2023-10-08"},
             ]}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_tmdb(db)
            return n, buf.getvalue()

    def test_dien_ten_va_tom_tat_tieng_viet(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db)
        self.assertEqual(len(db.patched), 1)
        _, filters, values = db.patched[0]
        self.assertEqual(filters, {"id": 5})
        self.assertEqual(values["title_vi"], "Dược Sư Tự Sự")
        self.assertEqual(values["synopsis_vi"], "Maomao.")
        self.assertGreater(n, 0)
        self.assertIn("Dược Sư Tự Sự", out)

    def test_tao_episodes_khi_dung_mot_mua(self):
        db = FakeDB([dict(ROW)])
        self._run(db)
        eps_upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(eps_upserts), 1)
        rows = eps_upserts[0][1]
        self.assertEqual([r["number"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["anime_id"], 5)

    def test_nhieu_mua_thi_khong_tao_episodes(self):
        db = FakeDB([dict(ROW)])
        self._run(db, seasons=(1, 2), total=48)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])
        values = db.patched[0][2]
        self.assertNotIn("episodes_total", values)   # không lấy số tập của 2 mùa

    def test_da_co_episodes_thi_khong_tao_them(self):
        db = FakeDB([dict(ROW)], existing_episodes={5: [{"number": 1}]})
        self._run(db)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])

    def test_khong_match_thi_khong_ghi_gi(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db, match=lambda row: (None, 0.0, "search[x]"))
        self.assertEqual(db.patched, [])
        self.assertEqual(db.upserted, [])
        self.assertEqual(n, 0)
        self.assertIn("không tìm được trên TMDB", out)

    def test_khong_ghi_de_ten_da_bien_tap(self):
        row = dict(ROW, title_vi="Tên biên tập tay", synopsis_vi="Tóm tắt tay")
        db = FakeDB([row])
        self._run(db)
        values = db.patched[0][2] if db.patched else {}
        self.assertNotIn("title_vi", values)
        self.assertNotIn("synopsis_vi", values)

    def test_loi_cau_hinh_tmdb_thi_no(self):
        db = FakeDB([dict(ROW)])

        def boom(row):
            raise tmdb.TmdbError("TMDB_API_KEY không hợp lệ (401)")

        with self.assertRaises(tmdb.TmdbError):
            self._run(db, match=boom)
        self.assertEqual(db.patched, [])

    def test_loi_mot_bo_khong_lam_chet_job(self):
        db = FakeDB([dict(ROW), dict(ROW, id=6)])

        def flaky(row):
            if row["id"] == 5:
                raise ValueError("dữ liệu TMDB lạ")
            return MATCH

        n, out = self._run(db, match=flaky)
        self.assertEqual(len(db.patched), 1)          # bộ 6 vẫn được xử lý
        self.assertIn("dữ liệu TMDB lạ", out)

    def test_thieu_key_thi_runtime_error_kem_huong_dan(self):
        db = FakeDB([dict(ROW)])
        with patch.object(tmdb, "is_configured", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                with redirect_stdout(io.StringIO()):
                    ingest_main.job_tmdb(db)
        msg = str(ctx.exception)
        self.assertIn("TMDB_API_KEY", msg)
        self.assertIn("themoviedb.org", msg)

    def test_ghi_audit_ingest_runs(self):
        db = FakeDB([dict(ROW)])
        self._run(db)
        self.assertEqual(db.logs[-1][0], "tmdb")
        self.assertTrue(db.logs[-1][2])


if __name__ == "__main__":
    unittest.main()
