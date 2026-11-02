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
        self.deleted = []
        self.thieu_tap = []
        self.logs = []
        self.dry = False

    select_extra = None

    def select(self, table, query):
        if self.queries is not None:
            self.queries.append((table, query))
        if "number=gt." in query and self.select_extra:
            return list(self.select_extra.get("episodes", []))
        if table == "anime":
            return list(self.anime_rows)
        if table == "anime_thieu_tap":
            return self.thieu_tap
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

    def delete(self, table, filters):
        self.deleted.append((table, filters))
        return 1

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


ROW = {
    "id": 5, "slug": "kusuriya", "anilist_id": 104578,
    "title_romaji": "Kusuriya no Hitorigoto",
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
    def _run(self, db, seasons=(1,), total=24, match=None, meta=None, eps=None,
             window=None):
        """Chạy job với TMDB giả. `match` cho phép mô phỏng không-khớp hoặc lỗi."""
        base_match = match or (lambda row: MATCH)

        def match_fn(row, accept=None):
            """Giả lập `match_anime(row, accept=…)` của code thật."""
            res = base_match(row)
            if accept is not None and res[0] is not None and not accept(res[0]):
                return None, 0.0, res[2]      # không ứng viên nào dùng được
            return res

        self.window_ids = []

        def fake_window(aid):
            self.window_ids.append(aid)
            return window or {}

        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(ingest_main.anilist, "airing_window",
                          side_effect=fake_window), \
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

    @staticmethod
    def _real_patches(db):
        """Bỏ qua patch mốc `tmdb_checked_at` (chỉ là tối ưu thời gian)."""
        return [p for p in db.patched if "tmdb_checked_at" not in p[2]]

    def test_dien_ten_va_tom_tat_tieng_viet(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db)
        self.assertEqual(len(self._real_patches(db)), 1)
        _, filters, values = self._real_patches(db)[0]
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

    def test_season_don_mua_tach_theo_nam(self):
        """Ca thật 02/11/2026 (`yozakura-san-chi-no-daisakusen-2nd-season`).

        TMDB trả một season **24 tập** cho series, AniList biết 12 tập và năm
        2026. `episodes_plausible` từ chối (24 > 12), `first_season_cut` từ chối
        (tên ghi mùa 2) → trước đây bỏ trắng. Nay tách theo NGÀY CHIẾU.
        """
        row = dict(ROW, episodes_total=12, year=2026,
                   title_english="Mission: Yozakura Family Season 2")
        eps, n = [], 1
        for y, c in ((2025, 12), (2026, 12)):
            for i in range(c):
                eps.append({"episode_number": n, "name": f"T{n}",
                            "air_date": f"{y}-01-{i % 28 + 1:02d}"})
                n += 1
        # TMDB thật: `seasons[].episode_count` báo 12 nhưng danh sách tập trả
        # về 24 (số liệu trong detail bị lệch). Vì vậy luật trừ offset (đòi
        # 24 ≈ 2×12) không chạy được, phải tách theo NĂM.
        meta = {1: {"episode_count": 12, "air_date": "2025-01-10"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1,), total=24, meta=meta, eps=eps)
        upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(upserts), 1, "phải tách được 12 tập của năm 2026")
        nums = [r["number"] for r in upserts[0][1]]
        self.assertEqual(nums, list(range(1, 13)))
        self.assertTrue(all(r["airing_at"].startswith("2026")
                            for r in upserts[0][1]),
                        "phải lấy đúng 12 tập của mùa 2 (năm 2026)")
        # Hai đường đều đúng cho ca này: "gộp mùa — trừ 12" (24 = 2×12, cắt nửa
        # sau) hoặc "tách theo năm 2026". Chỉ cấm việc ghi bừa.
        self.assertTrue("tách theo" in out or "gộp mùa" in out, out)

    def test_detail_bao_sai_so_tap_van_tach_duoc(self):
        """`seasons[].episode_count` = 12 nhưng danh sách tập trả 24.

        `merged_year_candidate` (dùng số trong detail) bỏ qua ca này, nên phải
        thử lại `split_season_offset` với SỐ TẬP THẬT đọc được (24 = 2×12).
        """
        row = dict(ROW, episodes_total=12, year=2026,
                   title_english="Mission: Yozakura Family Season 2")
        eps, n = [], 1
        for y, c in ((2025, 12), (2026, 12)):     # 24 tập, năm 2026 nằm SAU
            for i in range(c):
                eps.append({"episode_number": n, "name": f"T{n}",
                            "air_date": f"{y}-02-{i % 28 + 1:02d}"})
                n += 1
        meta = {1: {"episode_count": 12, "air_date": "2025-02-10"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1,), total=24, meta=meta, eps=eps)
        upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(upserts), 1, out)
        self.assertEqual([r["number"] for r in upserts[0][1]], list(range(1, 13)))
        self.assertTrue(all(r["airing_at"].startswith("2026")
                            for r in upserts[0][1]))

    def test_khong_tach_duoc_thi_van_khong_ghi(self):
        """Năm không có tập nào khớp số lượng → vẫn KHÔNG ghi (không ghép bừa)."""
        row = dict(ROW, episodes_total=12, year=2019)
        eps = [{"episode_number": i, "name": f"T{i}",
                "air_date": "2026-01-%02d" % (i % 28 + 1)} for i in range(1, 25)]
        meta = {1: {"episode_count": 12, "air_date": "2026-01-10"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1,), total=24, meta=meta, eps=eps)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])
        self.assertIn("không tách được", out)

    def test_mua_tmdb_dai_hon_thi_cat_theo_khoang_chieu(self):
        """Ca thật 02/11/2026: `yozakura-san-chi-no-daisakusen-2nd-season`.

        TMDB 216467 có mùa 1 (2024) + mùa 2 **24 tập** (12/04/2026 →), AniList
        tách 12 + 12 ("Part 2"). `first_season_cut` từ chối (tên ghi mùa 2),
        `split_season_offset` từ chối (TMDB có 2 mùa), luật theo NĂM cũng trượt
        (cả hai cour đều 2026) → trước đây bỏ trắng. Nay cắt bằng ngày chiếu
        của chính entry AniList.
        """
        import datetime as dt
        row = dict(ROW, episodes_total=12, year=2026,
                   title_english="Mission: Yozakura Family Season 2")
        eps, d = [], dt.date(2026, 4, 12)
        for i in range(24):
            eps.append({"episode_number": i + 1, "name": f"T{i+1}",
                        "air_date": (d + dt.timedelta(days=7 * i)).isoformat()})
        meta = {1: {"episode_count": 27, "air_date": "2024-04-07"},
                2: {"episode_count": 24, "air_date": "2026-04-12"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1, 2), total=51, meta=meta, eps=eps,
                           window={"from": dt.date(2026, 4, 12),
                                   "to": dt.date(2026, 6, 28)})
        upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(upserts), 1, out)
        self.assertEqual([r["number"] for r in upserts[0][1]], list(range(1, 13)))
        self.assertEqual(upserts[0][1][0]["title"], "T1")
        self.assertIn("theo khoảng chiếu", out)
        self.assertEqual(self.window_ids, [104578],
                         "phải tra AniList bằng anilist_id của ĐÚNG bộ đó")
        # không có tập nào nằm ngoài khoảng chiếu để dọn
        deletes = [d for d in db.deleted if d[0] == "episodes"]
        dates = [f for _, f in deletes]
        self.assertTrue(all("lt.2026-01-12" in f.get("airing_at", "")
                            or "gt.2026-09-26" in f.get("airing_at", "")
                            for f in dates), dates)

    def test_tap_cu_sai_nam_thi_xu_ly_lai_va_don(self):
        """Ca thật 02/11/2026: `tensei-kizoku-…-3rd-season` (2026) đang có **36
        tập** lấy từ TMDB season gộp (bắt đầu 07/04/2024) → tập của mùa 1+2 nằm
        trong mùa 3. Job cũ thấy "đã có tập" nên bỏ qua vĩnh viễn.
        """
        import datetime as dt
        row = dict(ROW, episodes_total=36, year=2026,
                   title_english="As a Reincarnated Aristocrat… Season 3")
        # TMDB: MỘT season 36 tập, 12 tập/năm 2024 · 2024 · 2026
        eps, n = [], 1
        for start, count in ((dt.date(2024, 4, 7), 12),
                             (dt.date(2024, 10, 6), 12),
                             (dt.date(2026, 10, 4), 12)):
            for i in range(count):
                eps.append({"episode_number": n, "name": f"T{n}",
                            "air_date": (start + dt.timedelta(days=7 * i)).isoformat()})
                n += 1
        meta = {1: {"episode_count": 36, "air_date": "2024-04-07"}}
        db = FakeDB([row], existing_episodes={5: [
            {"number": 1, "airing_at": "2024-04-07T00:00:00+00:00"}]})
        _, out = self._run(db, seasons=(1,), total=36, meta=meta, eps=eps,
                           window={"from": dt.date(2026, 10, 4), "to": None})
        upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(upserts), 1, out)
        self.assertEqual([r["number"] for r in upserts[0][1]], list(range(1, 13)))
        self.assertTrue(all(r["airing_at"].startswith("2026")
                            for r in upserts[0][1]))
        # dọn tập cũ nằm trước khoảng chiếu (chừa 90 ngày)
        early = [f for t, f in db.deleted if t == "episodes" and "lt." in f.get("airing_at", "")]
        self.assertEqual(len(early), 1, db.deleted)
        self.assertIn("lt.2026-07-06", early[0]["airing_at"])

    def test_don_tap_trung_sau_khi_danh_so_lai(self):
        """Ca thật 02/11/2026: `tensei-kizoku-…-3rd-season` có 1..12 (đúng) và
        25..36 (cùng ngày chiếu) → trang chi tiết hiện 24 tập trong khi chỉ có 12
        tập thật. Phải xoá bản trùng, KHÔNG đụng tập tương lai khác ngày.
        """
        import datetime as dt
        row = dict(ROW, episodes_total=36, year=2026,
                   title_english="As a Reincarnated Aristocrat… Season 3")
        start = dt.date(2026, 9, 27)
        eps = [{"episode_number": i + 1, "name": None,
                "air_date": (start + dt.timedelta(days=7 * i)).isoformat()}
               for i in range(12)]
        meta = {1: {"episode_count": 36, "air_date": "2026-09-27"}}
        # bảng episodes hiện có: 1 bản trùng (số 25, cùng ngày) + 1 tập tương lai
        # tập cũ bắt đầu từ 2024 (dữ liệu season gộp) ⇒ job phải xử lý lại
        db = FakeDB([row], existing_episodes={5: [
            {"number": 1, "airing_at": "2024-04-07T00:00:00+00:00"}]})
        db.select_extra = {"episodes": [
            {"id": 501, "number": 25, "airing_at": "2026-09-27T00:00:00+00:00"},
            {"id": 502, "number": 36, "airing_at": "2027-06-06T00:00:00+00:00"},
        ]}
        _, out = self._run(db, seasons=(1,), total=36, meta=meta, eps=eps,
                           window={"from": start, "to": None})
        self.assertIn("dọn 1 tập trùng", out)
        removed = [f.get("id") for t, f in db.deleted if t == "episodes"]
        self.assertIn(501, removed, "phải xoá theo KHOÁ CHÍNH id")
        self.assertNotIn(502, removed, "tập tương lai khác ngày chiếu phải giữ")

    def test_view_bao_tap_trung_thi_xu_ly_lai_du_da_co_tap(self):
        """Ca thật 02/11/2026: `tensei-kizoku-…-3rd-season` có 12 tập đúng +
        12 dòng trùng (số 25..36). Trước đây job thấy "đã có tập" nên bỏ qua
        vĩnh viễn, view cũng không bắt vì bộ này KHÔNG 0 tập.
        """
        import datetime as dt
        row = dict(ROW, episodes_total=36, year=2026,
                   title_english="As a Reincarnated Aristocrat… Season 3")
        start = dt.date(2026, 9, 27)
        eps = [{"episode_number": i + 1, "name": None,
                "air_date": (start + dt.timedelta(days=7 * i)).isoformat()}
               for i in range(12)]
        meta = {1: {"episode_count": 36, "air_date": "2026-09-27"}}
        db = FakeDB([], existing_episodes={5: [
            {"number": 1, "airing_at": "2026-09-27T00:00:00+00:00"}]})
        db.thieu_tap = [dict(row, tmdb_checked_at=None)]   # view báo "sai"
        db.select_extra = {"episodes": [
            {"id": 501, "number": 25,
             "airing_at": "2026-09-27T00:00:00+00:00"}]}
        _, out = self._run(db, seasons=(1,), total=36, meta=meta, eps=eps,
                           window={"from": start, "to": None})
        self.assertIn("danh sách tập cần sửa", out)
        self.assertIn("dọn 1 tập trùng", out)
        removed = [f.get("id") for t, f in db.deleted if t == "episodes"]
        self.assertIn(501, removed)

    def test_khong_co_ngay_chieu_anilist_thi_bao_ro(self):
        """Không đọc được ngày chiếu → KHÔNG ghi, và nói rõ vì sao (không im)."""
        import datetime as dt
        row = dict(ROW, episodes_total=12, year=2026,
                   title_english="Mission: Yozakura Family Season 2")
        eps = [{"episode_number": i + 1, "name": f"T{i+1}",
                "air_date": (dt.date(2026, 4, 12) + dt.timedelta(days=7 * i)).isoformat()}
               for i in range(24)]
        meta = {1: {"episode_count": 27, "air_date": "2024-04-07"},
                2: {"episode_count": 24, "air_date": "2026-04-12"}}
        db = FakeDB([row])
        _, out = self._run(db, seasons=(1, 2), total=51, meta=meta, eps=eps,
                           window={})
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])
        self.assertIn("KHÔNG hợp", out)
        self.assertIn("không có ngày chiếu AniList", out,
                      "phải nói rõ luật bị bỏ qua, không im lặng")

    def test_cot_anilist_id_phai_duoc_select(self):
        """Lỗi thật 02/11/2026: `TMDB_COLS` thiếu `anilist_id` ⇒ `airing_window`
        luôn trả {} ⇒ mọi luật "cắt theo khoảng chiếu" im lặng không chạy, job
        vẫn báo thành công. Test này chặn tái diễn.
        """
        for col in ("id", "anilist_id", "year", "episodes_total", "tmdb_id",
                    "tmdb_checked_at"):
            self.assertIn(col, ingest_main.TMDB_COLS)
        # và id đó phải được dùng thật: kiểm ở ca cắt theo khoảng chiếu
        # (test_mua_tmdb_dai_hon_thi_cat_theo_khoang_chieu).

    def test_view_thieu_tap_duoc_them_vao_hang_doi(self):
        """Bộ đã có tên VI + episodes_total nhưng 0 tập không nằm trong 2 query
        cũ → phải được lấy từ view `anime_thieu_tap` mới thử lại được."""
        db = FakeDB([])
        db.thieu_tap = [dict(ROW, id=77, slug="thieu-tap",
                             tmdb_checked_at=None)]
        n, out = self._run(db, window={})
        self.assertIn("danh sách tập cần sửa", out)
        touched = ([f.get("id") for _, f, _ in self._real_patches(db)]
                   + [r.get("anime_id") for t, rows in db.upserted if t == "episodes"
                      for r in rows])
        self.assertIn(77, touched, "bộ 0 tập phải được xử lý thật, không chỉ nằm "
                                   "trong danh sách")

    def test_khong_match_thi_khong_ghi_gi(self):
        db = FakeDB([dict(ROW)])
        n, out = self._run(db, match=lambda row: (None, 0.0, "search[x]"))
        self.assertEqual(self._real_patches(db), [],
                         "không match được → không ghi dữ liệu gì")
        self.assertEqual(db.upserted, [])
        # vẫn ĐÁNH DẤU đã hỏi TMDB để lần sau không quét lại ngay
        self.assertEqual(len(db.patched), 1)
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
        self.assertEqual(len(self._real_patches(db)), 1)   # bộ 6 vẫn được xử lý
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

    def test_da_du_tap_thi_khong_lay_them(self):
        """ĐỦ tổng số tập rồi thì enrich không đụng lại (khỏi tốn request)."""
        db = FakeDB([dict(ROW, episodes_total=12)],
                    existing_episodes={5: [{"number": n} for n in range(1, 13)]})
        self._run(db)
        self.assertEqual([u for u in db.upserted if u[0] == "episodes"], [])

    def test_thieu_tap_thi_enrich_van_lap(self):
        """HỒI QUY 02/11/2026 — lỗi làm `fairy-tail` kẹt 114/175.

        Điều kiện cũ chỉ đi lấy tập khi bảng episodes TRỐNG. Bộ đã có *một phần*
        tập (114/175) thì bị bỏ qua vĩnh viễn: `tmdb --force` chạy xong, ghi
        mốc `tmdb_checked_at` mới, `ingest_runs` báo 220 dòng — nhưng bảng
        `episodes` của bộ KHÔNG đổi một dòng nào.
        """
        db = FakeDB([dict(ROW, episodes_total=4)],   # ROW: year 2023, 4 tập
                    existing_episodes={5: [{"number": 1, "airing_at": "2023-10-01"}]})
        self._run(db)
        ups = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(ups), 1, "1/4 tập ⇒ vẫn phải đi lấy phần thiếu")
        self.assertIn(2, [r["number"] for r in ups[0][1]])

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


class TestLoiGhiHoSoKhongChanDanhSachTap(unittest.TestCase):
    """Ca thật 02/11/2026: 13 bộ bị 409 `anime_tmdb_id_key` khi ghi hồ sơ, và vì
    `DB.patch` ném lỗi nên job bỏ luôn phần danh sách tập của chính bộ đó.

    Nay lỗi ghi hồ sơ chỉ được ghi nhận; danh sách tập vẫn phải được lấy.
    """

    def test_patch_hong_van_ghi_tap(self):
        from ingest import main as m
        from ingest import tmdb as t

        class DB:
            dry = False
            def __init__(self):
                self.upserts, self.patches = [], []
            def select(self, table, query):
                if table == "anime":
                    return self.select_all("anime", query)
                return []          # bảng episodes: chưa có tập nào
            def select_all(self, table, query, page_size=1000, max_rows=200000):
                return [{"id": 7, "slug": "x", "title_romaji": "X S2",
                         "title_english": "X Season 2", "title_native": None,
                         "title_vi": None, "synopsis_vi": None, "year": 2019,
                         "episodes_total": 12, "tmdb_id": None}]
            def patch(self, table, filters, values):
                raise RuntimeError('patch anime lỗi 409: duplicate key')
            def upsert(self, table, rows, on_conflict=None,
                       fallback_per_row=False):
                self.upserts.append((table, rows))
                return list(rows)
            def log_ingest(self, *a, **k):
                pass

        detail = {"id": 99, "name": "X", "seasons": [
            {"season_number": 1, "episode_count": 12, "air_date": "2015-01-01"},
            {"season_number": 2, "episode_count": 12, "air_date": "2019-01-01"}]}
        season = {"episodes": [
            {"episode_number": i, "air_date": "2019-01-0%d" % (i % 9 + 1),
             "name": f"Episode {i}"} for i in range(1, 13)]}

        db = DB()
        with patch.object(t, "is_configured", return_value=True), \
                patch.object(t, "match_anime", return_value=(
                    {"id": 99, "name": "X"}, 0.95, "search[X]")), \
                patch.object(t, "fetch_detail", return_value=detail), \
                patch.object(t, "fetch_season", return_value=season), \
                patch.object(t, "extract_vietnamese", return_value=(None, None)), \
                patch.object(t.time, "sleep"):
            m.job_tmdb(db, limit=1)

        tables = [u[0] for u in db.upserts]
        self.assertIn("episodes", tables,
                      "409 khi ghi hồ sơ KHÔNG được chặn danh sách tập")
        eps = next(rows for name, rows in db.upserts if name == "episodes")
        self.assertEqual([e["number"] for e in eps], list(range(1, 13)))


class TestThuUngVienKeTiepTrongJob(unittest.TestCase):
    """Ca thật 02/11/2026 (`kusuriya-no-hitorigoto-2nd-season`).

    TMDB trả 2 series cho cùng một bộ; series điểm cao nhất **chỉ có mùa 1**,
    trong khi entry AniList là **mùa 2**. Trước đây job lấy series đầu, không
    chọn được mùa → bộ 0 tập. Nay phải thử ứng viên kế tiếp.
    """

    def test_dung_series_thu_hai_khi_series_dau_thieu_mua(self):
        row = dict(ROW, slug="kusuriya-2nd", year=2025, episodes_total=24,
                   title_english="The Apothecary Diaries Season 2")
        db = FakeDB([row])

        first = {"id": 220542, "name": "The Apothecary Diaries Season 2"}
        second = {"id": 333686, "name": "The Apothecary Diaries"}

        def fake_match(r, accept=None):
            for cand in (first, second):
                if accept is None or accept(cand):
                    return cand, 0.9, "search[x]"
            return None, 0.0, "search[x]"

        def fake_detail(tv_id):
            if tv_id == 220542:      # chỉ có mùa 1 (12 tập) → không dùng được cho mùa 2 (24 tập)
                return {"id": tv_id, "seasons": [
                    {"season_number": 1, "episode_count": 12,
                     "air_date": "2023-10-22"}], "translations": {"translations": []},
                    "alternative_titles": {"results": []}}
            return {"id": tv_id, "seasons": [
                {"season_number": 1, "episode_count": 24, "air_date": "2023-10-22"},
                {"season_number": 2, "episode_count": 24, "air_date": "2025-01-10"}],
                "translations": {"translations": []},
                "alternative_titles": {"results": []}}

        eps = [{"episode_number": i, "name": f"T{i}",
                "air_date": "2025-01-%02d" % (i % 28 + 1)} for i in range(1, 25)]
        with patch.object(tmdb, "is_configured", return_value=True), \
                patch.object(tmdb, "match_anime", side_effect=fake_match), \
                patch.object(tmdb, "fetch_detail", side_effect=fake_detail), \
                patch.object(tmdb, "fetch_season",
                             side_effect=lambda tv, n: {"episodes": eps}), \
                patch.object(tmdb.time, "sleep"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ingest_main.job_tmdb(db)

        eps_upserts = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(eps_upserts), 1, "phải lấy được tập từ series thứ hai")
        self.assertEqual(len(eps_upserts[0][1]), 24)
        self.assertEqual(db.patched[0][2].get("tmdb_id"), 333686)


class TestChiDinhSlug(unittest.TestCase):
    """`tmdb --only-slug kusuriya`: sửa đúng một bộ NGAY.

    Job D bỏ qua bộ vừa hỏi TMDB trong 1–7 ngày (`tmdb_checked_at`) để không
    quét lại 792 giây cho 0 bản ghi. Nhưng khi người chạy vừa vá dữ liệu của
    một bộ cụ thể thì phải xử lý được ngay, không phải chờ hết hạn — nếu không
    cách duy nhất là sửa tay trong DB.
    """

    def _run(self, db, **kw):
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "match_anime", return_value=MATCH), \
             patch.object(tmdb, "fetch_detail",
                          side_effect=lambda tv: _detail(total=24)), \
             patch.object(tmdb, "fetch_season", return_value={"episodes": []}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                n = ingest_main.job_tmdb(db, **kw)
        return n, buf.getvalue()

    def test_bo_qua_loc_da_hoi_gan_day(self):
        import datetime as dt
        vua_hoi = dt.datetime.now(dt.timezone.utc).isoformat()
        db = FakeDB([dict(ROW, tmdb_checked_at=vua_hoi)])
        db.queries = []
        _, out = self._run(db, only_slug="kusuriya")
        q = " ".join(qq for t, qq in db.queries if t == "anime")
        self.assertIn("slug=in.(kusuriya)", q)
        self.assertNotIn("title_vi.is.null", q)
        real = [p for p in db.patched if "tmdb_checked_at" not in p[2]]
        self.assertEqual(len(real), 1, "vừa hỏi TMDB hôm nay vẫn phải xử lý")
        self.assertIn("chỉ 1 slug", out)

    def test_nhieu_slug_cach_nhau_dau_phay(self):
        db = FakeDB([dict(ROW), dict(ROW, id=6, slug="khac")])
        db.queries = []
        _, out = self._run(db, only_slug="kusuriya, khac")
        q = " ".join(qq for t, qq in db.queries if t == "anime")
        self.assertIn("slug=in.(kusuriya,khac)", q)
        self.assertIn("chỉ 2 slug", out)

    def test_slug_khong_ton_tai_thi_no(self):
        db = FakeDB([dict(ROW)])          # DB chỉ có "kusuriya"
        with self.assertRaises(RuntimeError) as ctx:
            self._run(db, only_slug="khong-co-that")
        self.assertIn("khong-co-that", str(ctx.exception))
        self.assertIn("add --anilist", str(ctx.exception))
        self.assertEqual(db.patched, [], "không được ghi gì khi slug sai")

    def test_cli_truyen_co_xuong_job(self):
        db = FakeDB([dict(ROW)])
        calls = []

        def fake(db_, limit, with_episodes=True, refresh=False, only_slug="",
                 force=False):
            calls.append(only_slug)
            return 0

        with patch.object(ingest_main, "job_tmdb", side_effect=fake), \
             patch.object(ingest_main.dbmod, "DB", return_value=db), \
             redirect_stdout(io.StringIO()):
            ingest_main.main(["tmdb", "--only-slug", "kusuriya"])
        self.assertEqual(calls, ["kusuriya"], "--only-slug phải tới được job D")

    def test_mac_dinh_van_loc_da_hoi(self):
        """Không có --only-slug → giữ nguyên hành vi cũ (bỏ qua bộ vừa hỏi)."""
        import datetime as dt
        vua_hoi = dt.datetime.now(dt.timezone.utc).isoformat()
        db = FakeDB([dict(ROW, tmdb_checked_at=vua_hoi)])
        self._run(db)
        self.assertEqual(db.patched, [])


class TestForceQuaHan(unittest.TestCase):
    """`tmdb --force`: chạy lại ngay sau khi SỬA CÁCH ĐỌC TMDB.

    Bản vá `title_vi` (02/11/2026) chỉ có tác dụng nếu job ghé lại các bộ đã hỏi
    TMDB hôm nay; không có `--force` thì phải chờ 7 ngày.
    """

    def _run(self, db, **kw):
        with patch.object(tmdb, "is_configured", return_value=True), \
             patch.object(tmdb, "match_anime", return_value=MATCH), \
             patch.object(tmdb, "fetch_detail",
                          side_effect=lambda tv: _detail(total=24)), \
             patch.object(tmdb, "fetch_season", return_value={"episodes": []}), \
             redirect_stdout(io.StringIO()) as buf:
            n = ingest_main.job_tmdb(db, **kw)
        return n, buf.getvalue()

    def test_force_bo_qua_han_da_hoi(self):
        import datetime as dt
        vua_hoi = dt.datetime.now(dt.timezone.utc).isoformat()
        db = FakeDB([dict(ROW, tmdb_checked_at=vua_hoi)])
        _, out = self._run(db, force=True)
        real = [p for p in db.patched if "tmdb_checked_at" not in p[2]]
        self.assertEqual(len(real), 1, "force phải xử lý dù vừa hỏi hôm nay")
        self.assertIn("bỏ hạn", out)

    def test_force_dien_lai_title_vi_khi_con_trong(self):
        """Cột `title_vi` rỗng vẫn được ghi dù `synopsis_vi` đã có."""
        db = FakeDB([dict(ROW, synopsis_vi="đã có", tmdb_checked_at=None)])
        self._run(db, force=True)
        real = [p for p in db.patched if "tmdb_checked_at" not in p[2]]
        self.assertEqual(real[0][2].get("title_vi"), "Dược Sư Tự Sự")


class TestGhepMuaTrongJob(unittest.TestCase):
    """Job D phải ghép nhiều mùa TMDB khi một entry AniList trải qua nhiều mùa.

    Không có bước này thì `fairy-tail` (AniList 175 tập, TMDB mùa 1 = 48 tập) chỉ
    nhận 48 tập rồi dừng vĩnh viễn.
    """

    def test_ghep_2_mua_va_danh_so_lien_tuc(self):
        db = FakeDB([dict(ROW, episodes_total=4)])
        meta = {1: {"episode_count": 2}, 2: {"episode_count": 2}}
        n, out = TestJobTmdb()._run(db, seasons=(1, 2), total=4, meta=meta)
        ups = [u for u in db.upserted if u[0] == "episodes"]
        self.assertEqual(len(ups), 1)
        self.assertEqual([r["number"] for r in ups[0][1]], [1, 2, 3, 4])
        self.assertIn("ghép 2 mùa", out)
