"""Test `anilist.airing_window` — khoảng chiếu dùng để cắt tập TMDB.

Lỗi thật 02/11/2026 (job chạy 220s, "thành công", 0 tập): `gql()` ĐÃ bóc sẵn
lớp `data`, nhưng `airing_window` bóc thêm lần nữa (`data["data"]["Media"]`) nên
luôn nhận `{}` — không lỗi, không cảnh báo, mọi luật "cắt theo khoảng chiếu"
im lặng không chạy. Các test dưới đây khoá đúng chỗ đó.
"""
import datetime as dt
import unittest
from unittest.mock import patch

from ingest import anilist


class TestAiringWindow(unittest.TestCase):
    def _call(self, media):
        with patch.object(anilist, "gql", return_value={"Media": media}):
            return anilist.airing_window(178434)

    def test_doc_dung_start_va_end(self):
        """`gql()` trả `{"Media": …}` (đã bóc `data`) → phải đọc ra ngày."""
        win = self._call({
            "id": 178434, "episodes": 12, "status": "FINISHED",
            "startDate": {"year": 2024, "month": 10, "day": 6},
            "endDate": {"year": 2024, "month": 12, "day": 22},
        })
        self.assertEqual(win["from"], dt.date(2024, 10, 6))
        self.assertEqual(win["to"], dt.date(2024, 12, 22))
        self.assertEqual(win["episodes"], 12)

    def test_dang_chieu_chua_co_ngay_ket_thuc(self):
        win = self._call({
            "id": 204650, "episodes": 12, "status": "RELEASING",
            "startDate": {"year": 2026, "month": 10, "day": 4},
            "endDate": None,
        })
        self.assertEqual(win["from"], dt.date(2026, 10, 4))
        self.assertIsNone(win["to"])

    def test_thieu_ngay_thi_khong_doan(self):
        """AniList chỉ có năm (thiếu tháng/ngày) → KHÔNG bịa ngày."""
        win = self._call({
            "id": 1, "episodes": 12, "status": "FINISHED",
            "startDate": {"year": 2026, "month": None, "day": None},
            "endDate": None,
        })
        self.assertIsNone(win["from"])

    def test_media_null_khong_no(self):
        win = self._call(None)
        self.assertIsNone(win["from"])
        self.assertIsNone(win["to"])

    def test_goi_dung_id(self):
        seen = []
        with patch.object(anilist, "gql",
                          side_effect=lambda q, v: seen.append(v) or {"Media": {}}):
            anilist.airing_window(176301)
        self.assertEqual(seen, [{"id": 176301}])


if __name__ == "__main__":
    unittest.main()
