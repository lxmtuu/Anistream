"""Test Job C' — tạo `episodes` từ link official đã có.

Vì sao cần: đo 2026-11-01 thấy 23/27 bộ có link free_legal nhưng bảng `episodes`
TRỐNG (dandadan 12 link/0 tập, noblesse 13/0). Người dùng mở trang chi tiết thấy
"0 tập" dù có video, và job tập chỉ chạy được khi có TMDB_API_KEY + khớp TMDB.
"""
import io
import unittest
from contextlib import redirect_stdout

from ingest import main as ingest_main


class FakeDB:
    """Chỉ đủ dùng cho job_link_episodes; trả dữ liệu theo tên bảng."""

    def __init__(self, links, anime, episodes=None, dry=False):
        self.links = links
        self.anime = anime
        self.episodes = episodes or []
        self.dry = dry
        self.upserted = []
        self.logs = []
        self.queries = []

    def select(self, table, query):
        self.queries.append((table, query))
        if table == "streaming_links":
            return list(self.links)
        if table == "anime":
            return [dict(a) for a in self.anime]      # cả 2 lần gọi dùng id/total/slug
        if table == "episodes":
            return [{"anime_id": a} for a in self.episodes]
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows), on_conflict))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


def run(db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        n = ingest_main.job_link_episodes(db)
    return n, buf.getvalue()


class TestTaoTapTuLink(unittest.TestCase):
    def test_bo_co_link_0_tap_duoc_tao_du(self):
        db = FakeDB(
            links=[{"anime_id": 1, "episode_number": n} for n in range(1, 13)],
            anime=[{"id": 1, "slug": "dandadan", "episodes_total": 12}],
        )
        n, _ = run(db)
        self.assertEqual(n, 12)
        rows = [r for t, rows, _ in db.upserted if t == "episodes" for r in rows]
        self.assertEqual(sorted(r["number"] for r in rows), list(range(1, 13)))
        self.assertTrue(all(r["anime_id"] == 1 for r in rows))

    def test_bo_da_co_tap_thi_khong_dung_toi(self):
        db = FakeDB(
            links=[{"anime_id": 2, "episode_number": 1}],
            anime=[{"id": 2, "slug": "co-tap", "episodes_total": 12}],
            episodes=[2],
        )
        n, _ = run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])

    def test_khong_tao_tap_vuot_tong_so_tap(self):
        """Chốt chặn: Fairy Tail 175 tập nhưng Muse đăng tới 277."""
        db = FakeDB(
            links=[{"anime_id": 3, "episode_number": n} for n in (110, 175, 200, 277)],
            anime=[{"id": 3, "slug": "fairy-tail", "episodes_total": 175}],
        )
        n, out = run(db)
        self.assertEqual(n, 2)
        rows = [r for t, rows, _ in db.upserted if t == "episodes" for r in rows]
        self.assertEqual(sorted(r["number"] for r in rows), [110, 175])
        self.assertIn("VƯỢT", out)
        self.assertIn("fairy-tail", out)

    def test_tong_khong_biet_thi_khong_chan(self):
        db = FakeDB(
            links=[{"anime_id": 4, "episode_number": n} for n in (1, 2, 3)],
            anime=[{"id": 4, "slug": "chua-biet-tong", "episodes_total": None}],
        )
        self.assertEqual(run(db)[0], 3)

    def test_bo_chi_co_link_tap_0_khong_tao_tap(self):
        """Link "bản gộp" (episode_number=0) không phải là 1 tập cụ thể."""
        db = FakeDB(
            links=[{"anime_id": 5, "episode_number": 0}],
            anime=[{"id": 5, "slug": "gop", "episodes_total": 12}],
        )
        self.assertEqual(run(db)[0], 0)

    def test_dry_run_khong_ghi(self):
        db = FakeDB(
            links=[{"anime_id": 6, "episode_number": 1}],
            anime=[{"id": 6, "slug": "x", "episodes_total": 12}],
            dry=True,
        )
        self.assertEqual(run(db)[0], 0)
        self.assertEqual(db.upserted, [])

    def test_ghi_dung_conflict_key_va_log(self):
        db = FakeDB(
            links=[{"anime_id": 7, "episode_number": 1}],
            anime=[{"id": 7, "slug": "y", "episodes_total": 12}],
        )
        run(db)
        _, _, conflict = db.upserted[0]
        self.assertEqual(conflict, "anime_id,number")
        self.assertEqual(db.logs[-1][:4], ("links", "episodes", True, 1))
