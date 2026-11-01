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

if __name__ == '__main__': unittest.main()
