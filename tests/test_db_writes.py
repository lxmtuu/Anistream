import datetime as dt
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest.db import DB


def _db() -> DB:
    """DB ở chế độ ghi nhưng không cần .env (url/key gán tay)."""
    db = DB(dry_run=True)
    db.dry = False
    db.url = "https://example.supabase.co"
    db.key = "service-key"
    return db


class FakeResp:
    def __init__(self, status=201, body=None, text=""):
        self.status_code = status
        self._body = body if body is not None else []
        self.text = text

    def json(self):
        return self._body


class TestLogIngest(unittest.TestCase):
    def test_finished_at_la_timestamp_that(self):
        """Trước đây gửi 'now()' → Postgres 400 và lỗi im lặng."""
        db = _db()
        with patch("ingest.db.requests.post", return_value=FakeResp(201)) as post:
            db.log_ingest("youtube", "links", True, 16)

        payload = post.call_args.kwargs["json"]
        self.assertNotEqual(payload["finished_at"], "now()")
        parsed = dt.datetime.fromisoformat(payload["finished_at"])
        self.assertIsNotNone(parsed.tzinfo, "phải kèm timezone, nếu không Supabase hiểu sai giờ")

    def test_bao_loi_khi_bang_tu_choi(self):
        db = _db()
        buf = io.StringIO()
        with patch("ingest.db.requests.post",
                   return_value=FakeResp(400, text="invalid input syntax")):
            with redirect_stdout(buf):
                db.log_ingest("youtube", "links", True, 16)
        self.assertIn("ingest_runs từ chối", buf.getvalue())

    def test_audit_khong_lam_chet_job(self):
        db = _db()
        with patch("ingest.db.requests.post", side_effect=RuntimeError("mất mạng")):
            with redirect_stdout(io.StringIO()):
                db.log_ingest("youtube", "links", False, 0)   # không được raise


class TestUpsert(unittest.TestCase):
    def test_chia_lo_200(self):
        db = _db()
        rows = [{"id": i} for i in range(450)]
        with patch("ingest.db.requests.post",
                   return_value=FakeResp(201, body=[])) as post:
            db.upsert("anime", rows, on_conflict="anilist_id")
        self.assertEqual(post.call_count, 3)
        sizes = [len(c.kwargs["json"]) for c in post.call_args_list]
        self.assertEqual(sizes, [200, 200, 50])

    def test_loi_la_raise_khi_khong_bat_fallback(self):
        db = _db()
        with patch("ingest.db.requests.post",
                   return_value=FakeResp(409, text="duplicate key")):
            with self.assertRaises(RuntimeError):
                db.upsert("anime", [{"id": 1}, {"id": 2}], on_conflict="anilist_id")

    def test_fallback_tung_row_bo_qua_row_loi(self):
        """1 URL bị gán cho 2 anime không được làm chết cả lô 200 row."""
        db = _db()

        def post(url, params=None, json=None, headers=None, timeout=None):
            if len(json) > 1:
                return FakeResp(409, text="duplicate key value violates "
                                          "unique index streaming_links_url_uidx")
            if json[0]["url"] == "https://youtu.be/trung":
                return FakeResp(409, text="duplicate key")
            return FakeResp(201, body=json)

        rows = [
            {"url": "https://youtu.be/a", "anime_id": 1},
            {"url": "https://youtu.be/trung", "anime_id": 2},
            {"url": "https://youtu.be/b", "anime_id": 3},
        ]
        buf = io.StringIO()
        with patch("ingest.db.requests.post", side_effect=post):
            with redirect_stdout(buf):
                out = db.upsert("streaming_links", rows,
                                on_conflict="anime_id,platform,region,episode_number",
                                fallback_per_row=True)

        self.assertEqual([r["url"] for r in out],
                         ["https://youtu.be/a", "https://youtu.be/b"])
        log = buf.getvalue()
        self.assertIn("bỏ qua", log)
        self.assertIn("youtu.be/trung", log)

    def test_rong_thi_khong_goi_mang(self):
        db = _db()
        with patch("ingest.db.requests.post") as post:
            self.assertEqual(db.upsert("anime", [], on_conflict="anilist_id"), [])
        post.assert_not_called()

    def test_dry_run_khong_goi_mang(self):
        db = _db()
        db.dry = True
        with patch("ingest.db.requests.post") as post:
            out = db.upsert("anime", [{"id": 1}], on_conflict="anilist_id")
        self.assertEqual(out, [{"id": 1}])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
