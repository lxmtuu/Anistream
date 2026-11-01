"""Test xếp nội dung ĐÚNG kênh Muse VN.

Muse VN đăng theo mùa và theo kênh của họ, nên có 3 cái bẫy thật đã gặp:

1. Tiêu đề có "Mùa 2" (tiếng Việt) → `norm()` cũ xoá dấu thành "m a 2" nên tên bị
   lệch, và entry mùa 1 bị dùng cho tập của mùa 2.
2. Muse đăng bản **2011** (148 tập) của Hunter x Hunter trong khi AniList entry khớp
   tên là bản **1999** (62 tập) → 86 link bị gán sai bộ.
3. Video gộp ("Tập 01-24") — xem tests/test_muse_rss.py.

Ở đây kiểm phần THUẦN (không gọi mạng).
"""
import unittest

from ingest import match, youtube


def media(romaji, episodes=None, year=None, popularity=100, english=None):
    return {
        "id": abs(hash(romaji)) % 10**6,
        "title": {"romaji": romaji, "english": english or romaji, "native": None},
        "episodes": episodes,
        "startDate": {"year": year},
        "popularity": popularity,
    }


class TestMuaTrongTieuDe(unittest.TestCase):
    def test_parse_mua_tieng_viet(self):
        p = youtube.parse_title("One Punch Man - Mùa 2 - Tập 5")
        self.assertEqual(p["season"], 2)
        self.assertEqual(p["series_base"], "One Punch Man")
        self.assertEqual(p["episode"], 5)

    def test_parse_nhieu_kieu_mua(self):
        self.assertEqual(youtube.parse_title("Ace of the Diamond - Mùa 2 - Tập 17")["season"], 2)
        self.assertEqual(youtube.parse_title("Fairy Tail (S3) - Tập 51")["season"], 3)
        self.assertEqual(youtube.parse_title("Bộ phim Season 2 - Tập 3")["season"], 2)
        self.assertIsNone(youtube.parse_title("Crayon Shin-chan Tập 3")["season"])

    def test_mua_2_khong_lam_lech_norm(self):
        # "mùa 2" từng bị norm() đổi thành "m a 2" → số 2 còn lại làm lệch điểm
        self.assertEqual(match.norm("One Punch Man - Mùa 2"), match.norm("One Punch Man"))

    def test_nam_trong_tieu_de(self):
        self.assertEqual(youtube.parse_title("Hunter x Hunter (2011) - Tập 100")["year_hint"], 2011)
        self.assertEqual(youtube.parse_title("Fairy Tail 2014 - Tập 51")["year_hint"], 2014)
        self.assertIsNone(youtube.parse_title("One Punch Man - Tập 1")["year_hint"])


class TestChooseEntry(unittest.TestCase):
    def test_chon_mua_theo_ten_entry(self):
        cands = [media("One Punch Man", 12, 2015, 9000),
                 media("One Punch Man 2nd Season", 12, 2019, 5000)]
        best, why = match.choose_entry(cands, "One Punch Man", season=2, max_episode=5)
        self.assertEqual(best["title"]["romaji"], "One Punch Man 2nd Season")
        self.assertIn("mùa 2", why)

    def test_mua_2_chua_co_entry_thi_khong_gan_vao_mua_1(self):
        cands = [media("Some Anime", 12, 2020)]
        best, why = match.choose_entry(cands, "Some Anime", season=2, max_episode=3)
        self.assertIsNone(best, "không được gán tập mùa 2 vào entry mùa 1")
        self.assertIn("mùa 2", why)

    def test_loai_entry_khong_du_cho_tap(self):
        """Ca thật: Hunter x Hunter 1999 (62) vs bản 2011 (148)."""
        cands = [media("HUNTER×HUNTER", 62, 1999, 8000),
                 media("HUNTER×HUNTER (2011)", 148, 2011, 7000)]
        best, why = match.choose_entry(cands, "Hunter x Hunter", max_episode=100)
        self.assertEqual(best["episodes"], 148, "phải chọn bộ đủ 148 tập")
        self.assertIn("khớp tên", why)

    def test_uu_tien_nam_khi_nhieu_ung_vien_du_cho(self):
        cands = [media("Hunter x Hunter", 148, 1999, 9000),
                 media("Hunter x Hunter", 148, 2011, 5000)]
        best, _ = match.choose_entry(cands, "Hunter x Hunter", max_episode=100,
                                     year_hint=2011)
        # không có mùa → xét điểm tên; hoà thì giữ hành vi cũ (không tự bịa)
        self.assertEqual(best["episodes"], 148)

    def test_khong_ung_vien_nao_du_cho_thi_tra_none(self):
        cands = [media("Fairy Tail", 175, 2009, 9000)]
        best, why = match.choose_entry(cands, "Fairy Tail", max_episode=277)
        self.assertIsNone(best)
        self.assertIn("277", why)
        self.assertIn("175", why)

    def test_khong_biet_tong_tap_thi_cho_qua(self):
        cands = [media("Mystery Anime", None, 2024, 10)]
        best, _ = match.choose_entry(cands, "Mystery Anime", max_episode=500)
        self.assertIsNotNone(best)

    def test_ten_khong_khop_thi_bo(self):
        cands = [media("Completely Different Show", 24, 2020)]
        best, why = match.choose_entry(cands, "One Punch Man", max_episode=3)
        self.assertIsNone(best)
        self.assertIn("không khớp", why)

    def test_khong_co_ung_vien(self):
        self.assertIsNone(match.choose_entry([], "X", max_episode=1)[0])


class TestFitsEpisode(unittest.TestCase):
    def test_cac_truong_hop(self):
        self.assertTrue(match.fits_episode({"episodes": 12}, 12))
        self.assertFalse(match.fits_episode({"episodes": 12}, 13))
        self.assertTrue(match.fits_episode({"episodes": None}, 999))
        self.assertTrue(match.fits_episode({}, 5))


class TestOnlyMuseChannel(unittest.TestCase):
    def test_mac_dinh_chi_bat_muse(self):
        import os
        from ingest import config
        # môi trường test không set YOUTUBE_CHANNELS → mặc định chỉ muse_vn
        if os.environ.get("YOUTUBE_CHANNELS"):
            self.skipTest("môi trường có YOUTUBE_CHANNELS")
        self.assertEqual(config.YOUTUBE_CHANNELS, ["muse_vn"])

    def test_ten_kenh_sai_thi_no_kem_danh_sach_hop_le(self):
        from unittest.mock import patch
        from ingest import config
        with patch.object(config, "YOUTUBE_CHANNELS", ["muse_vn", "muse_viet_nam"]):
            with self.assertRaises(RuntimeError) as ctx:
                youtube.enabled_channels()
        msg = str(ctx.exception)
        self.assertIn("muse_viet_nam", msg)
        self.assertIn("muse_vn", msg)

    def test_loc_dung_kenh_theo_cau_hinh(self):
        from unittest.mock import patch
        from ingest import config
        with patch.object(config, "YOUTUBE_CHANNELS", ["ani_one_asia"]):
            chans = youtube.enabled_channels()
        self.assertEqual([c["key"] for c in chans], ["ani_one_asia"])


if __name__ == "__main__":
    unittest.main()
