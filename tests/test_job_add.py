"""Test `ingest.main.job_add` — thêm đúng MỘT bộ AniList theo id (Job G).

Vì sao cần: catalog chạy theo mùa, schedule theo lịch phát, `seasons` chỉ đi theo
SEQUEL/PREQUEL. Bộ chỉ có quan hệ **Alternative** không bao giờ tự vào DB — ca
thật 02/11/2026: HUNTER×HUNTER (2011, 148 tập, AniList 11061) vs bản 1999
(62 tập), trong khi Muse VN có đủ 148 tập của bản 2011.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import anilist
from ingest import main as ingest_main


class FakeDB:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.upserted = []
        self.logs = []

    def select(self, table, query):
        if table == "anime" and "anilist_id=eq." in query:
            return list(self.existing)
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        # ghi thật vào "bảng" để bước đọc-lại kiểm được
        self.existing = [{"slug": r.get("slug"),
                          "episodes_total": r.get("episodes_total")}
                         for r in rows]
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows))


MEDIA = {
    "id": 11061,
    "idMal": 11061,
    "title": {"romaji": "HUNTER×HUNTER (2011)",
              "english": "Hunter x Hunter (2011)", "native": "ハンター×ハンター"},
    "description": "Gon…", "coverImage": {"large": "x"}, "bannerImage": None,
    "siteUrl": "https://anilist.co/anime/11061", "averageScore": 90,
    "popularity": 500000, "episodes": 148, "duration": 23,
    "status": "FINISHED", "season": "FALL", "seasonYear": 2011, "format": "TV",
    "genres": ["Action"], "studios": {"nodes": [{"name": "Madhouse"}]},
    "nextAiringEpisode": None, "trailer": None, "externalLinks": [],
}


class TestJobAdd(unittest.TestCase):
    def _run(self, db, media=None):
        with patch.object(anilist, "media", return_value=media or MEDIA):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_add(db, 11061)
            return n, buf.getvalue()

    def test_them_bo_moi(self):
        db = FakeDB()
        with patch.object(anilist, "to_anime_row",
                          return_value={"slug": "hunter-x-hunter-2011",
                                        "anilist_id": 11061,
                                        "episodes_total": 148}):
            n, out = self._run(db)
        self.assertEqual(n, 1)
        self.assertIn("148", out)
        self.assertEqual(db.upserted[0][0], "anime")

    def test_bo_da_co_thi_khong_them_trung(self):
        db = FakeDB(existing=[{"id": 315, "slug": "hunter-hunter",
                               "episodes_total": 62}])
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])
        self.assertIn("đã có", out)

    def test_ghi_xong_ma_khong_doc_lai_duoc_thi_no(self):
        """Không được im lặng báo thành công khi upsert không vào DB."""
        db = FakeDB()
        with patch.object(anilist, "to_anime_row",
                          return_value={"slug": "x", "anilist_id": 11061}), \
                patch.object(FakeDB, "upsert",
                             side_effect=lambda *a, **k: db.upserted.append(
                                 (a[0], list(a[1]))) or []):
            with self.assertRaises(RuntimeError):
                self._run(db)

    def test_anilist_tra_rong_thi_no(self):
        with patch.object(anilist, "media", side_effect=RuntimeError("không có media")):
            with self.assertRaises(RuntimeError):
                ingest_main.job_add(FakeDB(), 1)


if __name__ == "__main__":
    unittest.main()
