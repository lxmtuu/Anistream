"""Test Job J (`coverage`) — bộ nào THẬT SỰ xem được.

Vì sao: `check` chỉ bắt mâu thuẫn dữ liệu. Câu người dùng hỏi là "bộ này có xem
được không?" — đo 02/11/2026 có **94 bộ** liệt kê tập mà **0 video**.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main


class FakeDB:
    def __init__(self, anime, eps=(), links=()):
        self.anime = [dict(a) for a in anime]
        self.eps = [{"anime_id": a, "number": n} for a, n in eps]
        self.links = [{"anime_id": a, "episode_number": n} for a, n in links]
        self.dry = False

    def select_all(self, table, query):
        return {"anime": self.anime, "episodes": self.eps,
                "streaming_links": self.links}.get(table, [])


def A(id_, slug, pop=1, total=12, status="FINISHED"):
    return {"id": id_, "slug": slug, "status": status,
            "episodes_total": total, "popularity": pop}


class TestJobCoverage(unittest.TestCase):

    def _run(self, db):
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ingest_main.job_coverage(db)
        return n, buf.getvalue()

    def test_dem_bo_chi_co_metadata(self):
        db = FakeDB([A(1, "co-video"), A(2, "chi-metadata", pop=900)],
                    eps=[(1, 1), (1, 2), (2, 1), (2, 2)],
                    links=[(1, 1), (1, 2)])
        n, out = self._run(db)
        self.assertEqual(n, 1)
        self.assertIn("chi-metadata", out)
        self.assertIn("1 bộ CÓ video", out)
        self.assertIn("tập có video: 2/4 (50.0%)", out)

    def test_bo_trong_hoan_toan_khong_tinh_la_chi_metadata(self):
        db = FakeDB([A(1, "trong")])
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertIn("1 bộ trống hoàn toàn", out)

    def test_link_episode_0_khong_tinh_la_co_video(self):
        """`episode_number = 0` là "bản gộp cả bộ" — vẫn là video, nhưng KHÔNG
        được cộng vào số tập có video (nó không phải 1 tập cụ thể)."""
        db = FakeDB([A(1, "ban-gop")], eps=[(1, 1)], links=[(1, 0)])
        n, out = self._run(db)
        self.assertEqual(n, 1, "không có tập nào có video ⇒ vẫn là chỉ metadata")
        self.assertIn("0/1 (0.0%)", out)

    def test_dry_run_bo_qua(self):
        db = FakeDB([A(1, "x")])
        db.dry = True
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertIn("dry-run", out)

    def test_cli_goi_job(self):
        db = FakeDB([A(1, "x")])
        with patch.object(ingest_main.dbmod, "DB", return_value=db), \
             redirect_stdout(io.StringIO()):
            ingest_main.main(["coverage"])
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
