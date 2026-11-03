"""Job K — tên tiếng Việt trên kênh → bộ trong DB (TMDB → AniList).

Đo 03/11/2026: 51 tên / 601 video vẫn không vào được DB, gồm những bộ lớn nhất
của kênh ("Đại chiến người Khổng Lồ S1" 50 video, "Thất hình đại tội S2" 24…).
Tên tiếng Việt KHÔNG có trong AniList; cầu nối duy nhất là TMDB `original_name`
(tiếng Nhật) → AniList search.
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import match, tmdb, youtube


class FakeDB:
    def __init__(self, unmatched=None):
        self.unmatched = unmatched or []
        self.upserted = []
        self.logs = []
        self.dry = False
        self.dry_run = False

    def select_all(self, table, query, page_size=1000, max_rows=200000):
        if table == "ingest_unmatched":
            return [dict(r) for r in self.unmatched]
        if table == "anime_alias":
            return []
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows), on_conflict))
        if table == "anime":
            return [dict(r, id=77) for r in rows]
        return list(rows)

    @property
    def dry(self):
        return self._dry

    @dry.setter
    def dry(self, v):
        self._dry = v

    def delete(self, table, filters):
        self.upserted.append((f"delete:{table}", [filters], None))
        return 1

    def log_ingest(self, *a, **k):
        self.logs.append(a)


ROW = {"series_name": "Đại chiến người Khổng Lồ S3", "videos": 45, "max_episode": 22}
TMDB_HIT = {"id": 1429, "name": "Đại chiến người Khổng Lồ",
            "original_name": "進撃の巨人"}
DETAIL = {"id": 1429, "original_name": "進撃の巨人", "name": "Đại chiến người Khổng Lồ",
          "translations": {"translations": [
              {"iso_639_1": "en", "data": {"name": "Attack on Titan"}}]}}
AL_CANDS = [
    {"id": 16498, "title": {"romaji": "Shingeki no Kyojin", "native": "進撃の巨人"},
     "episodes": 25, "format": "TV", "popularity": 100},
    {"id": 99147, "title": {"romaji": "Shingeki no Kyojin Season 3",
                            "native": "進撃の巨人 Season３"},
     "episodes": 22, "format": "TV", "popularity": 100},
]


class TestJobAlias(unittest.TestCase):

    def _run(self, db, **kw):
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(TMDB_HIT, 0.95)), \
             patch.object(tmdb, "fetch_detail", return_value=DETAIL), \
             patch.object(ingest_main.anilist, "search_media",
                          return_value=AL_CANDS):
            with redirect_stdout(buf):
                n = ingest_main.job_alias(db, **kw)
        return n, buf.getvalue()

    def test_ghi_alias_va_chon_dung_mua(self):
        db = FakeDB([ROW])
        n, out = self._run(db)
        self.assertEqual(n, 2, "ghi 2 dòng alias (tên đầy đủ + tên đã bỏ mùa)")
        alias_ups = [u for u in db.upserted if u[0] == "anime_alias"][0]
        keys = {r["alias_key"] for r in alias_ups[1]}
        self.assertIn("đại chiến người khổng lồ s3", keys)
        self.assertIn("đại chiến người khổng lồ", keys)
        self.assertEqual(alias_ups[2], "anime_id,alias_key")
        # phải chọn entry MÙA 3 (22 tập), không phải mùa 1
        anime_ups = [u for u in db.upserted if u[0] == "anime"][0]
        self.assertEqual(anime_ups[1][0]["anilist_id"], 99147)
        self.assertIn("anilist 99147", out)

    def test_tmdb_khong_khop_thi_khong_ghi_gi(self):
        db = FakeDB([ROW])
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(None, 0.31)), \
             redirect_stdout(buf):
            n = ingest_main.job_alias(db)
        self.assertEqual(n, 0)
        self.assertEqual(db.upserted, [])
        self.assertIn("TMDB không khớp", buf.getvalue())

    def test_anilist_khong_co_thi_bao_ro(self):
        db = FakeDB([ROW])
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(TMDB_HIT, 0.9)), \
             patch.object(tmdb, "fetch_detail", return_value=DETAIL), \
             patch.object(ingest_main.anilist, "search_media", return_value=[]), \
             redirect_stdout(buf):
            n = ingest_main.job_alias(db)
        self.assertEqual(n, 0)
        self.assertIn("AniList", buf.getvalue())

    def test_thieu_key_tmdb_thi_bo_qua_khong_no(self):
        db = FakeDB([ROW])
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=False), \
             redirect_stdout(buf):
            n = ingest_main.job_alias(db)
        self.assertEqual(n, 0)
        self.assertIn("TMDB_API_KEY", buf.getvalue())

    def test_khong_co_ten_nao(self):
        db = FakeDB([])
        n, out = self._run(db)
        self.assertEqual(n, 0)
        self.assertIn("trống", out)


class TestAliasKhongKemMua(unittest.TestCase):
    """Tên không kèm mùa phải gắn vào entry ĐẦU của thương hiệu, không phải mùa
    đang ghép — vì Muse đánh số tập cộng dồn (Tập 50 = mùa 3)."""

    ROW3 = {"series_name": "Lúc đó tôi đã chuyển sinh thành Slime S3",
            "videos": 24, "max_episode": 72}
    GOC = {"id": 39535, "episodes": 24, "format": "TV",
           "title": {"romaji": "Tensei Shitara Slime Datta Ken"}}
    S3 = {"id": 156822, "episodes": 24, "format": "TV",
          "title": {"romaji": "Tensei Shitara Slime Datta Ken 3rd Season"}}

    def test_tap_cong_don_khong_lam_mat_mua(self):
        """max_episode 72 (cộng dồn) không được làm job K bỏ entry 24 tập."""
        db = FakeDB([self.ROW3])
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(TMDB_HIT, 0.9)), \
             patch.object(tmdb, "fetch_detail", return_value=DETAIL), \
             patch.object(ingest_main.anilist, "search_media", return_value=[self.S3]), \
             patch.object(ingest_main.franchise, "goc", return_value=self.GOC), \
             patch.object(ingest_main.anilist, "media", return_value=self.GOC), \
             patch.object(ingest_main.franchise, "phu_hop",
                          return_value=(True, "cộng dồn qua mùa (tập 72 → tập 24 của mùa này)")), \
             redirect_stdout(buf):
            n = ingest_main.job_alias(db)
        self.assertEqual(n, 2, buf.getvalue())
        self.assertIn("cộng dồn", buf.getvalue())

    def test_ten_goc_va_ten_khong_mua_vao_hai_bo(self):
        db = FakeDB([self.ROW3])
        buf = io.StringIO()
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(TMDB_HIT, 0.9)), \
             patch.object(tmdb, "fetch_detail", return_value=DETAIL), \
             patch.object(ingest_main.anilist, "search_media", return_value=[self.S3]), \
             patch.object(ingest_main.franchise, "goc", return_value=self.GOC), \
             patch.object(ingest_main.anilist, "media", return_value=self.GOC), \
             patch.object(ingest_main.franchise, "phu_hop", return_value=(True, "ok")), \
             redirect_stdout(buf):
            n = ingest_main.job_alias(db)
        self.assertEqual(n, 2, buf.getvalue())
        alias_ups = [u for u in db.upserted if u[0] == "anime_alias"][0]
        theo_alias = {r["alias"]: r["anime_id"] for r in alias_ups[1]}
        # tên có mùa → giữ ở entry mùa 3 (id 77 giả lập cho cả hai lần upsert)
        self.assertIn("Lúc đó tôi đã chuyển sinh thành Slime S3", theo_alias)

    def test_don_alias_trung_tren_bo_khac(self):
        db = FakeDB([self.ROW3])
        da_xoa = []
        db.delete = lambda table, filters: da_xoa.append((table, filters)) or 1
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "find_vietnamese", return_value=(TMDB_HIT, 0.9)), \
             patch.object(tmdb, "fetch_detail", return_value=DETAIL), \
             patch.object(ingest_main.anilist, "search_media", return_value=[self.S3]), \
             patch.object(ingest_main.franchise, "goc", return_value=self.GOC), \
             patch.object(ingest_main.anilist, "media", return_value=self.GOC), \
             patch.object(ingest_main.franchise, "phu_hop", return_value=(True, "ok")), \
             redirect_stdout(io.StringIO()):
            ingest_main.job_alias(db)
        self.assertTrue(any(t == "anime_alias" and "neq." in str(f.get("anime_id"))
                            for t, f in da_xoa),
                        "phải xoá alias cùng tên đang trỏ về bộ khác")


class TestChiMucDungAlias(unittest.TestCase):
    """Chỉ mục tên phải đọc cả `anime_alias` → video tiếng Việt ghép được."""

    def test_alias_trong_db_duoc_dung(self):
        class DB(FakeDB):
            def select_all(self, table, query, **kw):
                if table == "anime":
                    return [{"id": 5, "anilist_id": 16498, "slug": "shingeki",
                             "title_romaji": "Shingeki no Kyojin", "title_vi": None,
                             "title_english": None, "title_native": None,
                             "episodes_total": 25, "popularity": 9, "format": "TV",
                             "year": 2013}]
                if table == "anime_alias":
                    return [{"anime_id": 5, "alias": "Đại chiến người Khổng Lồ",
                             "alias_key": "đại chiến người khổng lồ"}]
                return []

        idx = ingest_main._chi_muc_ten(DB())
        self.assertIn("đại chiến người khổng lồ", idx)
        e, _ = ingest_main._tra_chi_muc(idx, "Đại chiến người Khổng Lồ",
                                        "Đại chiến người Khổng Lồ", None, 3)
        self.assertEqual(e["anime_id"], 5)

    def test_bang_alias_chua_co_thi_bo_qua(self):
        class DB(FakeDB):
            def select_all(self, table, query, **kw):
                if table == "anime_alias":
                    raise RuntimeError("relation does not exist")
                return []

        self.assertEqual(ingest_main._chi_muc_ten(DB()), {})


class TestSeasonFromVn(unittest.TestCase):

    def test_cac_kieu_viet_mua(self):
        cases = {"Đại chiến người Khổng Lồ S1": 1,
                 "Lúc đó tôi đã chuyển sinh thành Slime Season 4": 4,
                 "Ace of the Diamond act II - Mùa 2": 2,
                 "Thất hình đại tội": None}
        for name, want in cases.items():
            self.assertEqual(youtube.season_from_vn(name), want, name)

    def test_bo_mua_giu_dau_hai_cham(self):
        self.assertEqual(youtube.base_from_vn(
            "Re:Zero - Bắt đầu lại từ con số 0 tại thế giới khác S4"),
            "Re:Zero - Bắt đầu lại từ con số 0 tại thế giới khác")


if __name__ == "__main__":
    unittest.main()
