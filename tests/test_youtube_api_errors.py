"""Test cho youtube_api: dịch lỗi Google thành câu hiểu được.

Lý do có file này: khi mới tạo key, 3 lỗi hay gặp nhất là **key sai**, **chưa bật
YouTube Data API v3**, và **hết quota**. Google trả cả 3 dạng 403 kèm `reason`
tiếng Anh; nếu in nguyên body thì người dùng không biết phải bấm vào đâu.
"""
import unittest
from unittest.mock import patch

from ingest import config, youtube_api


def _resp(status=200, body='{}'):
    class R:
        pass
    r = R()
    r.status_code = status
    r.text = body
    r.json = lambda: __import__("json").loads(body)
    return r


class TestExplainError(unittest.TestCase):
    def test_chua_bat_api(self):
        body = ('{"error":{"errors":[{"reason":"accessNotConfigured"}],'
                '"message":"YouTube Data API v3 has not been used in project"}}')
        msg = youtube_api._explain_error(403, body)
        self.assertIn("CHƯA BẬT", msg)
        self.assertIn("Library", msg)          # chỉ đúng chỗ cần bấm
        self.assertIn("403", msg)

    def test_het_quota(self):
        body = '{"error":{"errors":[{"reason":"quotaExceeded"}],"message":"x"}}'
        msg = youtube_api._explain_error(403, body)
        self.assertIn("quota", msg.lower())
        self.assertIn("--deep", msg)           # gợi ý xử lý ngay được

    def test_key_khong_hop_le(self):
        body = '{"error":{"errors":[{"reason":"keyInvalid"}],"message":"Bad Request"}}'
        msg = youtube_api._explain_error(400, body)
        self.assertIn("không hợp lệ", msg)
        self.assertIn("Credentials", msg)

    def test_bi_chan_theo_ip(self):
        body = '{"error":{"errors":[{"reason":"ipRefererBlocked"}],"message":"x"}}'
        self.assertIn("IP", youtube_api._explain_error(403, body))

    def test_body_khong_phai_json_van_khong_no(self):
        msg = youtube_api._explain_error(500, "<html>oops</html>")
        self.assertIn("500", msg)
        self.assertIn("oops", msg)

    def test_reason_la_ma_la_thi_van_bao_ro(self):
        body = '{"error":{"status":"SOMETHING_NEW","message":"lạ"}}'
        msg = youtube_api._explain_error(400, body)
        self.assertIn("SOMETHING_NEW", msg)


class TestGetKiemTraKey(unittest.TestCase):
    def test_thieu_key_bao_ro_kem_duong_dan(self):
        with patch.object(config, "YOUTUBE_API_KEY", ""):
            with self.assertRaises(RuntimeError) as ctx:
                youtube_api._get("channels", part="contentDetails")
        msg = str(ctx.exception)
        self.assertIn("YOUTUBE_API_KEY", msg)
        self.assertIn("console.cloud.google.com", msg)
        self.assertIn("--deep", msg)           # nói luôn cách chạy không cần key

    def test_200_tra_json(self):
        with patch.object(config, "YOUTUBE_API_KEY", "AIza-test"), \
             patch("ingest.youtube_api.requests.get",
                   return_value=_resp(200, '{"items":[]}')) as get:
            out = youtube_api._get("channels", part="contentDetails")
        self.assertEqual(out, {"items": []})
        self.assertEqual(get.call_args.kwargs["params"]["key"], "AIza-test")

    def test_403_thi_no_kem_goi_y(self):
        with patch.object(config, "YOUTUBE_API_KEY", "AIza-test"), \
             patch("ingest.youtube_api.requests.get",
                   return_value=_resp(403, '{"error":{"errors":'
                                           '[{"reason":"quotaExceeded"}]}}')):
            with self.assertRaises(RuntimeError) as ctx:
                youtube_api._get("videos", part="status")
        self.assertIn("quota", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
