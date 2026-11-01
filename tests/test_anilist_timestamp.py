"""Test hồi quy cho lỗi 22008 của job A.

Lỗi thật gặp trên project Supabase thật (2026-11-01):

    POST /rest/v1/episodes 400
    {"code":"22008","message":"date/time field value out of range: \"1793536200\""}

Nguyên nhân: AniList trả `airingAt` là epoch GIÂY (int), code cũ gán thẳng vào
`airing_at` (timestamptz) → Postgres không hiểu → **chết cả job A**, nên không
có anime/episode nào vào DB dù AniList trả về 22 tập.

Test này khoá lại hành vi đúng: luôn gửi chuỗi ISO 8601 có timezone.
"""
import datetime as dt
import unittest

from ingest.anilist import to_episode_row, to_iso


class TestIsoTimestamp(unittest.TestCase):
    def test_epoch_int_thanh_iso_utc(self):
        # 1793536200 = 2026-11-01T12:30:00Z
        self.assertEqual(to_iso(1793536200), "2026-11-01T12:30:00+00:00")

    def test_anh_xa_dung_thoi_diem(self):
        self.assertEqual(
            dt.datetime.fromisoformat(to_iso(1793536200)).timestamp(),
            1793536200,
        )

    def test_co_timezone(self):
        out = to_iso(1793536200)
        self.assertIsNotNone(dt.datetime.fromisoformat(out).tzinfo)

    def test_chuoi_iso_giu_nguyen(self):
        self.assertEqual(to_iso("2026-11-01T00:00:00Z"), "2026-11-01T00:00:00Z")

    def test_rong_thanh_none(self):
        self.assertIsNone(to_iso(None))
        self.assertIsNone(to_iso(""))

    def test_episode_row_khong_con_so_tho(self):
        row = to_episode_row(anime_id=7, number=3, airing_at=1793536200)
        self.assertEqual(row["airing_at"], "2026-11-01T12:30:00+00:00")
        self.assertNotIsInstance(row["airing_at"], int)
        self.assertEqual(row["number"], 3)
        self.assertEqual(row["anime_id"], 7)
        # HỒI QUY: title rỗng phải BỎ HẲN khoá khỏi payload (không phải gửi None).
        # Gửi `title: None` → upsert merge-duplicates ghi NULL đè lên tên tập mà
        # TMDB/Jikan đã điền; job A chạy 30 phút/lần nên xoá sạch tên tập.
        self.assertNotIn("title", row)

    def test_episode_row_giu_title(self):
        self.assertEqual(to_episode_row(1, 1, 1793536200, "Tập 1")["title"], "Tập 1")


if __name__ == "__main__":
    unittest.main()
