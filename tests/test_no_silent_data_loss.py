"""Test 3 bản vá chống mất dữ liệu âm thầm.

1. `DB.select_all` — PostgREST (Supabase) cắt response ở "Max Rows" = 1000.
   Xin `limit=20000` vẫn chỉ nhận 1000 dòng → phải tự phân trang, nếu không job C'
   tưởng bộ nằm sau dòng 1000 "chưa có tập" và job E báo nhầm "mùa mới".
2. `anilist.to_anime_row` — không được gửi khoá None: upsert merge-duplicates sẽ
   ghi NULL đè `episodes_total`/`cover_url` mà TMDB vừa điền (ca thật: 8 bộ).
3. `job_jikan --fill-gaps` — bộ thiếu VÀI tập (33 bộ) trước đây bị bỏ qua vĩnh viễn.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import anilist, db as dbmod
from ingest import main as ingest_main


class TestSelectAll(unittest.TestCase):
    def _db(self, total_rows):
        """DB thật nhưng `select` trả từ bộ nhớ, tôn trọng limit/offset như PostgREST."""
        db = object.__new__(dbmod.DB)
        db.dry = False
        db.rows = [{"id": i} for i in range(total_rows)]
        db.calls = []

        def fake_select(table, query):
            db.calls.append(query)
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            limit = int(params.get("limit", 1000))
            offset = int(params.get("offset", 0))
            # PostgREST thật: không bao giờ trả quá Max Rows (1000)
            limit = min(limit, 1000)
            return db.rows[offset:offset + limit]

        db.select = fake_select
        return db

    def test_doc_het_2500_dong(self):
        db = self._db(2500)
        got = db.select_all("episodes", "select=anime_id")
        self.assertEqual(len(got), 2500)
        self.assertEqual([c for c in db.calls if "offset=0" in c] and len(db.calls), 3)

    def test_bo_limit_cu_trong_query(self):
        """Query cũ có `&limit=20000` — không được để 2 tham số limit chồng nhau."""
        db = self._db(10)
        db.select_all("streaming_links", "select=id&limit=20000")
        self.assertEqual(sum(c.count("limit=") for c in db.calls), len(db.calls))
        self.assertNotIn("20000", " ".join(db.calls))

    def test_it_hon_1_trang_thi_dung(self):
        db = self._db(37)
        self.assertEqual(len(db.select_all("anime", "select=id")), 37)
        self.assertEqual(len(db.calls), 1)

    def test_dry_run_khong_goi_api(self):
        db = object.__new__(dbmod.DB)
        db.dry = True
        self.assertEqual(db.select_all("anime", "select=id"), [])


class TestKhongGhiDeNull(unittest.TestCase):
    MEDIA = {
        "id": 5, "idMal": 9,
        "title": {"romaji": "X", "english": None, "native": None},
        "episodes": None, "coverImage": {"large": None, "extraLarge": None},
        "bannerImage": None, "averageScore": None, "popularity": 10,
        "genres": [], "description": None, "seasonYear": None, "season": None,
        "status": "RELEASING", "format": "TV", "duration": None,
        "studios": {"nodes": []},
    }

    def test_khong_gui_khoa_rong(self):
        row = anilist.to_anime_row(self.MEDIA)
        # Đây là các cột mà job D (TMDB) điền — gửi None sẽ xoá trắng.
        for k in ("episodes_total", "cover_url", "banner_url", "score",
                  "year", "season", "duration_min", "synopsis_original"):
            self.assertNotIn(k, row, f"{k} rỗng không được có trong payload")

    def test_giu_gia_tri_rong_hop_le(self):
        row = anilist.to_anime_row(self.MEDIA)
        self.assertEqual(row["genres"], [])          # [] là dữ liệu thật
        self.assertEqual(row["popularity"], 10)
        self.assertEqual(row["anilist_id"], 5)

    def test_last_synced_at_co_gia_tri(self):
        """Cột này KHÔNG có default ở DB → trước đây 126/126 bộ luôn NULL."""
        self.assertIsNotNone(anilist.to_anime_row(self.MEDIA)["last_synced_at"])

    def test_episode_row_bo_ten_rong(self):
        row = anilist.to_episode_row(1, 3, None)
        self.assertEqual(row, {"anime_id": 1, "number": 3})


class FakeDBJikan:
    def __init__(self, rows, existing):
        self.rows = rows
        self.existing = existing          # {anime_id: [number, ...]}
        self.upserted = []
        self.logs = []
        self.dry = False

    def select(self, table, query):
        if table == "anime":
            return list(self.rows)
        if table == "episodes":
            aid = int(query.split("anime_id=eq.")[1].split("&")[0])
            return [{"number": n} for n in self.existing.get(aid, [])]
        return []

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return self.select(table, query)

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


def jikan_eps(aid, items, total=None, skip_filler=True):
    return [{"anime_id": aid, "number": n} for n in range(1, 13)]


class TestJikanFillGaps(unittest.TestCase):
    ROW = {"id": 1, "slug": "thieu-tap", "title_romaji": "X", "mal_id": 5,
           "episodes_total": 12, "status": "RELEASING"}

    def _run(self, db, **kw):
        buf = io.StringIO()
        with patch("ingest.jikan.episodes", return_value=[{}]), \
                patch("ingest.jikan.episode_rows", side_effect=jikan_eps), \
                redirect_stdout(buf):
            n = ingest_main.job_jikan(db, limit=10, **kw)
        return n, buf.getvalue()

    def test_mac_dinh_bo_qua_bo_da_co_vai_tap(self):
        db = FakeDBJikan([self.ROW], {1: [1, 2]})
        n, _ = self._run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])

    def test_fill_gaps_chi_them_tap_con_thieu(self):
        db = FakeDBJikan([self.ROW], {1: [1, 2]})
        n, out = self._run(db, fill_gaps=True)
        self.assertEqual(n, 10)
        rows = db.upserted[0][1]
        self.assertEqual([r["number"] for r in rows], list(range(3, 13)))
        self.assertIn("+10 tập", out)

    def test_fill_gaps_khong_goi_api_khi_da_du(self):
        db = FakeDBJikan([self.ROW], {1: list(range(1, 13))})
        with patch("ingest.jikan.episodes") as ep:
            n, _ = self._run(db, fill_gaps=True)
        self.assertEqual(n, 0)
        ep.assert_not_called()

    def test_bo_chua_co_tap_van_chay_nhu_cu(self):
        db = FakeDBJikan([self.ROW], {})
        n, _ = self._run(db)
        self.assertEqual(n, 12)
        self.assertEqual([r["number"] for r in db.upserted[0][1]], list(range(1, 13)))
