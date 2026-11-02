"""Chặn tái diễn: cron khai báo nhưng KHÔNG có nhánh `case` ⇒ rơi vào `*)`
và chạy `all` (việc thật không xảy ra dù CI xanh).

Đo 02/11/2026: cron `10 */6` chỉ đọc RSS = 15 video mới nhất/kênh nên **không
bao giờ** lấy được lịch sử kênh; 94 bộ liệt kê tập mà 0 video. Thêm cron 03:30
chạy `youtube --deep` và bắt Job I (`publish`) + Job J (`coverage`) chạy kèm.
"""
import os
import re
import unittest

WF = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows",
                  "ingest.yml")


class TestWorkflowCron(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(WF, encoding="utf-8") as f:
            cls.text = f.read()

    def test_moi_cron_deu_co_nhanh_case(self):
        crons = re.findall(r'^\s*- cron: "([^"]+)"', self.text, re.M)
        self.assertGreaterEqual(len(crons), 5)
        for c in crons:
            self.assertIn(f'"{c}"', self.text.split("case ")[1],
                          f"cron {c} không có nhánh case ⇒ rơi vào *)")

    def test_backfill_sau_chay_youtube_deep(self):
        arm = self.text.split('"30 3 * * *")')[1].split(";;")[0]
        self.assertIn("cmd=youtube", arm)
        self.assertIn("--deep", arm)

    def test_cron_6h_khong_bi_bien_thanh_deep(self):
        arm = self.text.split('"10 */6 * * *")')[1].split(";;")[0]
        self.assertIn("cmd=youtube", arm)
        self.assertNotIn("--deep", arm, "cron 6h phải giữ RSS cho rẻ")

    def test_buoc_chay_ingest_goi_publish_va_coverage(self):
        body = self.text.split("Chạy ingest")[1].split("Upload")[0]
        self.assertIn("python -m ingest.main publish", body)
        self.assertIn("python -m ingest.main coverage", body)
        self.assertIn("python -m ingest.main check", body)


if __name__ == "__main__":
    unittest.main()
