"""Test `ingest/qa.py` + Job G — kiểm bất biến dữ liệu.

Các lỗi đã thật sự xảy ra trên DB (01/11/2026) mà trước đây không chỗ nào phát hiện:
  · 1 bộ có 12 tập trong khi `episodes_total` = 3 (`fool-night`)
  · 8 bộ có 12–13 tập nhưng `episodes_total` = NULL
  · 194 link có số tập vượt tổng (ghép sai mùa: `fairy-tail`, `hunter-hunter`)
"""
import io
import unittest
from contextlib import redirect_stdout

from ingest import qa
from ingest import main as ingest_main


class FakeDB:
    def __init__(self, anime, episodes, links, dry=False):
        self.data = {"anime": anime, "episodes": episodes, "streaming_links": links}
        self.dry = dry
        self.logs = []
        self.queries = []

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        self.queries.append((table, query))
        return [dict(r) for r in self.data.get(table, [])]

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ANIME = [
    {"id": 1, "slug": "onepunch", "episodes_total": 12, "status": "FINISHED"},
    {"id": 2, "slug": "khong-tong", "episodes_total": None, "status": "RELEASING"},
]


def link(aid, ep, url=None):
    return {"anime_id": aid, "episode_number": ep, "platform": "youtube",
            "region": "VN", "kind": "free_legal", "is_verified": True,
            "url": url or f"https://www.youtube.com/watch?v=v{aid}_{ep}"}


class TestCollect(unittest.TestCase):
    def test_du_lieu_sach_khong_vi_pham(self):
        v = qa.collect(FakeDB(
            ANIME,
            [{"anime_id": 1, "number": n} for n in range(1, 13)],
            [link(1, n) for n in range(1, 13)],
        ))
        self.assertEqual(v["hard"], {})
        self.assertFalse(qa.has_hard(v))
        self.assertEqual(v["soft"]["bo_co_link_0_tap"], [])

    def test_tap_vuot_tong_la_vi_pham_cung(self):
        """Ca thật: fool-night 12 tập nhưng AniList ghi 3."""
        v = qa.collect(FakeDB(
            [{"id": 1, "slug": "fool-night", "episodes_total": 3, "status": "X"}],
            [{"anime_id": 1, "number": n} for n in range(1, 13)],
            [],
        ))
        self.assertIn("tap_vuot_tong", v["hard"])
        self.assertIn("fool-night", v["hard"]["tap_vuot_tong"][0])
        self.assertTrue(qa.has_hard(v))

    def test_tap_danh_so_0_hoac_am(self):
        v = qa.collect(FakeDB(ANIME, [{"anime_id": 1, "number": 0},
                                      {"anime_id": 1, "number": -2}], []))
        self.assertIn("tap_danh_so_sai", v["hard"])

    def test_slug_trung(self):
        v = qa.collect(FakeDB([dict(ANIME[0]), dict(ANIME[0], id=9)], [], []))
        self.assertEqual(v["hard"]["slug_trung"], ["onepunch"])

    def test_mot_url_gan_2_bo_la_loi(self):
        v = qa.collect(FakeDB(ANIME, [], [link(1, 1, "https://youtu.be/AAAA"),
                                          link(2, 1, "https://youtu.be/AAAA")]))
        self.assertIn("url_trung", v["hard"])

    def test_dong_mo_coi(self):
        v = qa.collect(FakeDB(ANIME, [{"anime_id": 999, "number": 1}],
                              [link(888, 1)]))
        self.assertEqual(len(v["hard"]["dong_mo_coi"]), 2)

    def test_link_vuot_tong_chi_la_canh_bao(self):
        """fairy-tail: link tập 176–277, tổng 175 → nghi ghép sai mùa."""
        v = qa.collect(FakeDB(ANIME, [{"anime_id": 1, "number": 1}],
                              [link(1, 1), link(1, 200)]))
        self.assertIn("link_vuot_tong", v["soft"])
        self.assertEqual(v["hard"], {})

    def test_bo_co_link_0_tap(self):
        v = qa.collect(FakeDB(ANIME, [], [link(1, 1)]))
        self.assertEqual(v["soft"]["bo_co_link_0_tap"], ["onepunch"])

    def test_bo_chi_co_ban_gop_van_bi_canh_bao(self):
        """Link episode_number = 0 ("cả bộ") không tạo được tập nào trong DB."""
        v = qa.collect(FakeDB(ANIME, [], [link(1, 0)]))
        self.assertEqual(v["soft"]["bo_co_link_0_tap"], ["onepunch"])

    def test_dem_bo_khong_biet_tong(self):
        self.assertEqual(qa.collect(FakeDB(ANIME, [], []))["soft"]["bo_khong_biet_tong"], 1)


class TestKiemTraMoi(unittest.TestCase):
    """Hai kiểm tra thêm 02/11/2026, đều từ lỗi THẬT đã xảy ra trên DB."""

    def test_tap_trung_ngay_chieu_bi_canh_bao(self):
        """`tensei-…-3rd-season` từng có 24 dòng: 1..12 và 25..36 CÙNG ngày."""
        anime = [{"id": 1, "slug": "tensei-3rd", "episodes_total": 36,
                  "status": "RELEASING"}]
        days = [f"2026-{m:02d}-{d:02d}T00:00:00Z"
                for m, d in ((9, 27), (10, 4), (10, 11), (10, 18), (10, 26),
                             (11, 1), (11, 8), (11, 15), (11, 22), (11, 29),
                             (12, 6), (12, 13))]
        eps = [{"anime_id": 1, "number": n, "airing_at": day}
               for n, day in zip(range(1, 13), days)]
        # 25..36 dùng đúng 12 ngày đó → chắc chắn là bản trùng
        eps += [{"anime_id": 1, "number": n, "airing_at": day}
                for n, day in zip(range(25, 37), days)]
        v = qa.collect(FakeDB(anime, eps, []))
        self.assertTrue(v["soft"]["tap_trung_ngay_chieu"], v["soft"])

    def test_hai_tap_cung_ngay_nhung_dung_tong_thi_khong_bao(self):
        """Double-episode thật (13 tập / 13 dòng, 2 tập trùng ngày) → không cảnh báo."""
        anime = [{"id": 1, "slug": "chitose", "episodes_total": 13,
                  "status": "FINISHED"}]
        eps = [{"anime_id": 1, "number": n, "airing_at": f"2025-10-{n:02d}T00:00:00Z"}
               for n in range(1, 14)]
        eps[12]["airing_at"] = eps[11]["airing_at"]
        v = qa.collect(FakeDB(anime, eps, []))
        self.assertEqual(v["soft"]["tap_trung_ngay_chieu"], [])

    def test_bo_hoan_thanh_trang_trang_bi_bao(self):
        """Bộ FINISHED, biết tổng, 0 tập, 0 video → app mở ra trang rỗng."""
        anime = [{"id": 1, "slug": "trang", "episodes_total": 12,
                  "status": "FINISHED"}]
        v = qa.collect(FakeDB(anime, [], []))
        self.assertEqual(v["soft"]["bo_hoan_thanh_0_tap"], ["trang"])

    def test_bo_dang_chieu_0_tap_thi_khong_bao(self):
        anime = [{"id": 1, "slug": "sap-chieu", "episodes_total": 12,
                  "status": "RELEASING"}]
        v = qa.collect(FakeDB(anime, [], []))
        self.assertEqual(v["soft"]["bo_hoan_thanh_0_tap"], [])


class TestJobCheck(unittest.TestCase):
    def _run(self, db, strict=True):
        buf = io.StringIO()
        with redirect_stdout(buf):
            n = ingest_main.job_check(db, strict=strict)
        return n, buf.getvalue()

    def test_sach_thi_khong_no(self):
        db = FakeDB(ANIME, [{"anime_id": 1, "number": 1}], [link(1, 1)])
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertIn("nhất quán", out)
        self.assertEqual(db.logs[-1][:4], ("qa", "check", True, 0))

    def test_vi_pham_cung_thi_NO(self):
        db = FakeDB([{"id": 1, "slug": "x", "episodes_total": 3, "status": "X"}],
                    [{"anime_id": 1, "number": 9}], [])
        with self.assertRaises(RuntimeError):
            self._run(db)
        self.assertFalse(db.logs[-1][2], "phải ghi ingest_runs ok=false")

    def test_no_strict_thi_chi_canh_bao(self):
        db = FakeDB([{"id": 1, "slug": "x", "episodes_total": 3, "status": "X"}],
                    [{"anime_id": 1, "number": 9}], [])
        n, out = self._run(db, strict=False)
        self.assertEqual(n, 1)
        self.assertIn("VI PHẠM CỨNG", out)

    def test_dry_run_khong_goi_db(self):
        db = FakeDB([], [], [], dry=True)
        self.assertEqual(self._run(db)[0], 0)
        self.assertEqual(db.queries, [])
