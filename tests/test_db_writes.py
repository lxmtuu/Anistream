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


class TestPatch(unittest.TestCase):
    """PATCH một phần — dùng cho job TMDB (chỉ sửa đúng cột cần sửa)."""

    def test_gui_dung_filter_va_chi_cot_can_sua(self):
        db = _db()
        with patch("ingest.db.requests.patch", return_value=FakeResp(204)) as p:
            db.patch("anime", {"id": 5}, {"title_vi": "Dược Sư Tự Sự"})

        kwargs = p.call_args.kwargs
        self.assertEqual(kwargs["params"], {"id": "eq.5"})
        self.assertEqual(kwargs["json"], {"title_vi": "Dược Sư Tự Sự"})
        self.assertEqual(kwargs["headers"]["Prefer"], "return=minimal")
        self.assertIn("/rest/v1/anime", p.call_args.args[0])

    def test_khong_goi_mang_khi_khong_co_gi_doi(self):
        db = _db()
        with patch("ingest.db.requests.patch") as p:
            self.assertEqual(db.patch("anime", {"id": 1}, {}), 0)
        p.assert_not_called()

    def test_loi_phai_no(self):
        db = _db()
        with patch("ingest.db.requests.patch",
                   return_value=FakeResp(400, text="column does not exist")):
            with self.assertRaises(RuntimeError) as ctx:
                db.patch("anime", {"id": 1}, {"title_vi": "x"})
        self.assertIn("patch anime lỗi 400", str(ctx.exception))

    def test_dry_run_khong_goi_mang(self):
        db = DB(dry_run=True)
        with patch("ingest.db.requests.patch") as p:
            with redirect_stdout(io.StringIO()):
                db.patch("anime", {"id": 1}, {"title_vi": "x"})
        p.assert_not_called()


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


class TestNhomTheoBoKhoa(unittest.TestCase):
    """PGRST102 — "All object keys must match" (lỗi thật 02/11/2026, job E chết).

    Ta cố ý BỎ khoá rỗng khỏi payload để upsert không ghi NULL đè dữ liệu tốt,
    nên trong 1 lô có row 17 khoá và row 15 khoá. PostgREST từ chối cả request.
    """

    def test_moi_request_deu_dong_nhat_bo_khoa(self):
        rows = [
            {"anilist_id": 1, "slug": "a", "episodes_total": 12, "cover_url": "x"},
            {"anilist_id": 2, "slug": "b"},                    # thiếu 2 khoá
            {"anilist_id": 3, "slug": "c", "episodes_total": 13},
        ]
        sent = []

        def fake_post(url, **kw):
            sent.append(kw["json"])
            return FakeResp(201, [{"anilist_id": r["anilist_id"], "id": r["anilist_id"]}
                                  for r in kw["json"]])

        db = _db()
        with patch("ingest.db.requests.post", side_effect=fake_post):
            out = db.upsert("anime", rows, on_conflict="anilist_id")

        self.assertEqual(len(out), 3, "không được mất row nào")
        for batch in sent:
            self.assertEqual(len({frozenset(r) for r in batch}), 1,
                             f"lô trộn khoá sẽ bị PGRST102: {batch}")

    def test_khong_dien_None_de_lam_day_khoa(self):
        """San phẳng bằng None = quay lại lỗi ghi NULL đè episodes_total."""
        rows = [{"anilist_id": 1, "episodes_total": 12}, {"anilist_id": 2}]
        sent = []
        db = _db()
        with patch("ingest.db.requests.post",
                   side_effect=lambda url, **kw: (sent.append(kw["json"]),
                                                  FakeResp(201, []))[1]):
            db.upsert("anime", rows, on_conflict="anilist_id")

        for batch in sent:
            for r in batch:
                self.assertNotIn(
                    "episodes_total",
                    {k: v for k, v in r.items() if v is None},
                    "không được thêm episodes_total=None vào row vốn không có",
                )

    def test_cung_bo_khoa_thi_chi_1_request(self):
        rows = [{"anilist_id": i, "slug": f"s{i}"} for i in range(5)]
        db = _db()
        with patch("ingest.db.requests.post",
                   return_value=FakeResp(201, [])) as post:
            db.upsert("anime", rows, on_conflict="anilist_id")
        self.assertEqual(post.call_count, 1)

    def test_group_by_keys_cua_ingest_episodes(self):
        """Job A: tập có giờ chiếu thì có `airing_at`, tập không có thì không."""
        from ingest.db import _group_by_keys

        rows = [{"anime_id": 1, "number": 1, "airing_at": "2026-01-01"},
                {"anime_id": 1, "number": 2},]
        groups = _group_by_keys(rows)
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(g) for g in groups], [1, 1])
