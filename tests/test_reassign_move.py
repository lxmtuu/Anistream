"""Test `ingest.reassign.move_all` — dời TOÀN BỘ link sang entry khác.

Ca thật 02/11/2026: Muse VN đăng "Hunter x Hunter" bản **2011** (148 tập,
AniList 11061) nhưng DB chỉ có bản 1999 (62 tập, AniList 136) — hai bản là quan
hệ *Alternative*, nên job catalog/schedule/seasons không bao giờ thêm bản 2011.
Toàn bộ 148 link nằm ở entry 1999; 86 link vượt tổng nên không ai xem được.

Muse đánh số theo đúng bộ 2011 ⇒ dời sang entry 2011 **không đổi số tập**.
"""
import unittest

from ingest import reassign


class FakeDB:
    def __init__(self, anime, links):
        self.anime = anime          # [{id, slug, episodes_total}]
        self.links = links          # [{id, anime_id, episode_number}]
        self.patched = []
        self.upserted = []
        self.deleted = []
        self.logs = []

    def select(self, table, query):
        if table == "streaming_links":       # kiểm "đích đã có link chưa"
            aid = int(query.split("anime_id=eq.", 1)[1].split("&", 1)[0])
            return [l for l in self.links if l["anime_id"] == aid][:1]
        assert table == "anime"
        slug = query.split("slug=eq.", 1)[1].split("&", 1)[0]
        return [a for a in self.anime if a["slug"] == slug]

    def select_all(self, table, query):
        assert table == "streaming_links"
        aid = int(query.split("anime_id=eq.", 1)[1].split("&", 1)[0])
        return [l for l in self.links if l["anime_id"] == aid]

    def patch(self, table, filters, values):
        self.patched.append((table, filters, values))
        for l in self.links:
            if l["id"] == filters["id"]:
                l.update(values)
        return 1

    def upsert(self, table, rows, on_conflict=None):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def delete(self, table, filters):
        self.deleted.append((table, filters))
        return 62

    def log_ingest(self, *a, **k):
        self.logs.append(a)


OLD = {"id": 315, "slug": "hunter-hunter", "episodes_total": 62}
NEW = {"id": 999, "slug": "hunter-x-hunter-2011", "episodes_total": 148}


class TestMoveAll(unittest.TestCase):
    def _db(self, n=148, dst_total=148, dst_busy=False):
        links = [{"id": i, "anime_id": 315, "episode_number": i}
                 for i in range(1, n + 1)]
        if dst_busy:
            links.append({"id": 9999, "anime_id": 999, "episode_number": 1})
        anime = [dict(OLD), dict(NEW, episodes_total=dst_total)]
        return FakeDB(anime, links)

    def test_dry_run_khong_ghi_gi(self):
        db = self._db()
        n = reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011", dry=True)
        self.assertEqual(n, 0)
        self.assertEqual(db.patched, [])
        self.assertEqual(db.upserted, [])

    def test_doi_het_link_giu_nguyen_so(self):
        db = self._db()
        n = reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011", dry=False)
        self.assertEqual(n, 148)
        self.assertTrue(all(p[2]["anime_id"] == 999 for p in db.patched))
        self.assertTrue(all("episode_number" not in p[2] for p in db.patched),
                        "không được đánh số lại — Muse đánh số theo bộ 2011")
        eps = db.upserted[0][1]
        self.assertEqual([e["number"] for e in eps], list(range(1, 149)))

    def test_xoa_tap_trong_cua_nguon(self):
        db = self._db()
        reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011", dry=False)
        self.assertEqual(len(db.deleted), 1)
        table, filters = db.deleted[0]
        self.assertEqual(table, "episodes")
        self.assertEqual(filters["anime_id"], 315)
        self.assertEqual(filters["airing_at"], "is.null")
        self.assertEqual(filters["title"], "is.null")

    def test_dich_khong_du_tap_thi_tu_choi(self):
        db = self._db(dst_total=100)
        with self.assertRaises(RuntimeError) as e:
            reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011", dry=False)
        self.assertIn("không nhận nổi", str(e.exception))
        self.assertEqual(db.patched, [])

    def test_dich_da_co_link_thi_tu_choi(self):
        db = self._db(dst_busy=True)
        with self.assertRaises(RuntimeError) as e:
            reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011", dry=False)
        self.assertIn("đã có link", str(e.exception))

    def test_slug_sai_thi_no(self):
        db = self._db()
        with self.assertRaises(RuntimeError):
            reassign.move_all(db, "khong-co", "hunter-x-hunter-2011")

    def test_nguon_khong_co_link_thi_no(self):
        db = FakeDB([dict(OLD), dict(NEW)], [])
        with self.assertRaises(RuntimeError):
            reassign.move_all(db, "hunter-hunter", "hunter-x-hunter-2011")


if __name__ == "__main__":
    unittest.main()
