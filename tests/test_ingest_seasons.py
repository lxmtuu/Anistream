"""Test job E — phát hiện MÙA MỚI qua quan hệ SEQUEL của AniList.

Vì sao cần: AniList tách mỗi mùa thành 1 entry riêng và entry mùa 1 KHÔNG có tập
của mùa 2. Không đi theo quan hệ `SEQUEL` thì app chỉ có những mùa "tình cờ" nằm
trong catalog/lịch phát.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

try:                                     # discover -s tests ⇒ tests/ nằm trên path
    from tests._offline import KhongMang
except ImportError:                      # chạy `python3 -m unittest tests.x`
    from _offline import KhongMang
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

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return self.select(table, query)

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


class TestJobSeasons(KhongMang, unittest.TestCase):
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


class TestLooksLaterSeason(unittest.TestCase):
    def test_nhan_dien_mua_sau(self):
        for t in ("Ao no Hako Season 2", "Kusuriya no Hitorigoto 3rd Season",
                  "Black Clover 2nd Season", "One Punch Man Part 2",
                  "Some Anime - Mùa 2"):
            self.assertTrue(ingest_main.looks_later_season({"title_romaji": t}), t)

    def test_bo_mua_dau_khong_bi_coi_la_mua_sau(self):
        for t in ("Fairy Tail", "Hunter x Hunter", "Dandadan", "Ao no Hako"):
            self.assertFalse(ingest_main.looks_later_season({"title_romaji": t}), t)


class TestJobSeasonsPrequel(unittest.TestCase):
    """Muse đăng mùa mới trước → DB có mùa 2 mà thiếu mùa 1."""

    def _run(self, db, sequels_map, prequels_map, rows=None):
        def pick(mp):
            def f(aid):
                v = mp.get(aid, [])
                if isinstance(v, Exception):
                    raise v
                return v
            return f

        with patch.object(anilist, "sequels", side_effect=pick(sequels_map)), \
                patch.object(anilist, "prequels", side_effect=pick(prequels_map)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_seasons(db, limit=10)
        return n, buf.getvalue()

    def test_them_mua_truoc_cho_bo_la_mua_2(self):
        row = dict(ROW, id=2, slug="ao-no-hako-season-2",
                   title_romaji="Ao no Hako Season 2", anilist_id=999)
        db = FakeDB([row])
        n, out = self._run(db, {}, {999: [m(100, "Ao no Hako", episodes=25)]})
        self.assertEqual(n, 1)
        anime_rows = [r for u in db.upserted if u[0] == "anime" for r in u[1]]
        self.assertEqual(anime_rows[0]["title_romaji"], "Ao no Hako")
        self.assertIn("mùa TRƯỚC", out)

    def test_khong_hoi_prequel_cho_mua_dau(self):
        db = FakeDB([dict(ROW)])
        called = []

        with patch.object(anilist, "sequels", return_value=[]), \
                patch.object(anilist, "prequels",
                             side_effect=lambda aid: called.append(aid) or []):
            with redirect_stdout(io.StringIO()):
                ingest_main.job_seasons(db, limit=10)
        self.assertEqual(called, [])

    def test_prequel_da_co_trong_db_thi_khong_them(self):
        row = dict(ROW, id=2, slug="x-season-2", title_romaji="X Season 2",
                   anilist_id=999)
        other = dict(ROW, id=3, slug="x", title_romaji="X", anilist_id=100)
        db = FakeDB([row, other])
        n, _ = self._run(db, {}, {999: [m(100, "X")]})
        self.assertEqual(n, 0)


class TestRelated(unittest.TestCase):
    def test_related_loc_dung_loai(self):
        # gql() đã mở gói payload["data"] → patch trả thẳng "Media".
        payload = {"Media": {"relations": {"edges": [
            {"relationType": "PREQUEL", "node": {"id": 1}},
            {"relationType": "SEQUEL", "node": {"id": 2}},
            {"relationType": "SIDE_STORY", "node": {"id": 3}},
        ]}}}
        with patch.object(anilist, "gql", return_value=payload, create=True):
            self.assertEqual([n["id"] for n in anilist.related(9, ("PREQUEL",))], [1])
            self.assertEqual([n["id"] for n in anilist.related(9, ("PREQUEL", "SEQUEL"))],
                             [1, 2])

    def test_sequels_va_prequels_dung_related(self):
        with patch.object(anilist, "related", return_value=[{"id": 7}]) as r:
            self.assertEqual(anilist.sequels(5), [{"id": 7}])
            anilist.prequels(5)
        self.assertEqual([c.args for c in r.call_args_list],
                         [(5, ("SEQUEL",)), (5, ("PREQUEL",))])


class TestGhiTheoLo(unittest.TestCase):
    """Lỗi thật 02/11/2026: phát hiện ~50 mùa rồi bước ghi cuối cùng lỗi
    PGRST102 ("All object keys must match") → mất TRẮNG toàn bộ."""

    def _run(self, db, n_new):
        medias = [m(1000 + i, f"Bo {i} Season 2") for i in range(n_new)]
        with patch.object(anilist, "sequels", return_value=medias), \
                patch.object(anilist, "prequels", return_value=[]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                got = ingest_main.job_seasons(db, limit=1)
        return got, buf.getvalue()

    def test_chia_nhieu_lan_ghi_khi_nhieu_mua(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db, 60)
        self.assertEqual(n, 60)
        anime_upserts = [u for u in db.upserted if u[0] == "anime"]
        self.assertEqual(len(anime_upserts), 3, "60 mùa → 3 lô 25/25/10")
        self.assertEqual([len(u[1]) for u in anime_upserts], [25, 25, 10])
        self.assertIn("đã ghi 25/60", out)

    def test_it_mua_thi_chi_1_lan_ghi(self):
        db = FakeDB([dict(ROW)])
        n, _ = self._run(db, 7)
        self.assertEqual(n, 7)
        self.assertEqual(len([u for u in db.upserted if u[0] == "anime"]), 1)

    def test_loi_giua_duong_van_giu_phan_da_ghi(self):
        db = FakeDB([dict(ROW)])
        calls = {"n": 0}

        def flaky(table, rows, on_conflict=None, fallback_per_row=False):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("PGRST102 giả lập")
            return db.upsert(table, rows, on_conflict, fallback_per_row)

        db.upsert = flaky
        with self.assertRaises(RuntimeError):
            self._run(db, 60)
        self.assertEqual(calls["n"], 2, "lô 1 phải ghi xong trước khi lô 2 lỗi")
