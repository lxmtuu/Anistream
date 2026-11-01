"""Test chống rate limit AniList + cache ghép tên ra đĩa.

Bối cảnh thật: `python3 -m ingest.main youtube --deep --limit 200` lấy được 5.560
video rồi đứng im vì AniList trả 429 liên tục (`đợi 38s` lặp mãi). Nguyên nhân:
mỗi tên series tốn tới 4 request, không giãn nhịp, và khi bị 429 thì chỉ ngủ rồi
thử lại y như cũ nên tỉ lệ bị chặn không giảm.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from ingest import anilist, match


class TestThrottle(unittest.TestCase):
    def setUp(self):
        self._min = anilist.MIN_INTERVAL
        self._last = anilist._last_call

    def tearDown(self):
        anilist.MIN_INTERVAL = self._min
        anilist._last_call = self._last

    def test_chờ_khi_2_request_quá_gần(self):
        anilist.MIN_INTERVAL = 1.0
        anilist._last_call = 100.0
        with patch("ingest.anilist.time.monotonic", return_value=100.2), \
             patch("ingest.anilist.time.sleep") as sleep:
            anilist._throttle()
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.8, places=2)

    def test_không_chờ_khi_đã_đủ_giãn_cách(self):
        anilist.MIN_INTERVAL = 1.0
        anilist._last_call = 100.0
        with patch("ingest.anilist.time.monotonic", return_value=105.0), \
             patch("ingest.anilist.time.sleep") as sleep:
            anilist._throttle()
        sleep.assert_not_called()

    def test_bị_429_thì_giãn_nhịp_cho_các_request_sau(self):
        anilist.MIN_INTERVAL = 1.0
        anilist._slow_down("38")
        self.assertGreater(anilist.MIN_INTERVAL, 1.0)

    def test_giãn_nhịp_không_vượt_trần(self):
        anilist.MIN_INTERVAL = anilist.MAX_INTERVAL
        for _ in range(10):
            anilist._slow_down()
        self.assertLessEqual(anilist.MIN_INTERVAL, anilist.MAX_INTERVAL)

    def test_429_tôn_trọng_Retry_After_và_giãn_nhịp(self):
        anilist.MIN_INTERVAL = 1.0
        anilist._last_call = 0.0
        resp = type("R", (), {
            "status_code": 429,
            "headers": {"Retry-After": "7"},
            "json": lambda self: {},
        })()
        with patch("ingest.anilist.requests.post", return_value=resp), \
             patch("ingest.anilist.time.sleep") as sleep, \
             patch("ingest.anilist.time.monotonic", return_value=1000.0):
            with self.assertRaises(RuntimeError):     # hết retry
                anilist.gql("query{x}")
        waits = [c.args[0] for c in sleep.call_args_list]
        self.assertIn(7, waits, "phải ngủ đúng Retry-After")
        self.assertGreater(anilist.MIN_INTERVAL, 1.0)

    def test_Retry_After_rác_không_làm_nổ(self):
        resp = type("R", (), {
            "status_code": 429, "headers": {"Retry-After": "n/a"},
            "json": lambda self: {},
        })()
        with patch("ingest.anilist.requests.post", return_value=resp), \
             patch("ingest.anilist.time.sleep") as sleep, \
             patch("ingest.anilist.time.monotonic", return_value=1000.0):
            with self.assertRaises(RuntimeError):
                anilist.gql("query{x}", retries=2)
        self.assertIn(15, [c.args[0] for c in sleep.call_args_list])


class TestDiskCache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "match_cache.json")

    def test_lưu_và_đọc_lại(self):
        cache = {"a": {"id": 1}, "b": None}
        match.save_disk_cache(cache, self.path)
        self.assertEqual(match.load_disk_cache(self.path), cache)

    def test_file_hỏng_thì_trả_rỗng_không_nổ(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{không phải json")
        self.assertEqual(match.load_disk_cache(self.path), {})

    def test_file_không_tồn_tại(self):
        self.assertEqual(match.load_disk_cache(os.path.join(self.dir, "x.json")), {})

    def test_alias_mới_thì_bỏ_kết_quả_âm_để_thử_lại(self):
        """Biên tập viên thêm alias → tên từng 'không khớp' phải được search lại."""
        match.save_disk_cache({"a": {"id": 1}, "b": None}, self.path)
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        data["aliases_mtime"] = -1                    # giả lập aliases.json vừa sửa
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        out = match.load_disk_cache(self.path)
        self.assertEqual(out, {"a": {"id": 1}}, "mục None phải bị bỏ, mục khớp giữ")
        self.assertNotIn("b", out)

    def test_ghi_nguyên_tử_không_để_lại_file_tmp(self):
        match.save_disk_cache({"a": {"id": 1}}, self.path)
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_thư_mục_chưa_có_thì_tự_tạo(self):
        p = os.path.join(self.dir, "sâu", "hơn", "c.json")
        match.save_disk_cache({"a": {"id": 2}}, p)
        self.assertTrue(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()
