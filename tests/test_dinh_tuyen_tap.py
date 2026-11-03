"""Định tuyến tập CỘNG DỒN qua các mùa (Muse VN) — `ingest/franchise.py` + job C.

Bằng chứng đo thật 03/11/2026 (oEmbed, không cần API key):

    youtu.be/iry712JcyDc → "Lúc đó tôi đã chuyển sinh thành Slime - Tập 13"

Video đó nằm ở mùa 3 nhưng tiêu đề **không có chữ "S3"** và số tập chạy tiếp từ
mùa trước (S1 1–24, S2 25–48, S3 49–72). Trước bản vá này:

* 702 (`3rd Season`, 24 tập) nhận 12 link tập **13–24** — thực chất là tập của
  MÙA 1 ⇒ người xem bấm "tập 13 mùa 3" lại ra tập 13 mùa 1.
* 701 (`2nd Season`, 12 tập) nhận **0 link**, 25 video vào `review`.
* 699 (`Season 3`, 12 tập) chỉ nhận 12/22 video; Muse đánh S3 = 1–22 vì S3 gồm
  Season 3 (12) + Season 3 Part 2 (10) trong AniList.
"""
import unittest
from unittest.mock import patch

from ingest import franchise
from ingest import main as ingest_main


def node(id_, eps, romaji, fmt="TV"):
    return {"id": id_, "episodes": eps, "format": fmt,
            "title": {"romaji": romaji, "native": None, "english": None}}


SLIME1 = node(39535, 24, "Tensei Shitara Slime Datta Ken")
SLIME2 = node(108511, 12, "Tensei Shitara Slime Datta Ken 2nd Season")
SLIME2P2 = node(116742, 12, "Tensei Shitara Slime Datta Ken 2nd Season Part 2")
SLIME3 = node(156822, 24, "Tensei Shitara Slime Datta Ken 3rd Season")

AOT1 = node(16498, 25, "Shingeki no Kyojin")
AOT2 = node(20958, 12, "Shingeki no Kyojin Season 2")
AOT3 = node(99147, 12, "Shingeki no Kyojin Season 3")
AOT3P2 = node(104578, 10, "Shingeki no Kyojin Season 3 Part 2")

CHUOI = {39535: (None, [SLIME2]), 108511: ([SLIME1], [SLIME2P2]),
         116742: ([SLIME2], [SLIME3]), 156822: ([SLIME2P2], []),
         16498: (None, [AOT2]), 20958: ([AOT1], [AOT3]),
         99147: ([AOT2], [AOT3P2]), 104578: ([AOT3], [])}


def fake_related(media_id, kinds=("SEQUEL",)):
    pre, seq = CHUOI.get(int(media_id), (None, []))
    if "PREQUEL" in kinds:
        return list(pre or [])
    return list(seq)


class TestChuoiThuongHieu(unittest.TestCase):

    def setUp(self):
        self.p = patch.object(franchise.anilist, "related", side_effect=fake_related)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_di_ve_goc_roi_xuoi_sequel(self):
        chain = franchise.chain_of(SLIME3, {})
        self.assertEqual([e["id"] for e in chain],
                         [39535, 108511, 116742, 156822])
        self.assertEqual([(e["start"], e["end"]) for e in chain],
                         [(1, 24), (25, 36), (37, 48), (49, 72)])

    def test_bo_qua_movie_va_entry_khong_biet_so_tap(self):
        # MOVIE chen giữa dãy số sẽ làm lệch mọi mùa phía sau.
        film = node(999, 1, "Slime Movie", fmt="MOVIE")
        with patch.object(franchise.anilist, "related",
                          side_effect=lambda mid, kinds=("SEQUEL",):
                          [film] + fake_related(mid, kinds)):
            chain = franchise.chain_of(SLIME3, {})
        self.assertNotIn(999, [e["id"] for e in chain])

    def test_cache_tranh_goi_lai(self):
        cache = {}
        franchise.chain_of(SLIME3, cache)
        franchise.chain_of(SLIME3, cache)
        self.assertIn("franchise:PREQUEL:156822", cache)


class TestPlan(unittest.TestCase):

    def setUp(self):
        p = patch.object(franchise.anilist, "related", side_effect=fake_related)
        p.start()
        self.addCleanup(p.stop)

    def test_slime_cong_don(self):
        # Muse: Tập 49 = tập 1 của mùa 3
        entry, ep, kieu = franchise.route(SLIME3, 49, 49, 72, {})
        self.assertEqual((entry["id"], ep, kieu), (156822, 1, "cumulative"))
        entry, ep, _ = franchise.route(SLIME3, 60, 49, 72, {})
        self.assertEqual((entry["id"], ep), (156822, 12))
        entry, ep, _ = franchise.route(SLIME3, 72, 49, 72, {})
        self.assertEqual((entry["id"], ep), (156822, 24))

    def test_slime_mua_2_part_2_nam_trong_day(self):
        entry, ep, _ = franchise.route(SLIME3, 40, 1, 72, {})
        self.assertEqual((entry["id"], ep), (116742, 4))

    def test_shingeki_s3_gop_hai_phan(self):
        # Muse đánh S3 = 1–22 (Season 3 12 tập + Part 2 10 tập)
        entry, ep, kieu = franchise.route(AOT3, 13, 1, 22, {})
        self.assertEqual((entry["id"], ep, kieu), (104578, 1, "fill"))
        entry, ep, _ = franchise.route(AOT3, 12, 1, 22, {})
        self.assertEqual((entry["id"], ep), (99147, 12))
        entry, ep, _ = franchise.route(AOT3, 22, 1, 22, {})
        self.assertEqual((entry["id"], ep), (104578, 10))

    def test_khong_mo_hinh_nao_phu_thi_tra_none(self):
        # Khoảng 1–99 vượt cả thương hiệu (72 tập) ⇒ KHÔNG đoán.
        self.assertIsNone(franchise.plan(SLIME3, 1, 99, {}))

    def test_bo_mot_mua_khong_doi(self):
        entry, ep, kieu = franchise.route(SLIME1, 13, 1, 24, {})
        self.assertEqual((entry["id"], ep, kieu), (39535, 13, "fill"))


class FakeDB:
    def __init__(self, anime=(), alias=()):
        self.anime = [dict(a) for a in anime]
        self.alias = [dict(a) for a in alias]
        self.upserted = []
        self.dry = False

    def select_all(self, table, query, **kw):
        if table == "anime":
            return [dict(a) for a in self.anime]
        if table == "anime_alias":
            return [dict(a) for a in self.alias]
        return []

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        if table == "anime":
            return [dict(r, id=r.get("id") or 777) for r in rows]
        return list(rows)

    def patch(self, *a, **k):
        return None


def anime(id_, anilist_id, eps, **kw):
    row = {"id": id_, "anilist_id": anilist_id, "slug": f"a{id_}",
           "title_vi": None, "title_romaji": kw.pop("romaji", f"Bộ {id_}"),
           "title_english": None, "title_native": None,
           "episodes_total": eps, "popularity": 100, "format": "TV", "year": 2024}
    row.update(kw)
    return row


def video(series, ep, url=None):
    return {"series": series, "series_base": series, "episode": ep,
            "season": None, "region": "VN",
            "url": url or f"https://youtu.be/{series[:4]}{ep}",
            "raw_title": f"{series} - Tập {ep}", "video_id": f"v{ep}"}


class TestJobCDinhTuyen(unittest.TestCase):
    """Job C phải đưa video về ĐÚNG mùa khi số tập chạy tiếp từ mùa trước."""

    def setUp(self):
        p = patch.object(franchise.anilist, "related", side_effect=fake_related)
        p.start()
        self.addCleanup(p.stop)

    def _db(self):
        # Mùa 1 đã có trong DB, được gắn tên Việt KHÔNG kèm mùa (do job K).
        return FakeDB(
            anime=[anime(1, 39535, 24, title_vi="Lúc đó tôi đã chuyển sinh thành Slime")],
            alias=[{"anime_id": 1, "alias": "Lúc đó tôi đã chuyển sinh thành Slime",
                    "alias_key": "lúc đó tôi đã chuyển sinh thành slime"}])

    def test_tap_13_vao_mua_1_tap_50_vao_mua_3(self):
        ten = "Lúc đó tôi đã chuyển sinh thành Slime"
        db = self._db()
        videos = [video(ten, 13), video(ten, 50)]
        # `_link_rows` trả 6 phần tử; phần tử thứ 2 là danh sách link.
        res = ingest_main._link_rows(db, videos, {}, verbose=False,
                                     rong={ten: (1, 72)})
        links = res[1]
        self.assertEqual(len(links), 2, "phải ghi được cả 2 video")
        theo_url = {l["url"]: l for l in links}
        t13 = theo_url["https://youtu.be/Lúc 13"]
        t50 = theo_url["https://youtu.be/Lúc 50"]
        self.assertEqual((t13["anime_id"], t13["episode_number"]), (1, 13))
        # Tập 50 = tập 2 của mùa 3 → bộ mùa 3 được tạo mới, KHÔNG ghi vào mùa 1
        self.assertEqual(t50["episode_number"], 2)
        self.assertNotEqual(t50["anime_id"], 1)

    def test_khong_co_khoang_thi_giu_hanh_vi_cu(self):
        ten = "Lúc đó tôi đã chuyển sinh thành Slime"
        db = self._db()
        res = ingest_main._link_rows(db, [video(ten, 13)], {}, verbose=False)
        self.assertEqual(res[1][0]["episode_number"], 13)
        self.assertEqual(res[1][0]["anime_id"], 1)


class TestGanSaiBoCu(unittest.TestCase):
    """Link cũ gắn sai bộ/tập phải được xét lại, không bị "đã có link" bỏ qua."""

    def setUp(self):
        p = patch.object(franchise.anilist, "related", side_effect=fake_related)
        p.start()
        self.addCleanup(p.stop)

    def test_giong_het_thi_bo_qua(self):
        ten = "Lúc đó tôi đã chuyển sinh thành Slime"
        db = FakeDB(anime=[anime(1, 39535, 24,
                                 title_vi="Lúc đó tôi đã chuyển sinh thành Slime")])
        v = video(ten, 13)
        res = ingest_main._link_rows(
            db, [v], {}, verbose=False, rong={ten: (1, 72)},
            da_co={v["url"]: [1, 13]})
        self.assertEqual(res[1], [], "đã đúng (bộ, tập) thì không ghi lại")

    def test_giong_bo_nhung_khac_tap_thi_ghi_lai(self):
        ten = "Lúc đó tôi đã chuyển sinh thành Slime"
        db = FakeDB(anime=[anime(1, 39535, 24,
                                 title_vi="Lúc đó tôi đã chuyển sinh thành Slime")])
        v = video(ten, 13)
        # Link cũ: url này đang bị gắn vào bộ mùa 3 (id 702) tập 13 — SAI.
        res = ingest_main._link_rows(
            db, [v], {}, verbose=False, rong={ten: (1, 72)},
            da_co={v["url"]: [702, 13]})
        self.assertEqual(res[1][0]["anime_id"], 1)
        self.assertEqual(res[1][0]["episode_number"], 13)


class TestKhoangTap(unittest.TestCase):

    def test_run_ranges_bo_qua_tap_0(self):
        vids = [video("A", 3), video("A", 9), video("A", 0), video("B", 5)]
        self.assertEqual(ingest_main._run_ranges(vids),
                         {"A": (3, 9), "B": (5, 5)})

    def test_gop_khoang_khong_lam_hep(self):
        a = {"A": (1, 72)}
        b = {"A": (70, 74), "B": (2, 2)}
        self.assertEqual(ingest_main._gop_khoang(a, b),
                         {"A": (1, 74), "B": (2, 2)})


if __name__ == "__main__":
    unittest.main()
