"""Test cho ingest/tmdb.py — phần làm giàu tiếng Việt (tên, tóm tắt, tập).

Toàn bộ dùng dữ liệu GIẢ (không gọi mạng): sandbox/CI không được gọi
api.themoviedb.org, và test phải chạy được khi không có TMDB_API_KEY.

Nguyên tắc được khoá bằng test ở đây: **thà thiếu còn hơn sai** — không đoán bừa,
không ghi đè dữ liệu người biên tập đã nhập, không lấy số tập của phim nhiều mùa.
"""
import datetime as dt
import unittest
from unittest.mock import patch

from ingest import config, tmdb


def _resp(status=200, body=None, text=""):
    class R:
        status_code = status
        def json(self_inner):
            return body if body is not None else {}
    r = R()
    r.status_code = status
    r.text = text
    return r


DETAIL = {
    "id": 12345,
    "name": "Kusuriya no Hitorigoto",
    "number_of_episodes": 24,
    "seasons": [{"season_number": 0}, {"season_number": 1}],
    "translations": {"translations": [
        {"iso_639_1": "ja", "data": {"name": "薬屋のひとりごと", "overview": "日本語"}},
        {"iso_639_1": "vi", "data": {"name": "Dược Sư Tự Sự",
                                     "overview": "Maomao sống trong khu kỹ viện."}},
    ]},
    "alternative_titles": {"results": [{"iso_3166_1": "VN", "title": "Dược Sư Tự Sự"}]},
}


class TestSoTen(unittest.TestCase):
    def test_norm_bo_mua_va_dau_cau(self):
        self.assertEqual(tmdb.norm("Kusuriya no Hitorigoto: 3rd Season!"),
                         tmdb.norm("kusuriya no hitorigoto"))

    def test_similarity(self):
        self.assertEqual(tmdb.similarity("Frieren", "frieren"), 1.0)
        self.assertGreater(tmdb.similarity("Sousou no Frieren", "Sousou no Frieren "), 0.9)
        self.assertLess(tmdb.similarity("Frieren", "Naruto"), 0.3)


class TestPickBest(unittest.TestCase):
    def test_chon_dung_bo_trong_nhieu_ket_qua(self):
        results = [
            {"id": 1, "name": "Naruto", "first_air_date": "2002-10-03", "popularity": 90},
            {"id": 2, "name": "Frieren: Beyond Journey's End",
             "first_air_date": "2023-09-29", "popularity": 80},
        ]
        best, score = tmdb.pick_best(results, ["Sousou no Frieren", "Frieren"], 2023)
        self.assertEqual(best["id"], 2)
        self.assertGreaterEqual(score, 0.8)

    def test_khac_nam_qua_xa_thi_bo(self):
        results = [{"id": 9, "name": "Frieren", "first_air_date": "1999-01-01", "popularity": 5}]
        best, score = tmdb.pick_best(results, ["Frieren"], 2023)
        self.assertIsNone(best)
        self.assertEqual(score, 0.0)

    def test_chi_kiem_ten_ngan_nam_trong_ten_dai_khi_dung_nam(self):
        """AniList 'Sousou no Frieren' vs TMDB 'Frieren: Beyond Journey's End'."""
        r = {"id": 7, "name": "Frieren: Beyond Journey's End",
             "first_air_date": "2023-09-29", "popularity": 80}
        best, score = tmdb.pick_best([r], ["Sousou no Frieren"], 2023)
        self.assertIsNotNone(best)
        self.assertGreaterEqual(score, 0.8)

    def test_khong_nham_naruto_voi_naruto_shippuden(self):
        """'Naruto' nằm trong 'Naruto Shippuden' nhưng khác năm → phải TỪ CHỐI."""
        r = {"id": 8, "name": "Naruto Shippuden",
             "first_air_date": "2007-02-15", "popularity": 90}
        best, _ = tmdb.pick_best([r], ["Naruto"], 2002)
        self.assertIsNone(best)

    def test_ten_khac_han_thi_khong_nhan(self):
        results = [{"id": 3, "name": "Totally Different Show",
                    "first_air_date": "2023-01-01", "popularity": 99}]
        best, _ = tmdb.pick_best(results, ["Sousou no Frieren"], 2023)
        self.assertIsNone(best)


class TestExtractVietnamese(unittest.TestCase):
    def test_lay_ban_dich_vi(self):
        t, o = tmdb.extract_vietnamese(DETAIL)
        self.assertEqual(t, "Dược Sư Tự Sự")
        self.assertEqual(o, "Maomao sống trong khu kỹ viện.")

    def test_ban_dich_vi_rong_thi_dung_ten_VN(self):
        d = {
            "name": "Kusuriya no Hitorigoto",
            "translations": {"translations": [
                {"iso_639_1": "vi", "data": {"name": "", "overview": ""}}]},
            "alternative_titles": {"results": [{"iso_3166_1": "VN", "title": "Dược Sư Tự Sự"}]},
        }
        t, o = tmdb.extract_vietnamese(d)
        self.assertEqual(t, "Dược Sư Tự Sự")
        self.assertIsNone(o)

    def test_ten_giong_het_ban_goc_thi_khong_coi_la_tieng_viet(self):
        d = {"name": "Frieren",
             "translations": {"translations": [
                 {"iso_639_1": "vi", "data": {"name": "Frieren", "overview": ""}}]}}
        t, o = tmdb.extract_vietnamese(d)
        self.assertIsNone(t)
        self.assertIsNone(o)


class TestBuildPatch(unittest.TestCase):
    ROW_EMPTY = {"id": 1, "title_vi": None, "synopsis_vi": None,
                 "episodes_total": None, "tmdb_id": None}

    def test_dien_khi_trong(self):
        p = tmdb.build_anime_patch(self.ROW_EMPTY, DETAIL, "Dược Sư Tự Sự", "Tóm tắt", True)
        self.assertEqual(p["title_vi"], "Dược Sư Tự Sự")
        self.assertEqual(p["synopsis_vi"], "Tóm tắt")
        self.assertEqual(p["tmdb_id"], 12345)
        self.assertEqual(p["episodes_total"], 24)

    def test_khong_ghi_de_du_lieu_da_co(self):
        row = {"id": 1, "title_vi": "Tên biên tập", "synopsis_vi": "Tóm tắt tay",
               "episodes_total": 12, "tmdb_id": 999}
        p = tmdb.build_anime_patch(row, DETAIL, "Tên TMDB", "Tóm tắt TMDB", True)
        self.assertEqual(p, {})

    def test_nhieu_mua_thi_khong_lay_episodes_total(self):
        p = tmdb.build_anime_patch(self.ROW_EMPTY, DETAIL, None, None, False)
        self.assertNotIn("episodes_total", p)
        self.assertEqual(p, {"tmdb_id": 12345})

    def test_gia_tri_none_khong_duoc_ghi(self):
        p = tmdb.build_anime_patch(self.ROW_EMPTY, {"id": 5}, None, None, True)
        self.assertNotIn("title_vi", p)
        self.assertNotIn("synopsis_vi", p)


class TestEpisodeRows(unittest.TestCase):
    SEASON = {"episodes": [
        {"episode_number": 2, "name": "Tập 2", "air_date": "2023-10-08"},
        {"episode_number": 1, "name": "Tập 1", "air_date": "2023-10-01"},
        {"episode_number": 3, "name": "", "air_date": None},        # chưa có ngày → bỏ
        {"episode_number": 0, "name": "Special", "air_date": "2023-09-30"},  # số 0 → bỏ
    ]}

    def test_loc_va_sap_xep(self):
        rows = tmdb.episode_rows(7, self.SEASON, single_season=True)
        self.assertEqual([r["number"] for r in rows], [1, 2])
        self.assertTrue(all(r["anime_id"] == 7 for r in rows))

    def test_airing_at_co_timezone_iso(self):
        row = tmdb.episode_rows(7, self.SEASON, True)[0]
        parsed = dt.datetime.fromisoformat(row["airing_at"])
        self.assertEqual(parsed.year, 2023)
        self.assertIsNotNone(parsed.tzinfo, "phải có timezone, nếu không Postgres hiểu sai")

    def test_nhieu_mua_thi_khong_tra_gi(self):
        self.assertEqual(tmdb.episode_rows(7, self.SEASON, single_season=False), [])

    def test_ten_rong_thanh_None(self):
        # "Tập 1" là placeholder (không phải tên thật) → None, xem TestCleanEpisodeTitle
        rows = tmdb.episode_rows(7, self.SEASON, True)
        self.assertIsNone(rows[0]["title"])

    def test_ten_that_duoc_giu(self):
        season = {"episodes": [{"episode_number": 1, "name": "Cơn mưa đầu mùa",
                                "air_date": "2023-10-01"}]}
        self.assertEqual(tmdb.episode_rows(7, season, True)[0]["title"],
                         "Cơn mưa đầu mùa")


class TestRealSeasons(unittest.TestCase):
    def test_bo_season_0(self):
        d = {"seasons": [{"season_number": 0}, {"season_number": 1}, {"season_number": 2}]}
        self.assertEqual(tmdb.real_seasons(d), [1, 2])

    def test_mot_mua(self):
        self.assertEqual(tmdb.real_seasons({"seasons": [{"season_number": 0},
                                                        {"season_number": 1}]}), [1])


class TestHttp(unittest.TestCase):
    def test_thieu_key_bao_loi_ro_rang(self):
        with patch.object(config, "TMDB_API_KEY", ""):
            with self.assertRaises(tmdb.TmdbError) as ctx:
                tmdb._get("/search/tv", {"query": "x"})
        self.assertIn("TMDB_API_KEY", str(ctx.exception))

    def test_401_noi_ro_key_sai(self):
        with patch.object(config, "TMDB_API_KEY", "bad"), \
             patch("ingest.tmdb.requests.get", return_value=_resp(401)):
            with self.assertRaises(tmdb.TmdbError) as ctx:
                tmdb._get("/search/tv", {"query": "x"})
        self.assertIn("401", str(ctx.exception))
        self.assertIn("không hợp lệ", str(ctx.exception))

    def test_429_bao_ro(self):
        with patch.object(config, "TMDB_API_KEY", "k"), \
             patch("ingest.tmdb.requests.get", return_value=_resp(429)):
            with self.assertRaises(tmdb.TmdbError) as ctx:
                tmdb._get("/search/tv", {"query": "x"})
        self.assertIn("429", str(ctx.exception))

    def test_200_tra_json_va_gui_dung_tham_so(self):
        with patch.object(config, "TMDB_API_KEY", "key-abc"), \
             patch("ingest.tmdb.requests.get",
                   return_value=_resp(200, {"results": []})) as get:
            out = tmdb._get("/search/tv", {"query": "frieren"})
        self.assertEqual(out, {"results": []})
        url = get.call_args.args[0]
        self.assertTrue(url.startswith("https://api.themoviedb.org/3"))
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["api_key"], "key-abc")
        self.assertEqual(params["language"], "vi-VN")
        self.assertEqual(params["query"], "frieren")


class TestPickSeason(unittest.TestCase):
    """Chọn ĐÚNG mùa TMDB cho 1 entry AniList.

    Bối cảnh thật: TMDB id 75865 (Takagi-san) có 3 mùa 12 tập; AniList tách
    "Karakai Jouzu no Takagi-san" (2018) / "2nd Season" (2019) / "3rd Season" (2022)
    thành 3 entry. Không chọn mùa thì không có danh sách tập nào.
    """

    D = {"seasons": [
        {"season_number": 0, "episode_count": 1, "air_date": "2017-01-01"},
        {"season_number": 1, "episode_count": 12, "air_date": "2018-01-08"},
        {"season_number": 2, "episode_count": 12, "air_date": "2019-07-07"},
        {"season_number": 3, "episode_count": 12, "air_date": "2022-01-08"},
    ]}

    def test_mot_mua_thi_lay_luon(self):
        d = {"seasons": [{"season_number": 1, "episode_count": 24,
                          "air_date": "2023-10-01"}]}
        self.assertEqual(tmdb.pick_season(d, 2023, 24)[0], 1)

    def test_nhieu_mua_giong_nhau_thi_dung_NAM(self):
        # cả 3 mùa đều 12 tập → số tập không phân biệt được, phải dùng năm
        self.assertEqual(tmdb.pick_season(self.D, 2018, 12)[0], 1)
        self.assertEqual(tmdb.pick_season(self.D, 2019, 12)[0], 2)
        self.assertEqual(tmdb.pick_season(self.D, 2022, 12)[0], 3)

    def test_khong_co_nam_thi_dung_SO_TAP_neu_duy_nhat(self):
        d = {"seasons": [
            {"season_number": 1, "episode_count": 12, "air_date": "2018-01-08"},
            {"season_number": 2, "episode_count": 24, "air_date": "2019-07-07"},
        ]}
        self.assertEqual(tmdb.pick_season(d, None, 24)[0], 2)

    def test_mo_ho_thi_TRA_NONE_khong_doan(self):
        d = {"seasons": [
            {"season_number": 1, "episode_count": 12, "air_date": "2018-01-08"},
            {"season_number": 2, "episode_count": 12, "air_date": "2019-07-07"},
        ]}
        so, why = tmdb.pick_season(d, None, 12)
        self.assertIsNone(so)
        self.assertIn("không xác định", why)

    def test_bo_qua_season_0_specials(self):
        d = {"seasons": [{"season_number": 0, "episode_count": 99},
                         {"season_number": 1, "episode_count": 12,
                          "air_date": "2020-01-01"}]}
        self.assertEqual(tmdb.pick_season(d, None, None)[0], 1)

    def test_khong_co_mua_nao(self):
        self.assertIsNone(tmdb.pick_season({"seasons": []})[0])


class TestEpisodesPlausible(unittest.TestCase):
    """Không ghi danh sách tập khi TMDB trả nhiều hơn hẳn AniList."""

    def test_khop_chinh_xac(self):
        self.assertTrue(tmdb.episodes_plausible(12, 12))

    def test_dang_chieu_con_thieu_tap(self):
        self.assertTrue(tmdb.episodes_plausible(12, 8))

    def test_tmdb_nhieu_hon_han(self):
        # Fool Night thật: AniList 3 tập, TMDB trả 12 → nghi lấy nhầm
        self.assertFalse(tmdb.episodes_plausible(3, 12))

    def test_chua_biet_tong_thi_cho_qua(self):
        self.assertTrue(tmdb.episodes_plausible(None, 12))

    def test_mua_rong(self):
        self.assertTrue(tmdb.episodes_plausible(12, 0))


class TestCleanEpisodeTitle(unittest.TestCase):
    """TMDB trả tên placeholder khi chưa dịch → không lưu vào DB.

    Đo thật trên DB: 429/526 tên tập là "Episode N" → app hiện dòng chữ vô nghĩa
    trùng với con số to của ô tập.
    """

    def test_bo_placeholder(self):
        for raw in ("Episode 7", "Ep. 7", "Tập 7", "第7話", "EP7", "7", "  Episode 12 "):
            self.assertIsNone(tmdb.clean_episode_title(raw), raw)

    def test_giu_ten_that(self):
        self.assertEqual(tmdb.clean_episode_title("Nishikata và cơn mưa"),
                         "Nishikata và cơn mưa")
        # chứa chữ "episode" nhưng là tên thật → giữ
        self.assertEqual(tmdb.clean_episode_title("Episode of the Town"),
                         "Episode of the Town")

    def test_rong_va_none(self):
        self.assertIsNone(tmdb.clean_episode_title(""))
        self.assertIsNone(tmdb.clean_episode_title(None))

    def test_episode_rows_dung_ham_loc(self):
        season = {"episodes": [
            {"episode_number": 1, "name": "Episode 1", "air_date": "2018-01-08"},
            {"episode_number": 2, "name": "Cuộc gặp ở phòng y tế",
             "air_date": "2018-01-15"},
        ]}
        rows = tmdb.episode_rows(9, season, single_season=True)
        self.assertIsNone(rows[0]["title"])
        self.assertEqual(rows[1]["title"], "Cuộc gặp ở phòng y tế")


if __name__ == "__main__":
    unittest.main()