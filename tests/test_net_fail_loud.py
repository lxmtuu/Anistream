"""Test chống "xanh mà việc thật không xảy ra" cho job F + lớp mạng.

Ca thật 02/11/2026 (log máy chủ dự án): 39/39 bộ Jikan đều `ConnectTimeout`, job
in 39 dòng lỗi rồi **exit 0** — CI xanh, dữ liệu không đổi, không ai biết.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import requests

from ingest import jikan, net
from ingest import main as ingest_main


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.upserted = []
        self.logs = []
        self.dry = False

    def select(self, table, query):
        return list(self.rows) if table == "anime" else []

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return self.select(table, query)

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {"id": 1, "slug": "one-punch-man", "title_romaji": "One Punch Man",
       "mal_id": 30276, "episodes_total": 12, "status": "FINISHED"}


class TestFailLoud(unittest.TestCase):
    def _run(self, db, exc):
        with patch("ingest.jikan.episodes", side_effect=exc), \
                redirect_stdout(io.StringIO()):
            return ingest_main.job_jikan(db, limit=1)

    def test_100_phan_tram_loi_thi_NO(self):
        db = FakeDB([ROW])
        with self.assertRaises(RuntimeError) as ctx:
            self._run(db, requests.exceptions.ConnectTimeout("timeout"))
        self.assertIn("không lấp được bộ nào", str(ctx.exception))
        self.assertFalse(db.logs[-1][2], "ingest_runs phải ghi ok=false")

    def test_co_it_nhat_1_bo_thanh_cong_thi_khong_no(self):
        """2 bộ: 1 lỗi + 1 lấp được → chỉ cảnh báo, job vẫn xanh."""
        db = FakeDB([ROW, dict(ROW, id=2, slug="khac", mal_id=999)])
        eps = [{"anime_id": 2, "number": n, "title": "T"} for n in range(1, 4)]
        with patch("ingest.jikan.episodes",
                   side_effect=[jikan.JikanError("timeout"), [{}]]), \
                patch("ingest.jikan.episode_rows", return_value=eps), \
                redirect_stdout(io.StringIO()):
            n = ingest_main.job_jikan(db, limit=2)
        self.assertEqual(n, 3)
        self.assertTrue(db.logs[-1][2])   # có lỗi nhưng vẫn ok=true

    def test_khong_co_loi_thi_im_lang_ok(self):
        db = FakeDB([ROW])
        with patch("ingest.jikan.episodes", return_value=[]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(ingest_main.job_jikan(db, limit=1), 0)
        self.assertTrue(db.logs[-1][2])


class TestNet(unittest.TestCase):
    def setUp(self):
        net._ipv4_forced = False
        import urllib3.util.connection as u3
        self._orig = u3.allowed_gai_family
        self.u3 = u3

    def tearDown(self):
        self.u3.allowed_gai_family = self._orig
        net._ipv4_forced = False

    def test_loi_ket_noi_thi_ep_IPv4_va_thu_lai(self):
        calls = []

        class Fake:
            def get(self, url, **kw):
                calls.append(url)
                if len(calls) == 1:
                    raise requests.exceptions.ConnectTimeout("boom")
                return "OK"

        with redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(net.get("https://x/y", session=Fake()), "OK")
        self.assertEqual(len(calls), 2)
        self.assertTrue(net.ipv4_forced())
        self.assertIn("IPv4", buf.getvalue())

    def test_het_luot_thi_NetworkError_kem_goi_y(self):
        class Fake:
            def get(self, url, **kw):
                raise requests.exceptions.ConnectTimeout("boom")

        with redirect_stdout(io.StringIO()), self.assertRaises(net.NetworkError) as ctx:
            net.get("https://api.jikan.moe/v4/x", session=Fake(), retries=2)
        msg = str(ctx.exception)
        self.assertIn("api.jikan.moe", msg)
        self.assertIn("curl -4", msg)

    def test_loi_HTTP_khong_bi_bat_o_day(self):
        """429/500 phải trả về cho tầng trên xử lý, không thành NetworkError."""
        class Fake:
            def get(self, url, **kw):
                return "RESP"

        self.assertEqual(net.get("https://x", session=Fake()), "RESP")


class TestJikanDungNet(unittest.TestCase):
    def test_timeout_mang_thanh_JikanError(self):
        with patch("ingest.net.get", side_effect=net.NetworkError("không tới được")):
            with self.assertRaises(jikan.JikanError):
                jikan._get("/anime/1/episodes")


class TestCauDao(unittest.TestCase):
    """Mạng chết hẳn thì dừng sau 5 bộ, không đốt 800 giây."""

    def test_5_loi_ket_noi_lien_tiep_thi_dung_som(self):
        rows = [dict(ROW, id=i, slug=f"bo-{i}", mal_id=1000 + i) for i in range(10)]
        db = FakeDB(rows)
        calls = []

        def boom(aid):
            calls.append(aid)
            raise jikan.JikanError("không kết nối được tới https://api.jikan.moe/v4/x")

        with patch("ingest.jikan.episodes", side_effect=boom), \
                redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError) as ctx:
            ingest_main.job_jikan(db, limit=10)
        self.assertIn("dừng sớm", str(ctx.exception))
        self.assertEqual(len(calls), 5, "chỉ được thử 5 bộ rồi dừng")

    def test_loi_khong_phai_mang_thi_khong_ngat(self):
        rows = [dict(ROW, id=i, slug=f"bo-{i}", mal_id=1000 + i) for i in range(8)]
        db = FakeDB(rows)
        calls = []

        def boom(aid):
            calls.append(aid)
            raise jikan.JikanError("Jikan 404: không có /anime/1/episodes")

        with patch("ingest.jikan.episodes", side_effect=boom), \
                redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            ingest_main.job_jikan(db, limit=8)
        self.assertEqual(len(calls), 8, "lỗi 404 phải thử hết, không ngắt giữa")
