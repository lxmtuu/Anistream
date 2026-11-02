"""Test `DB.delete` / `DB.patch` dựng tham số PostgREST đúng.

Lỗi thật 02/11/2026 (job TMDB, 63 tập đã ghi nhưng dọn tập cũ thì nổ):
`delete` chỉ ghép `eq.` vào MỌI giá trị, nên `airing_at: "lt.2026-07-06"` thành
`airing_at=eq.lt.2026-07-06` → Postgres `22007 invalid input syntax for type
timestamp with time zone: "lt.…"`. `patch` đã hỗ trợ toán tử từ trước, `delete`
thì chưa — hai hàm lệch nhau. Nay dùng chung `_FILTER_OPS`.
"""
import unittest
from unittest.mock import MagicMock, patch

from ingest import db as dbmod


class FakeResp:
    status_code = 204
    text = ""


class TestFilterOperators(unittest.TestCase):
    def _db(self):
        d = dbmod.DB.__new__(dbmod.DB)      # không cần .env
        d.dry = False
        d.url = "https://example.supabase.co"
        d.key = "k"
        return d

    def test_delete_giu_nguyen_toan_tu(self):
        d = self._db()
        with patch.object(dbmod.requests, "delete", return_value=FakeResp()) as m:
            d.delete("episodes", {"anime_id": 5, "airing_at": "lt.2026-07-06"})
        params = m.call_args.kwargs["params"]
        self.assertEqual(params["airing_at"], "lt.2026-07-06",
                         "phải gửi lt.… chứ KHÔNG phải eq.lt.…")
        self.assertEqual(params["anime_id"], "eq.5")

    def test_delete_toan_tu_gt(self):
        d = self._db()
        with patch.object(dbmod.requests, "delete", return_value=FakeResp()) as m:
            d.delete("episodes", {"anime_id": 5, "airing_at": "gt.2026-09-26"})
        self.assertEqual(m.call_args.kwargs["params"]["airing_at"], "gt.2026-09-26")

    def test_delete_khong_bo_loc_thi_no(self):
        with self.assertRaises(RuntimeError):
            self._db().delete("episodes", {})

    def test_patch_cung_giu_toan_tu(self):
        d = self._db()
        with patch.object(dbmod.requests, "patch", return_value=MagicMock(
                status_code=204, text="")) as m:
            d.patch("anime", {"id": 5}, {"title_vi": "x"})
        self.assertEqual(m.call_args.kwargs["params"]["id"], "eq.5")

    def test_hai_ham_dung_chung_hang_so(self):
        """Chặn tái diễn: sửa hàm này quên hàm kia."""
        self.assertIn("lt", dbmod._FILTER_OPS)
        self.assertIn("gt", dbmod._FILTER_OPS)


if __name__ == "__main__":
    unittest.main()
