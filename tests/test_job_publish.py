"""Test Job I (`python3 -m ingest.main publish`) — ẩn bộ KHÔNG có nội dung.

Vì sao: 12 bộ đã chiếu xong mà **0 tập, 0 video** vẫn nằm trên trang chủ
(đo 02/11/2026, sau khi dời 148 link của HUNTER×HUNTER sang bộ 2011 thì bộ 1999
thành trang trắng). `anime.is_published` mặc định `true` và không job nào đụng
tới ⇒ người dùng bấm vào là trang rỗng.

Khoá các hành vi:
  · FINISHED + 0 tập + 0 link → `is_published = false`
  · có tập HOẶC có link → phải hiện (kể cả FINISHED)
  · chưa chiếu xong (RELEASING / NOT_YET_RELEASED) → giữ hiện
  · đang ẩn mà đã có tập → BẬT LẠI (tự chữa lành, không cần sửa tay)
  · ghi không ăn → NỔ (bẫy `patch` trả 1 dù PostgREST 204 khớp 0 dòng)
  · dry-run → không PATCH
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main


class FakeDB:
    """DB giả tối thiểu: `anime` + `episodes` + `streaming_links`.

    `ghi_that=False` mô phỏng PostgREST trả 204 mà không đổi dòng nào — đúng
    kiểu hỏng đã gặp với `delete` trước đây.
    """

    def __init__(self, anime, tap=(), link=(), ghi_that=True):
        self.anime = [dict(a) for a in anime]
        self.tap = set(tap)
        self.link = set(link)
        self.ghi_that = ghi_that
        self.patches = []
        self.dry = False

    def select_all(self, table, query):
        if table == "anime":
            return [dict(a) for a in self.anime]
        if table == "episodes":
            return [{"anime_id": i} for i in self.tap]
        if table == "streaming_links":
            return [{"anime_id": i} for i in self.link]
        return []

    def patch(self, table, filters, values):
        self.patches.append((table, filters, dict(values)))
        if self.ghi_that:
            for a in self.anime:
                if a["id"] == filters["id"]:
                    a.update(values)
        return 1                    # luôn 1 — y như PostgREST 204


def A(id_, slug, status="FINISHED", published=True, total=12):
    return {"id": id_, "slug": slug, "status": status,
            "episodes_total": total, "is_published": published}


class TestJobPublish(unittest.TestCase):

    def _run(self, db):
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ingest_main.job_publish(db)
        return n, buf.getvalue()

    def test_an_bo_hoan_thanh_0_tap_0_link(self):
        db = FakeDB([A(1, "hunter-hunter")])
        n, out = self._run(db)
        self.assertEqual(n, 1)
        self.assertEqual(db.patches, [("anime", {"id": 1},
                                       {"is_published": False})])
        self.assertFalse(db.anime[0]["is_published"])
        self.assertIn("hunter-hunter", out)

    def test_co_tap_hoac_co_link_thi_van_hien(self):
        db = FakeDB([A(1, "co-tap"), A(2, "chi-co-link")], tap={1}, link={2})
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.patches, [], "không được đụng bộ có nội dung")
        self.assertTrue(all(a["is_published"] for a in db.anime))

    def test_chua_chieu_xong_thi_giu_hien(self):
        db = FakeDB([A(1, "dang-chieu", status="RELEASING"),
                     A(2, "sap-chieu", status="NOT_YET_RELEASED", total=None)])
        n, _ = self._run(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.patches, [])
        self.assertTrue(all(a["is_published"] for a in db.anime))

    def test_dang_an_ma_da_co_tap_thi_bat_lai(self):
        db = FakeDB([A(1, "vua-co-tap", published=False)], tap={1})
        n, out = self._run(db)
        self.assertEqual(n, 1)
        self.assertEqual(db.patches, [("anime", {"id": 1},
                                       {"is_published": True})])
        self.assertTrue(db.anime[0]["is_published"])
        self.assertIn("hiện lại", out)

    def test_ghi_khong_an_thi_no(self):
        db = FakeDB([A(1, "hunter-hunter")], ghi_that=False)
        with self.assertRaises(RuntimeError) as ctx:
            self._run(db)
        self.assertIn("is_published", str(ctx.exception))
        self.assertIn("hunter-hunter", str(ctx.exception))

    def test_dry_run_khong_patch(self):
        db = FakeDB([A(1, "hunter-hunter")])
        db.dry = True
        n, out = self._run(db)
        self.assertEqual((n, db.patches), (0, []))
        self.assertIn("dry-run", out)

    def test_idempotent_lan_chay_thu_hai(self):
        db = FakeDB([A(1, "hunter-hunter"), A(2, "co-tap")], tap={2})
        self._run(db)
        db.patches.clear()
        n, out = self._run(db)
        self.assertEqual((n, db.patches), (0, []))
        self.assertIn("đúng trạng thái hiển thị", out)

    def test_cli_goi_job(self):
        db = FakeDB([A(1, "hunter-hunter")])
        with patch.object(ingest_main.dbmod, "DB", return_value=db), \
             redirect_stdout(io.StringIO()):
            ingest_main.main(["publish"])
        self.assertEqual(len(db.patches), 1)


if __name__ == "__main__":
    unittest.main()
