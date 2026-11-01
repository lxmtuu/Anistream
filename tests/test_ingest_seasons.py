"""Test job E — phát hiện MÙA MỚI qua quan hệ SEQUEL của AniList.

Vì sao cần: AniList tách mỗi mùa thành 1 entry riêng và entry mùa 1 KHÔNG có tập
của mùa 2. Không đi theo quan hệ `SEQUEL` thì app chỉ có những mùa "tình cờ" nằm
trong catalog/lịch phát.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import anilist
from ingest import main as ingest_main


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
        self.upserted = []
        self.logs = []
        self.dry = False

    def select(self, table, query):
        self.queries.append((table, query))
        return list(self.rows)

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        out = []
        for r in rows:
            out.append(dict(r, id=len(out) + 1))
        return out

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {"id": 1, "slug": "one-punch-man", "title_romaji": "One Punch Man",
       "anilist_id": 21087, "status": "RELEASING"}


def m(aid, romaji, episodes=12, fmt="TV", year=2019):
    return {"id": aid, "title": {"romaji": romaji, "english": romaji, "native": None},
            "episodes": episodes, "format": fmt, "seasonYear": year,
            "coverImage": {"large": "x"}, "genres": ["Action"]}


class TestIsSeriesLike(unittest.TestCase):
    def test_tv_ona_la_mua_moi(self):
        for fmt in ("TV", "TV_SHORT", "ONA"):
            self.assertTrue(anilist.is_series_like({"format": fmt}), fmt)

    def test_movie_special_khong_phai_mua_moi(self):
        for fmt in ("MOVIE", "SPECIAL", "OVA", None):
            self.assertFalse(anilist.is_series_like({"format": fmt}), fmt)


class TestJobSeasons(unittest.TestCase):
    def _run(self, db, sequels_map, rows=None):
        def fake_sequels(aid):
            v = sequels_map.get(aid, [])
            if isinstance(v, Exception):
                raise v
            return v

        # KHÔNG patch _upsert_media: job_seasons gọi thẳng nó để ghi bảng anime,
        # test cần kiểm đúng dữ liệu được upsert.
        with patch.object(anilist, "sequels", side_effect=fake_sequels):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_seasons(db, limit=10)
        return n, buf.getvalue()

    def test_them_mua_moi(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db, {21087: [m(21088, "One Punch Man 2nd Season")]})
        self.assertEqual(n, 1)
        anime_upserts = [u for u in db.upserted if u[0] == "anime"]
        self.assertEqual(len(anime_upserts), 1)
        self.assertEqual(anime_upserts[0][1][0]["anilist_id"], 21088)
        self.assertIn("mùa mới: One Punch Man 2nd Season", out)

    def test_khong_them_mua_da_co_trong_db(self):
        db = FakeDB([dict(ROW), dict(ROW, id=2, slug="opm2",
                                     title_romaji="One Punch Man 2nd Season",
                                     anilist_id=21088)])
        n, _ = self._run(db, {21087: [m(21088, "One Punch Man 2nd Season")]})
        self.assertEqual(n, 0, "mùa đã có (theo anilist_id) thì không thêm lại")

    def test_bo_movie_special(self):
        db = FakeDB([dict(ROW)])
        n, _ = self._run(db, {21087: [m(21089, "OPM Movie", fmt="MOVIE"),
                                      m(21090, "OPM Special", fmt="SPECIAL")]})
        self.assertEqual(n, 0)

    def test_mot_bo_nhieu_sequel_khong_trung(self):
        db = FakeDB([dict(ROW)])
        n, _ = self._run(db, {21087: [m(21088, "OPM S2"), m(21088, "OPM S2")]})
        self.assertEqual(n, 1, "cùng anilist_id chỉ thêm 1 lần")

    def test_loi_mot_bo_khong_lam_chet_job(self):
        db = FakeDB([dict(ROW), dict(ROW, id=2, anilist_id=999, slug="x")])
        n, out = self._run(db, {21087: RuntimeError("429"),
                                999: [m(1000, "Mùa mới của X")]})
        self.assertEqual(n, 1, "bộ còn lại vẫn được xử lý")
        self.assertTrue(db.logs[-1][2], "vẫn ok vì có thêm được mùa mới")

    def test_khong_co_anime_nao_thi_thoi(self):
        db = FakeDB([])
        n, out = self._run(db, {})
        self.assertEqual(n, 0)
        self.assertIn("0 anime", out)

    def test_query_chi_lay_bo_co_anilist_id(self):
        db = FakeDB([dict(ROW)])
        self._run(db, {})
        q = db.queries[0][1]
        self.assertIn("anilist_id=not.is.null", q)


if __name__ == "__main__":
    unittest.main()
