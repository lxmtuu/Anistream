"""Ghép tên video với bộ ĐÃ CÓ trong DB (gồm `title_vi`) — không cần gọi AniList.

Vì sao (03/11/2026): Muse VN đăng bằng **tên tiếng Việt** ("Đám Cưới Đom Đóm",
"Hội Pháp Sư"). Những tên này không có trong AniList (romaji/english/native) nên
mọi bước ghép tên đều trượt, dù DB đã có bộ đó với `title_vi` do TMDB điền.

Đo trên DB thật: `hotaru-no-yomeiri` 12 tập / **0 link**, trong khi kênh vừa đăng
"Khoảnh khắc nổi bật Tập 01 - Đám Cưới Đom Đóm"; 163 bộ nhưng chỉ 30 bộ có video.
"""
import unittest
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import match


class FakeDB:
    def __init__(self, anime=()):
        self.anime = [dict(a) for a in anime]
        self.upserted = []
        self.dry = False

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        return [dict(a) for a in self.anime] if table == "anime" else []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        if table == "anime":
            return [dict(r, id=r.get("id") or 900) for r in rows]
        return list(rows)


def anime(id_, anilist_id, **kw):
    row = {"id": id_, "anilist_id": anilist_id, "slug": kw.pop("slug", f"a{id_}"),
           "title_vi": None, "title_romaji": None, "title_english": None,
           "title_native": None, "episodes_total": 12, "popularity": 100,
           "format": "TV", "year": 2026}
    row.update(kw)
    return row


def video(series, ep, season=None, url=None):
    return {"series": series, "series_base": series, "episode": ep,
            "season": season, "region": "VN",
            "url": url or f"https://youtu.be/v{ep}", "raw_title": series,
            "video_id": f"v{ep}"}


class TestChuanHoaTen(unittest.TestCase):

    def test_bo_hau_to_mua(self):
        self.assertEqual(ingest_main._bo_mua("Kusuriya (Phần 2)"), "Kusuriya")
        self.assertEqual(ingest_main._bo_mua("Re:Zero S4"), "Re:Zero")
        self.assertEqual(ingest_main._bo_mua("Mob Psycho 100 Mùa 2"), "Mob Psycho 100")
        self.assertEqual(ingest_main._bo_mua("Diamond 2nd Season"), "Diamond")

    def test_khoa_ten_giu_dau_tieng_viet(self):
        self.assertEqual(ingest_main._khoa_ten("Đám Cưới Đom Đóm"),
                         "đám cưới đom đóm")

    def test_khoa_ten_bo_ky_tu_va_khoang_trang(self):
        self.assertEqual(ingest_main._khoa_ten("  Fairy   Tail!! "), "fairy tail")


class TestChiMucTen(unittest.TestCase):

    def test_lap_chi_muc_tu_title_vi(self):
        db = FakeDB([anime(1, 111, title_vi="Đám Cưới Đom Đóm")])
        idx = ingest_main._chi_muc_ten(db)
        self.assertIn("đám cưới đom đóm", idx)
        self.assertEqual(idx["đám cưới đom đóm"][0]["anime_id"], 1)

    def test_bo_qua_bo_khong_co_anilist_id(self):
        db = FakeDB([anime(1, None, title_vi="X")])
        self.assertEqual(ingest_main._chi_muc_ten(db), {})

    def test_loi_doc_db_khong_lam_chet_job(self):
        class Hỏng(FakeDB):
            def select_all(self, *a, **k):
                raise RuntimeError("mất mạng")
        self.assertEqual(ingest_main._chi_muc_ten(Hỏng()), {})


class TestTraChiMuc(unittest.TestCase):

    def setUp(self):
        self.db = FakeDB([
            anime(1, 111, title_vi="Đám Cưới Đom Đóm"),
            anime(2, 222, title_romaji="Mob Psycho 100", episodes_total=12),
            anime(3, 333, title_romaji="Mob Psycho 100 II", episodes_total=13),
            anime(4, 444, title_vi="Koori no Jouheki", slug="koori-no-jouheki",
                  episodes_total=14),
            anime(5, 555, title_vi="Koori no Jouheki (Phần 2)",
                  slug="koori-no-jouheki-2nd-season", episodes_total=28),
        ])
        self.idx = ingest_main._chi_muc_ten(self.db)

    def test_khop_dung_ten_tieng_viet(self):
        e, why = ingest_main._tra_chi_muc(self.idx, "Đám Cưới Đom Đóm",
                                          "Đám Cưới Đom Đóm", None, 3)
        self.assertEqual(e["anime_id"], 1)
        self.assertIn("khớp tên", why)

    def test_nhieu_bo_cung_ten_thi_dung_so_mua(self):
        e, _ = ingest_main._tra_chi_muc(self.idx, "Koori no Jouheki Mùa 2",
                                        "Koori no Jouheki", 2, 5)
        self.assertEqual(e["anime_id"], 5, "S2 phải vào đúng bộ mùa 2")

    def test_khong_co_so_mua_thi_chon_bo_du_cho_tap(self):
        """Chỉ MỘT bộ đủ chỗ cho tập 20 ⇒ nhận bộ đó (28 tập, không phải 14)."""
        e, _ = ingest_main._tra_chi_muc(self.idx, "Koori no Jouheki",
                                        "Koori no Jouheki", None, 20)
        self.assertEqual(e["anime_id"], 5)

    def test_nhap_nhang_thi_tra_rong(self):
        """Tập 5 vừa 14 vừa 28 tập ⇒ KHÔNG đoán (để alias người biên tập)."""
        e, _ = ingest_main._tra_chi_muc(self.idx, "Koori no Jouheki",
                                        "Koori no Jouheki", None, 5)
        self.assertIsNone(e)

    def test_khong_co_trong_db_thi_tra_rong(self):
        e, why = ingest_main._tra_chi_muc(self.idx, "Bộ Hoàn Toàn Lạ", "Bộ Hoàn Toàn Lạ",
                                          None, 1)
        self.assertIsNone(e)
        self.assertEqual(why, "")


class TestTenPhuTrongNgoac(unittest.TestCase):
    """Muse VN có lúc chỉ đăng tên trong ngoặc: "Hội Pháp Sư - Tập 12"."""

    def test_khop_ten_trong_ngoac(self):
        db = FakeDB([anime(1, 6702, title_vi="Fairy Tail (Hội Pháp Sư)",
                           title_romaji="Fairy Tail", episodes_total=175)])
        idx = ingest_main._chi_muc_ten(db)
        e, _ = ingest_main._tra_chi_muc(idx, "Hội Pháp Sư", "Hội Pháp Sư", None, 12)
        self.assertEqual(e["anime_id"], 1)


class TestLinkRowsDungChiMuc(unittest.TestCase):

    def test_title_vi_khop_thi_khong_goi_anilist(self):
        db = FakeDB([anime(1, 111, title_vi="Đám Cưới Đom Đóm", episodes_total=12)])
        videos = [video("Đám Cưới Đom Đóm", 3), video("Đám Cưới Đom Đóm", 4)]
        with patch.object(match, "resolve",
                          side_effect=AssertionError("không được gọi AniList")), \
             patch.object(ingest_main, "_upsert_media",
                          side_effect=AssertionError("không được ghi lại hồ sơ")):
            rows, links, unmatched, review = ingest_main._link_rows(
                db, videos, {}, verbose=False)
        self.assertEqual(unmatched, {})
        self.assertEqual([l["episode_number"] for l in links], [3, 4])
        self.assertTrue(all(l["anime_id"] == 1 for l in links))
        self.assertEqual(rows, [])

    def test_van_ton_trong_chot_chan_vuot_tong(self):
        db = FakeDB([anime(1, 111, title_vi="Đám Cưới Đom Đóm", episodes_total=12)])
        videos = [video("Đám Cưới Đom Đóm", 13)]
        with patch.object(match, "resolve", side_effect=AssertionError):
            _, links, _, review = ingest_main._link_rows(db, videos, {}, verbose=False)
        self.assertEqual(links, [], "tập 13 > 12 tập ⇒ không ghi")
        self.assertEqual(len(review), 1)

    def test_khong_khop_gi_thi_roi_ve_anilist(self):
        db = FakeDB([])
        media = {"id": 999, "title": {"romaji": "Fairy Tail"},
                 "episodes": 175, "popularity": 1, "format": "TV"}
        videos = [video("Fairy Tail", 5)]
        with patch.object(match, "resolve", return_value=(media, 0.9, "alias")), \
             patch.object(match, "_ALIASES", {"fairy tail": 6702}), \
             patch.object(ingest_main, "_upsert_media",
                          return_value=([{"id": 7}], {999: 7})):
            _, links, unmatched, _ = ingest_main._link_rows(db, videos, {}, verbose=False)
        self.assertEqual(unmatched, {})
        self.assertEqual(links[0]["anime_id"], 7)


if __name__ == "__main__":
    unittest.main()
