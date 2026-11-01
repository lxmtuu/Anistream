"""Test Jikan (MyAnimeList) — nguồn DỰ PHÒNG cho danh sách tập.

Vì sao: AniList chỉ có tổng số tập, TMDB đôi khi thiếu/lệch mùa. Jikan miễn phí,
không cần key, và tra theo `mal_id` mà AniList đã trả (`idMal`).
Giới hạn thật của Jikan: 3 req/s, 60 req/phút → phải giãn nhịp + tôn trọng 429.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import jikan
from ingest import main as ingest_main


def resp(status=200, body=None, headers=None):
    class R:
        pass
    r = R()
    r.status_code = status
    r.headers = headers or {}
    r.text = str(body)
    r.json = lambda: body if body is not None else {}
    return r


class TestParseAired(unittest.TestCase):
    def test_iso_co_timezone(self):
        self.assertEqual(jikan.parse_aired("2018-01-08T00:00:00+00:00"),
                         "2018-01-08T00:00:00+00:00")

    def test_Z_thanh_utc(self):
        self.assertIn("+00:00", jikan.parse_aired("2018-01-08T00:00:00Z"))

    def test_rong_hoac_rac(self):
        for v in (None, "", "không phải ngày"):
            self.assertIsNone(jikan.parse_aired(v))


class TestEpisodeRows(unittest.TestCase):
    ITEMS = [
        {"mal_id": 2, "title": "Tập hai", "aired": "2018-01-15T00:00:00+00:00"},
        {"mal_id": 1, "title": "Episode 1", "aired": "2018-01-08T00:00:00+00:00"},
        {"mal_id": 3, "title": "Filler", "aired": "2018-01-22T00:00:00+00:00",
         "filler": True},
        {"mal_id": 99, "title": "Ngoài dải", "aired": "2019-01-01T00:00:00+00:00"},
    ]

    def test_sap_xep_va_loc(self):
        rows = jikan.episode_rows(7, self.ITEMS, episodes_total=12)
        self.assertEqual([r["number"] for r in rows], [1, 2], "filler + ngoài dải bị bỏ")
        self.assertEqual(rows[0]["anime_id"], 7)

    def test_ten_placeholder_thanh_none(self):
        rows = jikan.episode_rows(7, self.ITEMS, episodes_total=12)
        # Placeholder → KHÔNG có khoá title (gửi None sẽ xoá tên thật khi upsert)
        self.assertNotIn("title", rows[0], "'Episode 1' là placeholder")
        self.assertEqual(rows[1]["title"], "Tập hai")

    def test_khong_biet_tong_thi_khong_cat(self):
        rows = jikan.episode_rows(7, self.ITEMS, episodes_total=None)
        self.assertIn(99, [r["number"] for r in rows])

    def test_giu_filler_neu_yeu_cau(self):
        rows = jikan.episode_rows(7, self.ITEMS, skip_filler=False)
        self.assertIn(3, [r["number"] for r in rows])

    def test_ban_ghi_thieu_so_tap_bi_bo(self):
        rows = jikan.episode_rows(7, [{"mal_id": None, "title": "x"},
                                      {"mal_id": 0, "title": "y"}])
        self.assertEqual(rows, [])


class TestHttp(unittest.TestCase):
    def test_phan_trang(self):
        page1 = {"data": [{"mal_id": 1}], "pagination": {"has_next_page": True}}
        page2 = {"data": [{"mal_id": 2}], "pagination": {"has_next_page": False}}
        with patch.object(jikan, "_get", side_effect=[page1, page2]) as get, \
             patch("ingest.jikan.time.sleep"):
            out = jikan.episodes(123)
        self.assertEqual([e["mal_id"] for e in out], [1, 2])
        self.assertEqual(get.call_count, 2)

    def test_404_bao_ro(self):
        with patch("ingest.jikan.requests.get", return_value=resp(404, {})), \
             patch("ingest.jikan.time.sleep"):
            with self.assertRaises(jikan.JikanError) as ctx:
                jikan._get("/anime/999/episodes")
        self.assertIn("404", str(ctx.exception))

    def test_429_ton_trong_retry_after(self):
        with patch("ingest.jikan.requests.get",
                   side_effect=[resp(429, {}, {"Retry-After": "3"}),
                                resp(200, {"data": []})]), \
             patch("ingest.jikan.time.sleep") as sleep:
            out = jikan._get("/anime/1/episodes")
        self.assertEqual(out, {"data": []})
        self.assertIn(3, [c.args[0] for c in sleep.call_args_list])

    def test_5xx_thu_lai_roi_bao_loi(self):
        with patch("ingest.jikan.requests.get", return_value=resp(503, {})), \
             patch("ingest.jikan.time.sleep"):
            with self.assertRaises(jikan.JikanError):
                jikan._get("/anime/1/episodes", retries=2)

    def test_gian_nhip(self):
        jikan._last_call = 100.0
        with patch("ingest.jikan.time.monotonic", return_value=100.1), \
             patch("ingest.jikan.time.sleep") as sleep:
            jikan._throttle()
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.3, places=2)


class FakeDB:
    def __init__(self, anime_rows, episodes_exist=None):
        self.anime_rows = anime_rows
        self.episodes_exist = episodes_exist or {}
        self.upserted, self.logs, self.queries = [], [], []
        self.dry = False

    def select(self, table, query):
        self.queries.append((table, query))
        if table == "anime":
            return list(self.anime_rows)
        for aid, has in self.episodes_exist.items():
            if f"anime_id=eq.{aid}" in query:
                return [{"number": 1}] if has else []
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {"id": 5, "slug": "one-punch-man", "title_romaji": "One Punch Man",
       "mal_id": 30276, "episodes_total": 12, "status": "FINISHED"}

ITEMS = [{"mal_id": n, "title": f"Tập {n}", "aired": "2015-10-05T00:00:00+00:00"}
         for n in range(1, 13)]


class TestJobJikan(unittest.TestCase):
    def _run(self, db, items=None, only_airing=False):
        with patch.object(jikan, "episodes", return_value=items or ITEMS):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_jikan(db, limit=10, only_airing=only_airing)
        return n, buf.getvalue()

    def test_lap_tap_cho_bo_chua_co(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db)
        self.assertEqual(n, 12)
        self.assertEqual([u[0] for u in db.upserted], ["episodes"])
        self.assertIn("+12 tập", out)

    def test_bo_da_co_tap_thi_khong_dung_toi(self):
        db = FakeDB([dict(ROW)], episodes_exist={5: True})
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])
        self.assertIn("đã có tập", out)

    def test_bi_qua_bo_vuot_tong_so_tap(self):
        db = FakeDB([dict(ROW, episodes_total=6)])
        n, _ = self._run(db)
        self.assertEqual(len(db.upserted[0][1]), 6, "chỉ lấy 6 tập theo episodes_total")

    def test_chi_bo_dang_chieu(self):
        db = FakeDB([dict(ROW)])
        self._run(db, only_airing=True)
        self.assertIn("status=eq.RELEASING", db.queries[0][1])

    def test_loi_jikan_khong_lam_chet_job(self):
        db = FakeDB([dict(ROW), dict(ROW, id=6, mal_id=2, slug="khac")])
        calls = {"n": 0}

        def flaky(mal_id):
            calls["n"] += 1
            if calls["n"] == 1:
                raise jikan.JikanError("429 hết lượt")
            return ITEMS

        with patch.object(jikan, "episodes", side_effect=flaky):
            with redirect_stdout(io.StringIO()) as buf:
                n = ingest_main.job_jikan(db, limit=10)
        self.assertEqual(n, 12, "bộ thứ 2 vẫn được lấp")
        self.assertTrue(db.logs[-1][2], "vẫn ok vì có lấp được")
        self.assertIn("429", buf.getvalue())

    def test_ghi_audit_ingest_runs(self):
        db = FakeDB([dict(ROW)])
        self._run(db)
        self.assertEqual(db.logs[-1][0], "jikan")
        self.assertEqual(db.logs[-1][1], "episodes")


if __name__ == "__main__":
    unittest.main()
