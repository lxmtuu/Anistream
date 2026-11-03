"""Hai lỗi làm 129 series của Muse VN không vào được DB (đo 03/11/2026).

1. `match.choose_entry` (xét MÙA + SỐ TẬP) có code và có test nhưng **không được
   gọi ở đâu** — job C dùng `resolve` → `pick_best`, chỉ so tên mờ. Nên
   "Đại chiến người Khổng Lồ S3" không vào entry mùa 3, "One-Punch Man S3" mất.
2. Tiêu đề là TIẾNG VIỆT ("Thất hình đại tội", "Gia Sư Hitman Reborn!") — không có
   trên AniList. Tên gốc (romaji/English/Nhật) nằm trong MÔ TẢ video, chưa từng
   được đọc.
"""
import unittest
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import match, youtube


def media(mid, romaji, episodes=None, fmt="TV", pop=100):
    return {"id": mid, "title": {"romaji": romaji, "english": None, "native": None},
            "episodes": episodes, "format": fmt, "popularity": pop}


class FakeDB:
    def __init__(self):
        self.upserted = []
        self.dry = False

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        if table == "anime":
            return [dict(r, id=500 + i) for i, r in enumerate(rows)]
        return list(rows)


class TestTieuDePhu(unittest.TestCase):
    """Mô tả video Muse VN chứa tên romaji / English / Nhật."""

    DESC = """Danh sách phát đầy đủ các tập: https://www.youtube.com/playlist?list=X

Re:Zero kara Hajimeru Isekai Seikatsu S4
Re:ZERO -Starting Life in Another World- S4
Re：ゼロから始める異世界生活S4

【Nội dung câu chuyện】
Anime được chiếu trực tiếp miễn phí trên Muse Việt Nam!
➨ Subscribe Kênh của Muse
"""

    def test_lay_ten_romaji_va_nhat(self):
        ten = youtube.tieu_de_phu(self.DESC)
        self.assertIn("Re:Zero kara Hajimeru Isekai Seikatsu S4", ten)
        self.assertIn("Re：ゼロから始める異世界生活S4", ten)

    def test_bo_boilerplate_va_link(self):
        ten = youtube.tieu_de_phu(self.DESC)
        for x in ten:
            self.assertNotIn("http", x)
            self.assertNotIn("Subscribe", x)
            self.assertNotIn("chiếu trực tiếp", x)

    def test_gioi_han_so_dong(self):
        desc = "\n".join(f"Tên thay thế số {i}" for i in range(10))
        self.assertEqual(len(youtube.tieu_de_phu(desc)), 4)

    def test_mo_ta_rong(self):
        self.assertEqual(youtube.tieu_de_phu(""), [])
        self.assertEqual(youtube.tieu_de_phu(None), [])


class TestResolveSeriesXetMua(unittest.TestCase):

    CANDS = [media(1, "Shingeki no Kyojin", 25),
             media(2, "Shingeki no Kyojin Season 3", 22),
             media(3, "Shingeki no Kyojin Season 3 Part 2", 10)]

    def test_mua_3_vao_dung_entry_mua_3(self):
        with patch.object(match, "search_candidates", return_value=self.CANDS):
            m, _, why = match.resolve_series("Shingeki no Kyojin Season 3",
                                             season=3, max_episode=5)
        self.assertEqual(m["id"], 2, f"phải là entry mùa 3, nhận: {m['title']}")

    def test_tap_20_loai_entry_chi_co_10_tap(self):
        with patch.object(match, "search_candidates", return_value=self.CANDS):
            m, _, _ = match.resolve_series("Shingeki no Kyojin", season=3,
                                           max_episode=20)
        self.assertEqual(m["id"], 2, "entry Part 2 (10 tập) không chứa tập 20")

    def test_mua_khong_co_tren_anilist_thi_khong_gan_bua(self):
        with patch.object(match, "search_candidates", return_value=self.CANDS):
            m, _, why = match.resolve_series("Shingeki no Kyojin Season 9",
                                             season=9, max_episode=1)
        self.assertIsNone(m)
        self.assertIn("mùa 9", why)

    def test_ten_tu_mo_ta_di_iem_thap_thi_tu_choi(self):
        with patch.object(match, "search_candidates", return_value=self.CANDS):
            m, _, why = match.resolve_series("Câu chuyện kể về Subaru",
                                             max_episode=1, min_score=0.85)
        self.assertIsNone(m)
        self.assertIn("điểm", why)

    def test_cache_cho_lan_sau(self):
        cache = {}
        with patch.object(match, "search_candidates", return_value=self.CANDS):
            match.resolve_series("Shingeki no Kyojin", season=3, max_episode=5,
                                 cache=cache)
        with patch.object(match, "search_candidates",
                          side_effect=AssertionError("không được search lại")):
            m, _, why = match.resolve_series("Shingeki no Kyojin", season=3,
                                             max_episode=5, cache=cache)
        self.assertEqual(m["id"], 2)
        self.assertIn("cache", why)


class TestLinkRowsDungMoTa(unittest.TestCase):
    """Video có tiêu đề tiếng Việt nhưng mô tả có tên gốc → phải ghép được."""

    def test_ghep_qua_ten_trong_mo_ta(self):
        v = {"series": "Thất hình đại tội S2", "series_base": "Thất hình đại tội",
             "episode": 3, "season": 2, "region": "VN",
             "url": "https://youtu.be/x", "raw_title": "Thất hình đại tội S2 - Tập 3",
             "description": "Nanatsu no Taizai: Imashime no Fukkatsu"}
        db = FakeDB()
        da_goi = []

        def fake_resolve(name, **kw):
            da_goi.append(name)
            if name == "Nanatsu no Taizai: Imashime no Fukkatsu":
                return media(777, name, 24), 0.95, "khớp tên"
            return None, 0.3, "không khớp"

        with patch.object(match, "resolve_series", side_effect=fake_resolve):
            rows, links, unmatched, _, _cs, _mx = ingest_main._link_rows(
                db, [v], {}, verbose=False)
        self.assertEqual(unmatched, {})
        self.assertEqual(len(links), 1)
        self.assertIn("Nanatsu no Taizai: Imashime no Fukkatsu", da_goi)
        self.assertEqual(len(rows), 1, "bộ mới phải được tạo trong bảng anime")

    def test_mo_ta_khong_lam_mat_chot_chan_vuot_tong(self):
        v = {"series": "Bộ Lạ", "series_base": "Bộ Lạ", "episode": 99,
             "season": None, "region": "VN", "url": "https://youtu.be/y",
             "raw_title": "Bộ Lạ - Tập 99", "description": ""}
        db = FakeDB()
        with patch.object(match, "resolve_series",
                          return_value=(media(888, "Bộ Lạ", 12), 1.0, "khớp")):
            _, links, _, review, _cs, _mx = ingest_main._link_rows(db, [v], {}, verbose=False)
        self.assertEqual(links, [])
        self.assertEqual(len(review), 1)


if __name__ == "__main__":
    unittest.main()


class TestNhoKetQuaAm(unittest.TestCase):
    """Kết quả ÂM phải được nhớ — nếu không, job C bắn hàng chục nghìn request.

    Đo 03/11/2026: 104 tên chưa khớp / **1647 video**. Mỗi tên tốn 1–5 request
    AniList; không nhớ kết quả âm thì mỗi VIDEO lại hỏi lại ⇒ ~24.000 request,
    AniList giới hạn ~90 req/phút ⇒ chạy hàng giờ, vẫn 0 link, và dễ bị chặn.
    """

    def test_lan_2_dung_cache_am_khong_search(self):
        cache = {}
        with patch.object(match, "search_candidates", return_value=[]):
            m, _, why = match.resolve_series("Bộ Không Tồn Tại", cache=cache)
        self.assertIsNone(m)
        self.assertIn("không", why)
        self.assertIsNone(cache[match.alias_key("Bộ Không Tồn Tại")])
        with patch.object(match, "search_candidates",
                          side_effect=AssertionError("không được search lại")):
            m2, _, why2 = match.resolve_series("Bộ Không Tồn Tại", cache=cache)
        self.assertIsNone(m2)
        self.assertIn("cache", why2)

    def test_nhieu_video_cung_ten_chi_search_mot_lan(self):
        goi = []

        def dem(name, per_page=10):
            goi.append(name)
            return []

        with patch.object(match, "search_candidates", side_effect=dem):
            cache = {}
            for _ in range(50):
                match.resolve_series("Gia Sư Hitman Reborn!", cache=cache)
        self.assertEqual(len(goi), 1, "50 video cùng tên ⇒ chỉ 1 lần search")
