import unittest
from unittest.mock import patch
from ingest import youtube, match

class TestMuseRSS(unittest.TestCase):
    def test_channel_and_vietnamese_episode(self):
        self.assertEqual(youtube.CHANNELS[0]['channel_id'], 'UCott96qGP5ADmsB_yNQMvDA')
        p = youtube.parse_title('Ace of the Diamond act II - Mùa 2 - Tập 17 [Việt sub]')
        self.assertEqual(p['episode'], 17)
        self.assertEqual(p['series'], 'Ace of the Diamond act II - Mùa 2')

    def test_reject_highlight(self):
        self.assertIsNone(youtube.parse_title('Khoảnh khắc nổi bật Tập 01 - Đám Cưới Đom Đóm [Việt sub]'))

    def test_collect_skips_unknown(self):
        entries = [dict(video_id='abc', title='Tin tức anime', url='x', published='')]
        with patch.object(youtube, 'CHANNELS', [{'key':'muse_vn','name':'Muse','channel_id':'X','region':'VN'}]), patch.object(youtube, 'fetch_rss', return_value=entries):
            self.assertEqual(youtube.collect(check_embed=False, verbose=False), [])

    def test_vietnamese_alias_keeps_season_and_accents(self):
        self.assertEqual(match._ALIASES[match.alias_key("Chuyện về Đại Thánh Nữ Chuyển Sinh Ẩn Danh")], 187402)
        self.assertNotEqual(match.alias_key("Bộ phim Mùa 1"), match.alias_key("Bộ phim Mùa 2"))

    def test_feed_error_fails_job(self):
        with patch.object(youtube, 'CHANNELS', [{'name':'Muse','channel_id':'X'}]), patch.object(youtube, 'fetch_rss', side_effect=RuntimeError('network')):
            with self.assertRaises(RuntimeError):
                youtube.collect(check_embed=False, verbose=False)

class TestDaiTap(unittest.TestCase):
    """Bản gộp nhiều tập — ca thật từ ảnh chụp app.

    Video "[Bản Lồng Tiếng] One Punch Man - Tập 01-24" (1 video chứa 24 tập) từng
    bị parse thành `episode=1` → app ghi "Tập 1", bấm vào ra video 24 tập, và
    còn GHI ĐÈ link tập 1 thật (khoá upsert anime_id+platform+region+episode).
    """

    def test_ban_gop_ca_bo_thanh_episode_0(self):
        p = youtube.parse_title('[Bản Lồng Tiếng] One Punch Man - Tập 01-24')
        self.assertEqual(p['episode'], 0, 'bản gộp cả bộ = episode 0 (link cho cả bộ)')
        self.assertEqual(p['series'], 'One Punch Man')
        self.assertEqual(p['kind'], 'series')

    def test_ban_gop_ca_bo_tieng_trung(self):
        p = youtube.parse_title('鬼滅の刃 第01-26話')
        self.assertEqual(p['episode'], 0)
        self.assertEqual(p['series'], '鬼滅の刃')

    def test_ban_gop_ca_bo_ep(self):
        self.assertEqual(youtube.parse_title('One Punch Man Ep 01-12')['episode'], 0)

    def test_ban_gop_mot_phan_thi_BO_QUA_khong_gan_sai(self):
        # "Tập 1000-1099" không có số tập đúng để gán → bỏ, thà thiếu còn hơn sai
        self.assertIsNone(youtube.parse_title('Crayon Shin-chan Tập 1000-1099'))
        self.assertIsNone(youtube.parse_title('One Punch Man Tập 5-8'))

    def test_tap_le_van_dung(self):
        self.assertEqual(youtube.parse_title('One Punch Man - Tập 1')['episode'], 1)
        self.assertEqual(youtube.parse_title('鬼滅の刃 第5話')['episode'], 5)
        self.assertEqual(youtube.parse_title('One Punch Man Ep. 7')['episode'], 7)

    def test_dai_tap_khong_anh_huong_ten_series(self):
        self.assertEqual(youtube.parse_title('Crayon Shin-chan Tập 3')['series'],
                         'Crayon Shin-chan')

if __name__ == '__main__': unittest.main()


class TestMuaVietTat(unittest.TestCase):
    """Muse VN ghi "S4" TRẦN — "Re:Zero - … S4 - Tập 83" (03/11/2026).

    Trước đây chỉ nhận "(S4)" có ngoặc nên "S4" dính vào tên bộ ⇒ không khớp bộ
    nào ⇒ mùa 4 của Re:Zero có 0 link dù kênh đăng đủ tập.
    """

    def test_s4_tran_duoc_nhan_la_mua_4(self):
        from ingest import youtube
        p = youtube.parse_title(
            "Re:Zero - Bắt đầu lại từ con số 0 tại thế giới khác S4 - Tập 83 "
            "[Việt sub]")
        self.assertEqual(p["episode"], 83)
        self.assertEqual(p["season"], 4)
        self.assertNotIn("S4", p["series_base"], "S4 phải bị bỏ khỏi tên gốc "
                         "để tìm được bộ trong DB")

    def test_mua_2_tieng_viet_van_dung(self):
        from ingest import youtube
        p = youtube.parse_title("Ace of the Diamond act II - Mùa 2 - Tập 17 "
                                "[Việt sub]")
        self.assertEqual((p["episode"], p["season"]), (17, 2))
        self.assertEqual(p["series_base"], "Ace of the Diamond act II")

    def test_ten_co_chu_s_khong_bi_cat(self):
        from ingest import youtube
        p = youtube.parse_title("Sousou no Frieren - Tập 12")
        self.assertIsNone(p["season"], "chữ 'S' trong tên bộ không phải mùa")
