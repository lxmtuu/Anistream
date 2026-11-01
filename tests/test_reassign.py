"""Test `ingest/reassign.py` — chuyển link bị gán sai mùa.

Ca thật (02/11/2026): FAIRY TAIL — Muse đăng liên tục tập 1–277, AniList tách
"FAIRY TAIL" (175 tập) và "FAIRY TAIL (2014)" (102 tập). 102 link tập 176–277 bị
chặn ở entry mùa 1 → 102 video không ai xem được.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import reassign


def anime(aid, slug, total):
    return {"id": aid, "slug": slug, "title_romaji": slug.title(),
            "episodes_total": total}


class FakeDB:
    def __init__(self, animes, links, episodes=None):
        self.animes = animes
        self.links = links
        self.episodes = episodes or {}
        self.patches = []
        self.logs = []
        self.dry = False

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        if table == "anime":
            return [dict(a) for a in self.animes]
        if table == "streaming_links":
            return [dict(l) for l in self.links]
        return []

    def select(self, table, query):
        if table == "episodes":
            aid = int(query.split("anime_id=eq.")[1].split("&")[0])
            return [{"number": n} for n in self.episodes.get(aid, [])]
        return []

    def patch(self, table, filters, values):
        self.patches.append((table, filters, values))
        return 1

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


class TestPlan(unittest.TestCase):
    def test_fairy_tail_chuyen_dung_102_link(self):
        animes = [anime(1, "fairy-tail", 175), anime(2, "fairy-tail-2014", 102)]
        links = [{"id": 100 + i, "anime_id": 1, "episode_number": 176 + i}
                 for i in range(102)]
        p = reassign.plan(FakeDB(animes, links))
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["to_id"], 2)
        self.assertEqual(p[0]["offset"], 175)
        self.assertEqual(p[0]["mapped"][0], 1)
        self.assertEqual(p[0]["mapped"][-1], 102)
        self.assertEqual(p[0]["confidence"], "exact")

    def test_khong_co_entry_mua_sau_thi_khong_de_xuat(self):
        """HUNTER×HUNTER: link 63–148 nhưng DB chỉ có entry 62 tập, không có mùa sau."""
        db = FakeDB([anime(1, "hunter-hunter", 62)],
                    [{"id": 1, "anime_id": 1, "episode_number": 100}])
        p = reassign.plan(db)
        self.assertEqual(p[0]["to_id"], None)
        self.assertIn("không có entry", p[0]["reason"])

    def test_dich_da_co_tap_thi_khong_dung_toi(self):
        animes = [anime(1, "fairy-tail", 175), anime(2, "fairy-tail-2014", 102)]
        links = [{"id": i, "anime_id": 1, "episode_number": 176 + i} for i in range(3)]
        links += [{"id": 50, "anime_id": 2, "episode_number": 1}]
        p = reassign.plan(FakeDB(animes, links))
        self.assertIsNone(p[0]["to_id"], "đích đã có link → không được chuyển vào")

    def test_anh_xa_vuot_tong_cua_dich_thi_bo(self):
        """Link 176–200 cần 25 tập nhưng đích chỉ có 12 → nghi không phải mùa đó."""
        animes = [anime(1, "x", 175), anime(2, "x-2nd-season", 12)]
        links = [{"id": i, "anime_id": 1, "episode_number": 176 + i} for i in range(25)]
        p = reassign.plan(FakeDB(animes, links))
        self.assertIsNone(p[0]["to_id"])

    def test_link_trong_tong_thi_khong_dong_toi(self):
        animes = [anime(1, "a", 12), anime(2, "a-2", 12)]
        links = [{"id": 1, "anime_id": 1, "episode_number": 5}]
        self.assertEqual(reassign.plan(FakeDB(animes, links)), [])

    def test_danh_so_khong_lien_tuc_thi_chi_la_probable(self):
        """SHANGRI-LA: chỉ có tập 26 và 41 → ánh xạ 1 và 16, không khớp tuyệt đối."""
        animes = [anime(1, "shangri-la-frontier", 25),
                  anime(2, "shangri-la-frontier-2nd-season", 25)]
        links = [{"id": 1, "anime_id": 1, "episode_number": 26},
                 {"id": 2, "anime_id": 1, "episode_number": 41}]
        p = reassign.plan(FakeDB(animes, links))
        self.assertEqual(p[0]["confidence"], "probable")
        self.assertEqual(p[0]["mapped"], [1, 16])


class TestApply(unittest.TestCase):
    def _plan(self):
        animes = [anime(1, "fairy-tail", 175), anime(2, "fairy-tail-2014", 102)]
        links = [{"id": 100 + i, "anime_id": 1, "episode_number": 176 + i}
                 for i in range(3)]
        return reassign.plan(FakeDB(animes, links))

    def test_apply_patch_dung_anime_va_so_tap(self):
        db = FakeDB([], [])
        plans = self._plan()
        with patch("ingest.main.job_link_episodes", return_value=3):
            n = reassign.apply(db, plans)
        self.assertEqual(n, 3)
        self.assertEqual(db.patches[0],
                         ("streaming_links", {"id": 100},
                          {"anime_id": 2, "episode_number": 1}))
        self.assertEqual(db.patches[-1][2], {"anime_id": 2, "episode_number": 3})

    def test_only_exact_bo_qua_probable(self):
        db = FakeDB([], [])
        plans = [dict(p, confidence="probable") for p in self._plan()]
        with patch("ingest.main.job_link_episodes", return_value=0):
            n = reassign.apply(db, plans, only_exact=True)
        self.assertEqual(n, 0)
        self.assertEqual(db.patches, [])

    def test_khong_co_gi_thi_khong_goi_db(self):
        db = FakeDB([], [])
        with patch("ingest.main.job_link_episodes", return_value=0) as jle:
            n = reassign.apply(db, [])
        self.assertEqual(n, 0)
        jle.assert_not_called()

    def test_main_mac_dinh_chi_in(self):
        with patch("ingest.reassign.dbmod.DB") as mk:
            mk.return_value = FakeDB([anime(1, "a", 12)], [])
            with redirect_stdout(io.StringIO()) as buf:
                reassign.main([])
        self.assertIn("chưa ghi gì", buf.getvalue())
