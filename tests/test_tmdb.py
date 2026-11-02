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
        self.assertNotIn("title", rows[0])   # placeholder → bỏ khoá, không gửi NULL

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
        self.assertNotIn("title", rows[0])   # placeholder → bỏ khoá, không gửi NULL
        self.assertEqual(rows[1]["title"], "Cuộc gặp ở phòng y tế")


if __name__ == "__main__":
    unittest.main()

class TestSeasonFromTitle(unittest.TestCase):
    """30 bộ đã chiếu xong mà 0 tập (đo 02/11/2026) vì pick_season bó tay trước
    các mùa giống nhau (12–13 tập/mùa). Nay đọc số mùa ngay từ tên bộ."""

    def test_doc_so_mua_tu_ten(self):
        cases = {
            "Kusuriya no Hitorigoto 2nd Season": 2,
            "Ao no Hako Season 2": 2,
            "Tensei Shitara Ken Deshita 2nd Season": 2,
            "Kusuriya no Hitorigoto 3rd Season": 3,
            # HỒI QUY 02/11/2026: tên dạng ngắn "… 2" CHÍNH LÀ mùa 2. Trước đây
            # trả None ⇒ job D không chọn được mùa ⇒ bộ 0 tập dù TMDB có đủ.
            "Karakai Jouzu no Takagi-san 2": 2,
            "PetitCure: Precure Fairies Season 4": 4,
            "Bộ phim - Mùa 2": 2,
            # HỒI QUY 02/11/2026: "Second Season" viết bằng CHỮ (Diamond no Ace
            # act II: Second Season) trước đây không khớp regex nào → None.
            "Diamond no Ace act II: Second Season": 2,
            "Some Show Third Season": 3,
        }
        for title, want in cases.items():
            self.assertEqual(tmdb.season_from_title(title), want, title)

    def test_khong_doc_Part_2_vi_do_la_cour_trong_cung_mua(self):
        self.assertIsNone(tmdb.season_from_title("Chitose-kun wa Ramune Bin no Naka Part 2"))
        self.assertIsNone(tmdb.season_from_title("Mahou no Shimai LuluttoLilly Part 2"))

    def test_ten_khong_co_mua(self):
        self.assertIsNone(tmdb.season_from_title("FAIRY TAIL", "Fairy Tail"))
        self.assertIsNone(tmdb.season_from_title(None, ""))

    def test_thu_nhieu_ten_lay_cai_dau_tien_co(self):
        self.assertEqual(
            tmdb.season_from_title(None, "Some Anime 2nd Season", "Mùa 3"), 2)


class TestPickSeasonTheoTen(unittest.TestCase):
    def setUp(self):
        self.D = {"seasons": [
            {"season_number": 1, "episode_count": 24, "air_date": "2023-10-01"},
            {"season_number": 2, "episode_count": 24, "air_date": "2025-01-10"},
        ]}

    def test_goi_y_mua_thang_duoc_so_tap_va_nam(self):
        """Hai mùa đều 24 tập, năm lại lệch → trước đây trả None."""
        self.assertEqual(tmdb.pick_season(self.D, 2025, 24)[0], 2)   # nhờ năm
        self.assertEqual(tmdb.pick_season(self.D, None, 24)[0], None)  # mù mờ
        so, why = tmdb.pick_season(self.D, None, 24, season_hint=2)
        self.assertEqual(so, 2)
        self.assertIn("theo tên", why)

    def test_goi_y_khong_co_mua_do_thi_TRA_NONE(self):
        """Tên ghi mùa 5 nhưng TMDB chỉ có 1–2 → không được đoán sang mùa khác."""
        so, why = tmdb.pick_season(self.D, 2025, 24, season_hint=5)
        self.assertIsNone(so)
        self.assertIn("mùa 5", why)


class TestMuaTuTenDangNgan(unittest.TestCase):
    """AniList hay dùng dạng ngắn cho mùa 2/3 — trước đây không đọc được.

    Đo 02/11/2026: "One Punch Man 2", "Mob Psycho 100 II", "Karakai Jouzu no
    Takagi-san 2" đều trả None ⇒ job D không biết chọn mùa nào ⇒ 0 tập.
    """

    def test_so_o_cuoi(self):
        self.assertEqual(tmdb.season_from_title("One Punch Man 2"), 2)
        self.assertEqual(tmdb.season_from_title("Karakai Jouzu no Takagi-san 2"), 2)

    def test_so_la_ma(self):
        self.assertEqual(tmdb.season_from_title("Mob Psycho 100 II"), 2)
        self.assertEqual(tmdb.season_from_title("Some Show III"), 3)

    def test_so_lon_khong_phai_mua(self):
        """"Mob Psycho 100" là số 100 trong TÊN, không phải mùa 100."""
        self.assertIsNone(tmdb.season_from_title("Mob Psycho 100"))
        self.assertIsNone(tmdb.season_from_title("Ranma 1/2"))

    def test_khong_doan_khi_co_dau_hai_cham(self):
        """"Girls und Panzer: Saishuushou 5" là phần 5 của phim, không phải mùa TV."""
        self.assertIsNone(tmdb.season_from_title("Girls und Panzer: Saishuushou 5"))

    def test_van_doc_dung_dang_day_du(self):
        self.assertEqual(tmdb.season_from_title("Dandadan 2nd Season"), 2)
        self.assertEqual(tmdb.season_from_title("Kusuriya no Hitorigoto 3rd Season"), 3)


class TestEntryRiengCuaTungMua(unittest.TestCase):
    """TMDB có entry RIÊNG cho mỗi mùa (id 220542 = "Apothecary Diaries Season 2").

    Đo 02/11/2026: 5 bộ FINISHED đã có `tmdb_id` nhưng vẫn 0 tập — vì
    `season_from_title` đòi mùa 2, còn entry đó chỉ có Season 1 (24 tập), nên
    `pick_season` từ chối. Thực tế phải dùng chính Season 1 của entry đó.
    """

    D = {"seasons": [{"season_number": 1, "episode_count": 24,
                      "air_date": "2025-01-10"}]}

    def test_nhan_khi_so_tap_khop(self):
        so, why = tmdb.pick_season(self.D, 2025, 24, season_hint=2)
        self.assertEqual(so, 1, why)

    def test_van_tu_choi_khi_so_tap_lech_xa(self):
        """Entry 24 tập không thể là entry 12 tập của mùa khác."""
        so, why = tmdb.pick_season(self.D, 2025, 12, season_hint=2)
        self.assertIsNone(so, why)

    def test_khong_co_so_tap_thi_khong_doan(self):
        so, _ = tmdb.pick_season(self.D, None, None, season_hint=2)
        self.assertIsNone(so)


class TestBaseTitle(unittest.TestCase):
    """Tìm trên TMDB bằng TÊN GỐC khi tên có hậu tố mùa.

    Đo 02/11/2026: `tmdb --limit-tmdb 200` báo **56 bộ không tìm được trên TMDB**
    (`One-Punch Man Season 2`, `DAN DA DAN Season 2`, `Shangri-La Frontier Season
    2`, …) vì TMDB đặt tên series GỘP cả bộ, không có "Season 2" trong tên.
    """

    def test_bo_hau_to_mua(self):
        cases = {
            "One-Punch Man Season 2": "One-Punch Man",
            "Dandadan 2nd Season": "Dandadan",
            "One Punch Man 2": "One Punch Man",
            "Mob Psycho 100 II": "Mob Psycho 100",
            "Bộ phim - Mùa 2": "Bộ phim",
        }
        for title, want in cases.items():
            self.assertEqual(tmdb.base_title(title), want, title)

    def test_khong_cat_bua_khi_khong_co_mua(self):
        self.assertIsNone(tmdb.base_title("Naruto"))
        self.assertIsNone(tmdb.base_title("FAIRY TAIL"))
        self.assertIsNone(tmdb.base_title(None))

    def test_match_anime_thu_lai_bang_ten_goc(self):
        """Tên có "Season 2" trả 0 kết quả, tên gốc mới ra series gộp."""
        from unittest.mock import patch
        row = {"title_english": "One-Punch Man Season 2",
               "title_romaji": "One Punch Man 2", "title_native": None,
               "year": 2019}
        results = [{"id": 63926, "name": "One-Punch Man",
                    "original_name": "One-Punch Man",
                    "first_air_date": "2015-09-20", "popularity": 80}]

        def fake_get(path, params=None):
            assert path == "/search/tv"
            q = (params or {}).get("query", "")
            return {"results": results if q == "One-Punch Man" else []}

        with patch.object(tmdb, "_get", side_effect=fake_get), \
                patch.object(tmdb.time, "sleep"):
            best, score, how = tmdb.match_anime(row)
        self.assertIsNotNone(best, how)
        self.assertIn("One-Punch Man", how)


class TestCatBotTapMuaDau(unittest.TestCase):
    """TMDB gộp 2 mùa/2 cour vào MỘT mùa → nhiều tập hơn AniList.

    Đo 02/11/2026: 9 bộ bị bỏ trống danh sách tập vì lý do này — `Blue Box`
    (TMDB 37 > AniList 25), `You and I Are Polar Opposites` (25 > 12), `The
    Ramparts of Ice` (28 > 14), `A Wild Last Boss Appeared!` (24 > 12)…
    Với entry MÙA ĐẦU thì tập 1..N vẫn đúng → cắt phần dư là an toàn.
    """

    def _d(self, count, air="2025-01-10", extra=None):
        seasons = [{"season_number": 1, "episode_count": count, "air_date": air}]
        if extra:
            seasons.append(extra)
        return {"seasons": seasons}

    def test_cat_khi_la_mua_dau_va_gap_doi(self):
        self.assertEqual(tmdb.first_season_cut(self._d(37), 1, None, 2025, 25), 25)
        self.assertEqual(tmdb.first_season_cut(self._d(24), 1, None, 2025, 12), 12)

    def test_khong_cat_khi_la_mua_sau(self):
        d = self._d(12, extra={"season_number": 2, "episode_count": 12,
                               "air_date": "2026-01-10"})
        self.assertIsNone(tmdb.first_season_cut(d, 2, None, 2026, 12))

    def test_khong_cat_khi_ten_ghi_mua(self):
        self.assertIsNone(tmdb.first_season_cut(self._d(24), 1, 2, 2025, 12))

    def test_khong_cat_khi_nam_lech(self):
        self.assertIsNone(tmdb.first_season_cut(self._d(24, "2015-01-10"),
                                                1, None, 2019, 12))

    def test_khong_cat_khi_nhieu_hon_gap_doi(self):
        """Fool Night: AniList 3 vs TMDB 12 (4×) → nghi lấy nhầm series."""
        self.assertIsNone(tmdb.first_season_cut(self._d(12), 1, None, 2026, 3))

    def test_episode_rows_cat_dung_so(self):
        season = {"episodes": [
            {"episode_number": i, "air_date": "2025-01-0%d" % (i % 9 + 1),
             "name": f"T{i}"} for i in range(1, 13)]}
        rows = tmdb.episode_rows(7, season, True, max_number=5)
        self.assertEqual([r["number"] for r in rows], [1, 2, 3, 4, 5])


class TestExplain(unittest.TestCase):
    """`python3 -m ingest.tmdb --slug …` — in TMDB trả gì để chẩn đoán."""

    def test_in_du_ten_nam_diem_va_danh_dau_loai(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        row = {"slug": "the-ramparts-of-ice-season-2",
               "title_english": "The Ramparts of Ice Season 2",
               "title_romaji": "Koori no Jouheki 2nd Season",
               "year": 2026, "episodes_total": 12, "tmdb_id": None}
        res = [{"id": 283428, "name": "The Ramparts of Ice",
                "original_name": "The Ramparts of Ice",
                "first_air_date": "2026-01-10"},
               {"id": 1, "name": "Hoàn toàn khác", "original_name": None,
                "first_air_date": "1999-01-01"}]
        with patch.object(tmdb, "_get", return_value={"results": res}), \
                patch.object(tmdb.time, "sleep"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                tmdb.explain(row)
        out = buf.getvalue()
        self.assertIn("The Ramparts of Ice Season 2", out)
        self.assertIn("283428", out)
        self.assertIn("✓", out)
        self.assertIn("✗", out)

    def test_in_luon_cac_mua_va_ly_do_tu_choi(self):
        """Log cũ chỉ nói "TMDB chỉ có mùa 1" mà không nói mùa đó bao nhiêu tập
        ⇒ không thể biết vì sao bị từ chối. Nay phải in từng mùa + lý do."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        # Ca thật: kusuriya-no-hitorigoto-2nd-season — tên ghi mùa 2 nhưng TMDB
        # chỉ có mùa 1 với 12 tập (khác xa 24 tập AniList) → phải TỪ CHỐI.
        row = {"slug": "kusuriya-2nd",
               "title_english": "The Apothecary Diaries Season 2",
               "year": 2025, "episodes_total": 24, "tmdb_id": None}
        res = [{"id": 220542, "name": "The Apothecary Diaries Season 2",
                "first_air_date": "2023-10-22"}]
        detail = {"seasons": [{"season_number": 1, "episode_count": 12,
                               "air_date": "2023-10-22"}]}
        with patch.object(tmdb, "_get", return_value={"results": res}), \
                patch.object(tmdb, "fetch_detail", return_value=detail), \
                patch.object(tmdb.time, "sleep"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                tmdb.explain(row)
        out = buf.getvalue()
        self.assertIn("mùa 1: 12 tập", out)
        self.assertIn("TỪ CHỐI", out)

    def test_in_phan_bo_ngay_chieu(self):
        """Cần thấy "năm nào có bao nhiêu tập" để biết vì sao tách theo năm trượt
        (TMDB thiếu ngày? tập nằm ở năm khác?)."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        row = {"slug": "yozakura-2nd", "title_english": "Mission: Yozakura S2",
               "year": 2026, "episodes_total": 12, "tmdb_id": None}
        res = [{"id": 216467, "name": "Mission: Yozakura Family",
                "first_air_date": "2024-04-07"}]
        detail = {"seasons": [{"season_number": 1, "episode_count": 24,
                               "air_date": "2024-04-07"}]}
        eps = [{"episode_number": i, "air_date": "2025-01-%02d" % (i % 28 + 1),
                "name": f"T{i}"} for i in range(1, 25)]
        with patch.object(tmdb, "_get", return_value={"results": res}), \
                patch.object(tmdb, "fetch_detail", return_value=detail), \
                patch.object(tmdb, "fetch_season",
                             return_value={"episodes": eps}), \
                patch.object(tmdb.time, "sleep"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                tmdb.explain(row)
        out = buf.getvalue()
        self.assertIn("ngày chiếu:", out)
        self.assertIn("2025: 24 tập", out)


class TestGopMuaTrenTmdb(unittest.TestCase):
    """TMDB gộp nhiều mùa AniList vào MỘT season.

    Ca thật 02/11/2026: `dandadan-2nd-season` (AniList 12 tập, tên ghi mùa 2) trỏ
    tới TMDB 240411 "DAN DA DAN" chỉ có 1 season 24 tập. `pick_season` từ chối và
    bộ **lặng lẽ** không có tập nào — `check` không hề báo gì.
    """

    D24 = {"seasons": [{"season_number": 1, "episode_count": 24,
                        "air_date": "2024-10-04"}]}

    def test_mua_2_cua_season_24_tap(self):
        got = tmdb.split_season_offset(self.D24, 2, 12)
        self.assertEqual(got["season"], 1)
        self.assertEqual(got["offset"], 12)

    def test_khong_nhan_mua_1(self):
        self.assertIsNone(tmdb.split_season_offset(self.D24, 1, 12))

    def test_khong_nhan_khi_boi_so_khong_khop(self):
        """3 mùa × 12 = 36 ≠ 24 → không phải bộ này."""
        self.assertIsNone(tmdb.split_season_offset(self.D24, 3, 12))

    def test_khong_nhan_khi_tmdb_co_nhieu_mua(self):
        d = {"seasons": [
            {"season_number": 1, "episode_count": 12, "air_date": "2024-10-04"},
            {"season_number": 2, "episode_count": 12, "air_date": "2025-07-04"}]}
        self.assertIsNone(tmdb.split_season_offset(d, 2, 12))

    def test_danh_so_lai_sau_khi_tru_offset(self):
        season = {"episodes": [
            {"episode_number": i, "air_date": "2025-07-0%d" % (i % 9 + 1),
             "name": f"T{i}"} for i in range(1, 25)]}
        rows = tmdb.episode_rows(9, season, True, max_number=12, offset=12)
        self.assertEqual([r["number"] for r in rows], list(range(1, 13)))
        self.assertEqual(rows[0]["title"], "T13")   # giữ tên/ngày thật của TMDB


class TestThuUngVienKeTiep(unittest.TestCase):
    """TMDB trả NHIỀU series cho cùng một bộ — phải thử ứng viên kế tiếp.

    Ca thật 02/11/2026: `kusuriya-no-hitorigoto-2nd-season` (mùa 2) tìm ra cả
    220542 "Dược Sư Tự Sự" (chỉ có mùa 1) và 333686. Chỉ thử ứng viên điểm cao
    nhất ⇒ bộ bị bỏ trắng dù ứng viên kia có mùa 2.
    """

    def test_pick_all_tra_nhieu_ung_vien_giam_dan(self):
        titles = ["The Apothecary Diaries Season 2"]
        res = [{"id": 1, "name": "The Apothecary Diaries", "original_name": None,
                "first_air_date": "2023-10-22", "popularity": 50},
               {"id": 2, "name": "The Apothecary Diaries Season 2",
                "original_name": None, "first_air_date": "2025-01-10",
                "popularity": 10}]
        got = tmdb.pick_all(res, titles, None)
        self.assertEqual({r["id"] for r, _ in got}, {1, 2}, "phải trả CẢ HAI")
        scores = [sc for _, sc in got]
        self.assertEqual(scores, sorted(scores, reverse=True), "điểm giảm dần")

    def test_pick_all_khu_trung_theo_id(self):
        titles = ["Naruto"]
        res = [{"id": 7, "name": "Naruto", "first_air_date": "2002-10-03"},
               {"id": 7, "name": "Naruto", "first_air_date": "2002-10-03"}]
        self.assertEqual(len(tmdb.pick_all(res, titles, None)), 1)

    def test_match_anime_bo_qua_ung_vien_bi_tu_choi(self):
        row = {"title_english": "The Apothecary Diaries Season 2",
               "title_romaji": None, "title_native": None, "year": 2025}
        # 220542 khớp tên CHÍNH XÁC (điểm cao nhất) nhưng bị `accept` từ chối;
        # 333686 khớp mờ hơn nhưng có mùa cần tìm → phải nhảy sang ứng viên này.
        res = [{"id": 220542, "name": "The Apothecary Diaries Season 2",
                "first_air_date": "2023-10-22", "popularity": 90},
               {"id": 333686, "name": "The Apothecary Diaries",
                "first_air_date": "2025-01-10", "popularity": 5}]
        seen = []

        def accept(r):
            seen.append(r["id"])
            return r["id"] == 333686

        with patch.object(tmdb, "_get", return_value={"results": res}), \
                patch.object(tmdb.time, "sleep"):
            best, score, _ = tmdb.match_anime(row, accept=accept)
        self.assertEqual(best["id"], 333686, "phải thử ứng viên kế tiếp")
        self.assertEqual(seen[0], 220542)


class TestBoQuaBoVuaHoiTmdb(unittest.TestCase):
    """Không quét lại bộ vừa hỏi TMDB.

    Đo 02/11/2026: một lần chạy quét đủ 161 bộ trong **792 giây** và ghi được
    **0 bản ghi** — vì 44 bộ TMDB không có + 13 bộ không có bản dịch vi luôn
    thoả `title_vi.is.null` nên lần nào cũng bị chọn lại.
    """

    NOW = dt.datetime(2026, 11, 2, 12, 0, 0, tzinfo=dt.timezone.utc)

    def test_chua_tung_hoi_thi_xu_ly(self):
        cutoff = tmdb.stale_cutoff(7, self.NOW)
        self.assertTrue(tmdb.is_stale(None, cutoff))

    def test_hoi_hom_qua_thi_bo_qua(self):
        cutoff = tmdb.stale_cutoff(7, self.NOW)
        self.assertFalse(tmdb.is_stale("2026-11-01T23:59:59+00:00", cutoff))

    def test_hoi_30_ngay_truoc_thi_xu_ly_lai(self):
        cutoff = tmdb.stale_cutoff(7, self.NOW)
        self.assertTrue(tmdb.is_stale("2026-10-01T00:00:00+00:00", cutoff))

    def test_dang_chieu_chi_cho_1_ngay(self):
        cutoff = tmdb.stale_cutoff(tmdb.STALE_DAYS_RELEASING, self.NOW)
        self.assertFalse(tmdb.is_stale("2026-11-02T09:00:00+00:00", cutoff))
        self.assertTrue(tmdb.is_stale("2026-11-01T09:00:00+00:00", cutoff))

    def test_cutoff_dung_so_ngay(self):
        self.assertEqual(tmdb.stale_cutoff(7, self.NOW), "2026-10-26T12:00:00")
        self.assertEqual(tmdb.stale_cutoff(1, self.NOW), "2026-11-01T12:00:00")


class TestDonMuaTachTheoNam(unittest.TestCase):
    """TMDB dồn nhiều mùa vào MỘT season với số tập "lẻ".

    Ca thật 02/11/2026 (`explain --slug kusuriya-no-hitorigoto-2nd-season`):
    TMDB 220542 có **một** mùa **60 tập** = mùa 1 (24) + mùa 2 (24) + mùa 3 (12).
    Luật `split_season_offset` đòi 60 ≈ 2×24 nên trượt (60 ≠ 48); nhưng tập của
    mùa 2 tách được bằng NGÀY CHIẾU (năm 2025).
    """

    @staticmethod
    def _season():
        eps, n = [], 1
        for y, c in ((2023, 24), (2025, 24), (2026, 12)):
            for i in range(c):
                eps.append({"episode_number": n,
                            "air_date": f"{y}-01-{i % 28 + 1:02d}",
                            "name": f"T{n}"})
                n += 1
        return {"episodes": eps}

    def test_lay_dung_24_tap_cua_nam_2025(self):
        rows = tmdb.episode_rows_by_year(7, self._season(), 2025, 24)
        self.assertEqual([r["number"] for r in rows], list(range(1, 25)))
        self.assertEqual(rows[0]["title"], "T25", "giữ tên/ngày thật của TMDB")
        self.assertTrue(rows[0]["airing_at"].startswith("2025"))

    def test_nam_khong_co_tap_thi_tra_rong(self):
        self.assertEqual(tmdb.episode_rows_by_year(7, self._season(), 2024, 24), [])

    def test_so_tap_lech_nhieu_thi_tu_choi(self):
        """Mùa vắt qua 2 năm (12 + 12) tách theo năm ra 12 ≠ 24 → bỏ."""
        self.assertEqual(tmdb.episode_rows_by_year(7, self._season(), 2026, 24), [])

    def test_ung_vien_chi_khi_nhieu_hon_han(self):
        D = {"seasons": [{"season_number": 1, "episode_count": 60,
                          "air_date": "2023-10-22"}]}
        self.assertEqual(tmdb.merged_year_candidate(D, 2, 2025, 24), 1)
        self.assertIsNone(tmdb.merged_year_candidate(D, 1, 2025, 24))
        self.assertIsNone(tmdb.merged_year_candidate(D, 2, None, 24))

    def test_khong_nhan_khi_tmdb_nhieu_mua_rieng(self):
        D = {"seasons": [
            {"season_number": 1, "episode_count": 24, "air_date": "2023-10-22"},
            {"season_number": 2, "episode_count": 24, "air_date": "2025-01-10"}]}
        self.assertIsNone(tmdb.merged_year_candidate(D, 2, 2025, 24))
