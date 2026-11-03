"""Chặn gọi AniList trong unit test.

VÌ SAO CẦN (03/11/2026 — CI đỏ trong khi máy dev xanh): máy sandbox KHÔNG ra được
`graphql.anilist.co` nên `franchise._lien_quan` nhận lỗi mạng ⇒ trả [] ⇒ code đi
đường "không dựng được mô hình đánh số". CI thì CÓ mạng: cùng test đó nhận dữ liệu
thật của AniList và đi đường khác ⇒ assertion sai. Test phụ thuộc mạng là test đỏ
ngẫu nhiên, tệ hơn không có test.

Mixin này buộc mọi test dùng nó phải chạy với AniList "rỗng", giống máy không mạng.
"""
from unittest.mock import patch

from ingest import franchise


class KhongMang:
    """Trộn vào TestCase: `franchise.anilist.related` luôn trả []."""

    def setUp(self):
        super().setUp()
        p = patch.object(franchise.anilist, "related", return_value=[])
        p.start()
        self.addCleanup(p.stop)
