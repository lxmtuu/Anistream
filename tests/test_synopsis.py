"""Test cho việc lấy mô tả từ AniList (clean_html) + DTO synopsis.

Bối cảnh: `anime.synopsis_vi` chưa bao giờ được ghi (không có bước dịch nào,
`TMDB_API_KEY` đọc ra mà không dùng) → API trả `synopsis: ""` cho mọi anime.
AniList có trả `description` nhưng code cũ vứt đi. Bản vá: lưu bản gốc vào
`synopsis_original` (đã strip HTML) và DTO fallback về đó.
"""
import unittest

from ingest.anilist import clean_html, to_anime_row


class TestCleanHtml(unittest.TestCase):
    def test_strip_tag_giu_noi_dung(self):
        self.assertEqual(
            clean_html("<i>Frieren</i> là <b>pháp sư</b>."),
            "Frieren là pháp sư.",
        )

    def test_br_thanh_xuong_dong(self):
        self.assertEqual(clean_html("Dòng 1<br>Dòng 2<br/>Dòng 3"),
                         "Dòng 1\nDòng 2\nDòng 3")

    def test_giai_ma_entity(self):
        self.assertEqual(
            clean_html("A &amp; B &quot;thử&quot; &#039;này&#039;"),
            'A & B "thử" \'này\'',
        )

    def test_rong_thanh_none(self):
        for v in (None, "", "   ", "<br>", "<p></p>"):
            self.assertIsNone(clean_html(v), f"{v!r} phải là None")

    def test_gop_khoang_trang_thua(self):
        self.assertEqual(clean_html("A      B"), "A B")


class TestAnimeRowSynopsis(unittest.TestCase):
    def _media(self, **over):
        base = {
            "id": 154587,
            "idMal": 52991,
            "title": {"romaji": "Sousou no Frieren", "english": "Frieren",
                      "native": "葬送のフリーレン"},
            "description": "Một <i>pháp sư</i> sống rất lâu.<br>Hành trình bắt đầu.",
            "coverImage": {"large": "https://x/cover.jpg"},
            "bannerImage": None,
            "seasonYear": 2023,
            "season": "FALL",
            "status": "FINISHED",
            "format": "TV",
            "episodes": 28,
            "duration": 24,
            "averageScore": 93,
            "popularity": 300000,
            "genres": ["Adventure"],
            "studios": {"nodes": [{"name": "Madhouse"}]},
        }
        base.update(over)
        return base

    def test_co_synopsis_original(self):
        row = to_anime_row(self._media())
        self.assertEqual(
            row["synopsis_original"],
            "Một pháp sư sống rất lâu.\nHành trình bắt đầu.",
        )

    def test_khong_co_description_thi_none(self):
        # Khoá rỗng bị BỎ khỏi payload (upsert merge-duplicates sẽ ghi NULL đè
        # mô tả tốt đã có nếu ta gửi `synopsis_original: None`).
        self.assertNotIn("synopsis_original", to_anime_row(self._media(description=None)))

    def test_khong_ghi_de_synopsis_vi(self):
        # ingest KHÔNG được tự bịa bản dịch: cột tiếng Việt chỉ do người/dịch điền
        self.assertNotIn("synopsis_vi", to_anime_row(self._media()))


class TestDtoFallback(unittest.TestCase):
    """Kiểm đúng logic fallback của assemble.ts (chép lại biểu thức ở đây để
    khoá hợp đồng: synopsis_vi || synopsis_original || '')."""

    @staticmethod
    def _dto(row):
        return row.get("synopsis_vi") or row.get("synopsis_original") or ""

    def test_uu_tien_ban_dich(self):
        self.assertEqual(
            self._dto({"synopsis_vi": "Bản dịch", "synopsis_original": "Original"}),
            "Bản dịch",
        )

    def test_fallback_ban_goc(self):
        self.assertEqual(
            self._dto({"synopsis_vi": None, "synopsis_original": "Original"}),
            "Original",
        )

    def test_ca_hai_trong(self):
        self.assertEqual(self._dto({"synopsis_vi": None, "synopsis_original": None}), "")


if __name__ == "__main__":
    unittest.main()
