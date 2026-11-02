"""Test job D (`python3 -m ingest.main tmdb`) với DB giả + TMDB giả.

Khoá các hành vi quan trọng:
  · không match được → KHÔNG ghi gì (không đoán bừa)
  · nhiều mùa → không tạo episodes (tránh gán sai số tập)
  · chưa có episodes_total + đúng 1 mùa → tạo episodes
  · lỗi cấu hình TMDB (TmdbError) → NỔ, không bị nuốt
  · thiếu key → RuntimeError kèm hướng dẫn
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import tmdb


class FakeDB:
    queries = None

    def __init__(self, anime_rows, existing_episodes=None):
        self.anime_rows = anime_rows
        self.existing_episodes = existing_episodes or {}
        self.patched = []
        self.upserted = []
        self.logs = []
        self.dry = False

    def select(self, table, query):
        if self.queries is not None:
            self.queries.append((table, query))
        if table == "anime":
            return list(self.anime_rows)
        if table == "episodes":
            # query chứa anime_id=eq.<id>
            for aid, eps in self.existing_episodes.items():
                if f"anime_id=eq.{aid}" in query:
                    return eps
            return []
        return []

    def patch(self, table, filters, values):
        self.patched.append((table, filters, values))
        return 1

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        return list(rows)

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {
    "id": 5, "slug": "kusuriya", "title_romaji": "Kusuriya no Hitorigoto",
    "title_english": "The Apothecary Diaries", "title_native": None,
    "title_vi": None, "synopsis_vi": None, "year": 2023,
    "episodes_total": None, "tmdb_id": None,
}

MATCH = ({"id": 12345, "name": "Kusuriya no Hitorigoto"}, 0.93, "search[Kusuriya]")


def _detail(seasons=(1,), total=24, meta=None):
    """`meta` cho phép khai báo episode_count/air_date từng mùa (mô phỏng TMDB thật)."""
    meta = meta or {}
    return {
        "id": 12345, "name": "Kusuriya no Hitorigoto", "number_of_episodes": total,
        "seasons": [dict({"season_number": s}, **meta.get(s, {}))
                    for s in (0,) + tuple(seasons)],
        "translations": {"translations": [
            {"iso_639_1": "vi", "data": {"name": "Dược Sư Tự Sự", "overview": "Maomao."}}]},
        "alternative_titles": {"results": []},
    }


class TestJobTmdb(unittest.TestCase):
    def _run(self, db, seasons=(1,), total=24, match=None, meta=None, eps=None):
        """Chạy job với TMDB giả. `match` cho phép mô phỏng không-khớp hoặc lỗi."""
        match_fn = match or (lambda row: MATCH)
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "match_anime", side_effect=match_fn), \
             patch.object(tmdb, "fetch_detail",
                          side_effect=lambda tv: _detail(seasons=seasons, total=total,
                                                         meta=meta)), \
             patch.object(tmdb, "fetch_season", side_effect=lambda tv, n: {"episodes": eps or [
                 {"episode_number": 1, "name": "Tập 1", "air_date": "2023-10-01"},
                 {"episode_number": 2, "name": "Tập 2", "air_date": "2023-10-08"},
             ]}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_tmdb(db)
            return n, buf.getvalue()

    def test_dien_ten_va_tom_tat_tieng_viet(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db)
        self.assertEqual(len(db.patched), 1)
        _, filters, values = db.patched[0]
        self.assertEqual(filters, {"id": 5})
        self.assertEqual(values["title_vi"], "Dược Sư Tự Sự")
        self.assertEqual(values["synopsis_vi"], "Maomao.")
        self.assertGreater(n, 0)
        self.assertIn("Dược Sư Tự Sự", out)

    def test_tao_episodes_khi_dung_mot_mua(self):
        db = FakeDB([dict(ROW)])
        self._run(db)
        eps_upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(eps_upserts), 1)
        rows = eps_upserts[0][1]
        self.assertEqual([r["number"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["anime_id"], 5)

    def test_nhieu_mua_thi_khong_tao_episodes(self):
        db = FakeDB([dict(ROW)])
        self._run(db, seasons=(1, 2), total=48)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])
        values = db.patched[0][2]
        self.assertNotIn("episodes_total", values)   # không lấy số tập của 2 mùa

    def test_da_co_episodes_thi_khong_tao_them(self):
        db = FakeDB([dict(ROW)], existing_episodes={5: [{"number": 1}]})
        self._run(db)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])

    def test_da_co_episodes_total_van_lay_danh_sach_tap(self):
        """HỒI QUY: bộ đã có `episodes_total` từ AniList từng KHÔNG BAO GIỜ có tập.

        Takagi-san (12 tập, tmdb_id 75865) là ca thật: trang chi tiết hiện
        "12 tập" ở tiêu đề nhưng chỉ có 6 tập từ link YouTube, vì điều kiện cũ
        đòi `episodes_total is null` mới đi lấy danh sách tập.
        """
        db = FakeDB([dict(ROW, episodes_total=24)])
        self._run(db)
        eps_upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(eps_upserts), 1, "phải lấy danh sách tập dù đã biết tổng")
        self.assertEqual([r["number"] for r in eps_upserts[0][1]], [1, 2])
        self.assertNotIn("episodes_total", db.patched[0][2])   # không ghi đè số đã có

    def test_nhieu_mua_chon_theo_nam_roi_lay_tap(self):
        """Takagi-san: 3 mùa đều 12 tập, entry AniList là mùa 1 (2018)."""
        row = dict(ROW, year=2018, episodes_total=12)
        meta = {1: {"episode_count": 12, "air_date": "2018-01-08"},
                2: {"episode_count": 12, "air_date": "2019-07-07"},
                3: {"episode_count": 12, "air_date": "2022-01-08"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1, 2, 3), total=36, meta=meta)
        self.assertEqual(len([u for u in db.upserted if u[0] == "episodes"]), 1)
        self.assertIn("mùa 1", out)
        self.assertIn("khớp năm 2018", out)

    def test_tmdb_nhieu_tap_hon_anilist_thi_khong_ghi(self):
        """Fool Night thật: AniList 3 tập, TMDB season trả 12 → không ghi, báo rõ."""
        row = dict(ROW, episodes_total=3)
        eps = [{"episode_number": i, "name": f"T{i}", "air_date": "2026-01-0%d" % (i % 9 + 1)}
               for i in range(1, 13)]
        db = FakeDB([row])
        _, out = self._run(db, eps=eps)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])
        self.assertIn("KHÔNG hợp với AniList", out)

    def test_khong_match_thi_khong_ghi_gi(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db, match=lambda row: (None, 0.0, "search[x]"))
        self.assertEqual(db.patched, [])
        self.assertEqual(db.upserted, [])
        self.assertEqual(n, 0)
        self.assertIn("không tìm được trên TMDB", out)

    def test_khong_ghi_de_ten_da_bien_tap(self):
        row = dict(ROW, title_vi="Tên biên tập tay", synopsis_vi="Tóm tắt tay")
        db = FakeDB([row])
        self._run(db)
        values = db.patched[0][2] if db.patched else {}
        self.assertNotIn("title_vi", values)
        self.assertNotIn("synopsis_vi", values)

    def test_loi_cau_hinh_tmdb_thi_no(self):
        db = FakeDB([dict(ROW)])

        def boom(row):
            raise tmdb.TmdbError("TMDB_API_KEY không hợp lệ (401)")

        with self.assertRaises(tmdb.TmdbError):
            self._run(db, match=boom)
        self.assertEqual(db.patched, [])

    def test_loi_mot_bo_khong_lam_chet_job(self):
        db = FakeDB([dict(ROW), dict(ROW, id=6)])

        def flaky(row):
            if row["id"] == 5:
                raise ValueError("dữ liệu TMDB lạ")
            return MATCH

        n, out = self._run(db, match=flaky)
        self.assertEqual(len(db.patched), 1)          # bộ 6 vẫn được xử lý
        self.assertIn("dữ liệu TMDB lạ", out)

    def test_thieu_key_thi_runtime_error_kem_huong_dan(self):
        db = FakeDB([dict(ROW)])
        with patch.object(tmdb, "is_configured", return_value=False):
            with self.assertRaises(RuntimeError) as ctx:
                with redirect_stdout(io.StringIO()):
                    ingest_main.job_tmdb(db)
        msg = str(ctx.exception)
        self.assertIn("TMDB_API_KEY", msg)
        self.assertIn("themoviedb.org", msg)

    def test_ghi_audit_ingest_runs(self):
        db = FakeDB([dict(ROW)])
        self._run(db)
        self.assertEqual(db.logs[-1][0], "tmdb")
        self.assertTrue(db.logs[-1][2])


class TestJobTmdbRefresh(unittest.TestCase):
    """`tmdb --refresh`: tập MỚI của bộ đang chiếu phải vào DB.

    Lỗi cũ: điều kiện `or=(title_vi.is.null,…)` + `if not have` khiến bộ đang chiếu
    đã có 2 tập thì KHÔNG BAO GIỜ nhận được tập 3 → "cập nhật thường xuyên" không
    hoạt động dù chạy job mỗi ngày.
    """

    def _run(self, db, seasons=(1,), total=12, meta=None, eps=None):
        return TestJobTmdb()._run(db, seasons=seasons, total=total, meta=meta, eps=eps)

    def test_chi_chon_bo_dang_chieu(self):
        db = FakeDB([dict(ROW)])
        db.queries = []
        with redirect_stdout(io.StringIO()):
            with patch.object(tmdb, "is_configured", return_value=True), \
                 patch.object(tmdb, "match_anime", return_value=MATCH), \
                 patch.object(tmdb, "fetch_detail",
                              side_effect=lambda tv: _detail(total=12)), \
                 patch.object(tmdb, "fetch_season", return_value={"episodes": []}):
                ingest_main.job_tmdb(db, refresh=True)
        q = " ".join(q for t, q in db.queries if t == "anime")
        self.assertIn("status=eq.RELEASING", q)
        self.assertNotIn("title_vi.is.null", q, "refresh không được lọc theo trường thiếu")

    def test_da_co_tap_van_lay_va_dem_tap_MOI(self):
        db = FakeDB([dict(ROW, episodes_total=12)],
                    existing_episodes={5: [{"number": 1}, {"number": 2}]})
        self._run(db)                       # chế độ enrich: có tập → bỏ qua
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])

        db2 = FakeDB([dict(ROW, episodes_total=12)],
                     existing_episodes={5: [{"number": 1}, {"number": 2}]})
        with redirect_stdout(io.StringIO()) as buf:
            with patch.object(tmdb, "is_configured", return_value=True), \
                 patch.object(tmdb, "match_anime", return_value=MATCH), \
                 patch.object(tmdb, "fetch_detail",
                              side_effect=lambda tv: _detail(total=12)), \
                 patch.object(tmdb, "fetch_season", return_value={"episodes": [
                     {"episode_number": 1, "name": "A", "air_date": "2023-10-01"},
                     {"episode_number": 2, "name": "B", "air_date": "2023-10-08"},
                     {"episode_number": 3, "name": "C", "air_date": "2023-10-15"},
                 ]}):
                ingest_main.job_tmdb(db2, refresh=True)
        ups = [u for u in db2.upserted if u[0] == "episodes"]
        self.assertEqual(len(ups), 1, "refresh phải upsert dù đã có tập")
        self.assertIn("1 tập MỚI", buf.getvalue())
        self.assertIn("tập 3", buf.getvalue())

    def test_log_ingest_ghi_job_refresh(self):
        db = FakeDB([dict(ROW)])
        with redirect_stdout(io.StringIO()):
            with patch.object(tmdb, "is_configured", return_value=True), \
                 patch.object(tmdb, "match_anime", return_value=MATCH), \
                 patch.object(tmdb, "fetch_detail",
                              side_effect=lambda tv: _detail(total=12)), \
                 patch.object(tmdb, "fetch_season", return_value={"episodes": []}):
                ingest_main.job_tmdb(db, refresh=True)
        self.assertEqual(db.logs[-1][1], "refresh")


if __name__ == "__main__":
    unittest.main()


class TestGoiYMuaTuTen(unittest.TestCase):
    """30 bộ đã chiếu xong mà 0 tập (đo 02/11/2026).

    AniList tách mỗi mùa thành entry riêng; TMDB gộp cả series. `pick_season` cũ
    chỉ dựa năm/số tập nên bó tay khi các mùa giống nhau → không lấy được tập.
    Nay job D đọc số mùa từ TÊN bộ rồi truyền xuống `pick_season`.
    """

    def _run(self, row, detail, season_eps=24):
        db = FakeDB([row])
        with patch.object(tmdb, "is_configured", return_value=True), \
                patch("ingest.tmdb.match_anime", return_value=MATCH), \
                patch("ingest.tmdb.fetch_detail", return_value=detail), \
                patch("ingest.tmdb.fetch_season",
                      return_value={"episodes": [
                          {"episode_number": n, "air_date": "2025-01-10",
                           "name": None} for n in range(1, season_eps + 1)]}), \
                redirect_stdout(io.StringIO()):
            ingest_main.job_tmdb(db, limit=1)
        eps = [r for t, rows in db.upserted if t == "episodes" for r in rows]
        return db, eps

    def test_mua_2_giong_mua_1_van_lay_duoc_tap(self):
        row = dict(ROW, slug="kusuriya-no-hitorigoto-2nd-season",
                   title_romaji="Kusuriya no Hitorigoto 2nd Season",
                   title_english=None, year=2025, episodes_total=24)
        detail = _detail(seasons=(1, 2), total=48, meta={
            1: {"episode_count": 24, "air_date": "2023-10-01"},
            2: {"episode_count": 24, "air_date": "2025-01-10"},
        })
        db, eps = self._run(row, detail)
        self.assertEqual(len(eps), 24, "phải lấy được tập của mùa 2")
        self.assertEqual(sorted(r["number"] for r in eps), list(range(1, 25)))

    def test_ten_ghi_mua_5_ma_tmdb_chi_co_2_thi_khong_ghi_tap(self):
        row = dict(ROW, slug="x-5th-season", title_romaji="X 5th Season",
                   title_english=None, year=2030, episodes_total=12)
        detail = _detail(seasons=(1, 2), total=24, meta={
            1: {"episode_count": 12, "air_date": "2020-01-01"},
            2: {"episode_count": 12, "air_date": "2021-01-01"},
        })
        db, eps = self._run(row, detail, season_eps=12)
        self.assertEqual(eps, [], "không được gán tập mùa khác khi tên ghi mùa 5")


class TestMatchSequelKhongBiLocNam(unittest.TestCase):
    """25 bộ FINISHED 0 tập vì `match_anime` lọc NĂM.

    AniList ghi năm của MÙA ("One Punch Man 2" → 2019), TMDB ghi năm MÙA 1
    (2015) → lệch 4 > YEAR_TOLERANCE 2 → loại sạch, không có tmdb_id, không tập.
    """

    def test_mua_2_khop_du_nam_lech(self):
        from ingest import tmdb as t
        row = {"title_romaji": "One Punch Man 2", "title_english": None,
               "title_native": None, "year": 2019}
        results = [{"id": 63926, "name": "One-Punch Man",
                    "original_name": "One Punch Man",
                    "first_air_date": "2015-09-20", "popularity": 80}]
        with patch.object(t, "_get", return_value={"results": results}), \
                patch.object(t.time, "sleep"):
            best, score, how = t.match_anime(row)
        self.assertIsNotNone(best, "mùa 2 phải khớp được TMDB")
        self.assertGreaterEqual(score, 0.8)
        self.assertIn("One Punch Man 2", how)

    def test_bo_khong_phai_mua_van_loc_nam(self):
        """Bộ thường (không ghi mùa) vẫn phải lọc năm — tránh nhầm bộ khác."""
        from ingest import tmdb as t
        row = {"title_romaji": "Naruto", "title_english": None,
               "title_native": None, "year": 2002}
        results = [{"id": 1, "name": "Naruto Shippuden",
                    "original_name": "Naruto Shippuden",
                    "first_air_date": "2007-02-15", "popularity": 90}]
        with patch.object(t, "_get", return_value={"results": results}), \
                patch.object(t.time, "sleep"):
            best, _, _ = t.match_anime(row)
        self.assertIsNone(best, "Naruto vs Naruto Shippuden: lệch 5 năm → phải loại")
