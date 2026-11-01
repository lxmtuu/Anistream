"""Test job C (`python3 -m ingest.main youtube`) với DB/kênh giả.

Khoá 3 hành vi sửa trong lần này (đều là lỗi thật khi backfill 5.560 video):

1. **Ghi DB theo từng kênh** — bản cũ gom cả 2 kênh rồi ghi một lần; mất mạng
   ở khâu ghép tên là mất trắng, và `ingest_runs` không có dòng nào.
2. **Cache ghép tên ra đĩa** — chạy lại không search lại từ đầu.
3. **Lỗi được ghi lại** — `log_ingest(ok=False)` kèm lý do, kênh khác vẫn ghi.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from ingest import main as ingest_main
from ingest import config, match, youtube


class FakeDB:
    def __init__(self):
        self.upserted = []
        self.logs = []
        self.dry = False
        self._next_id = 100

    def upsert(self, table, rows, on_conflict=None, fallback_per_row=False):
        self.upserted.append((table, list(rows)))
        if table == "anime":
            out = []
            for r in rows:
                self._next_id += 1
                out.append(dict(r, id=self._next_id))
            return out
        return list(rows)

    def patch(self, table, filters, values):
        return 1

    def select(self, table, query):
        return []

    def log_ingest(self, source, job, ok, rows, error=""):
        self.logs.append((source, job, ok, rows, error))


CH1 = {"key": "muse_vn", "name": "Muse Việt Nam", "channel_id": "UC1", "region": "VN"}
CH2 = {"key": "ani_one_asia", "name": "Ani-One Asia", "channel_id": "UC2", "region": "AS"}


def video(series, ep, cid="v1"):
    return {"series": series, "episode": ep, "channel": "muse_vn",
            "channel_name": "Muse", "region": "VN", "video_id": cid,
            "url": f"https://www.youtube.com/watch?v={cid}", "raw_title": series,
            "published": "", "views": 0, "duration": 1440}


MEDIA = {"id": 99468, "title": {"romaji": "Karakai Jouzu no Takagi-san",
                                "english": "Teasing Master Takagi-san",
                                "native": "からかい上手の高木さん"},
         "popularity": 1000, "format": "TV"}


class TestJobYoutubePerChannel(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "match_cache.json")
        self.patches = [
            patch.object(youtube, "CHANNELS", [CH1, CH2]),
            # chỉ Muse VN là mặc định; test này kiểm cơ chế nhiều kênh nên bật cả 2
            patch.object(config, "YOUTUBE_CHANNELS", ["muse_vn", "ani_one_asia"]),
            patch.object(match, "default_cache_path", return_value=self.cache_path),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _run(self, per_channel, resolve=None, dry=False, expect_error=False):
        db = FakeDB()
        db.dry = dry
        calls = []

        def _collect(ch, **kw):
            res = per_channel.get(ch["key"])
            if isinstance(res, Exception):
                raise res
            calls.append(ch["key"])
            return res or []

        def _default_resolve(name, cache, want_series=True):
            # giống match.resolve thật: ghi kết quả vào cache
            cache[match.alias_key(name)] = MEDIA
            return MEDIA, 1.0, "alias"

        resolve_fn = resolve or _default_resolve
        with patch.object(youtube, "collect_channel", side_effect=_collect), \
             patch.object(ingest_main, "_upsert_media",
                          side_effect=lambda DB, medias: (
                              [{"anilist_id": m["id"]} for m in medias],
                              {m["id"]: 7 for m in medias})), \
             patch.object(match, "resolve", side_effect=resolve_fn):
            buf = io.StringIO()
            with redirect_stdout(buf):
                if expect_error:
                    with self.assertRaises(RuntimeError):
                        ingest_main.job_youtube(db)
                    n = 0
                else:
                    n = ingest_main.job_youtube(db)
        return db, n, buf.getvalue()

    def test_kênh_1_hỏng_kênh_2_vẫn_được_ghi(self):
        """HỒI QUY: trước đây gom cả 2 kênh rồi mới ghi → kênh 1 hỏng là mất cả 2."""
        db, n, out = self._run({
            "muse_vn": RuntimeError("HTTP 500"),
            "ani_one_asia": [video("crayon shinchan", 5, "v2")],
        }, expect_error=True)
        links = [u for u in db.upserted if u[0] == "streaming_links"]
        self.assertEqual(len(links), 1, "kênh 2 vẫn phải được ghi")
        self.assertEqual(links[0][1][0]["url"], "https://www.youtube.com/watch?v=v2")
        # lỗi phải được GHI LẠI, không im lặng
        self.assertFalse(db.logs[-1][2])
        self.assertIn("Ani-One", out)
        self.assertIn("Muse Việt Nam: HTTP 500", out)

    def test_có_kênh_lỗi_thì_NỔ_để_cron_đỏ(self):
        """Không được 'CI xanh mà việc thật không xảy ra'."""
        with self.assertRaises(RuntimeError) as ctx:
            self._run({"muse_vn": RuntimeError("HTTP 500"), "ani_one_asia": []})
        self.assertIn("1/2 kênh", str(ctx.exception))

    def test_tất_cả_kênh_ok_thì_log_ok(self):
        db, n, out = self._run({
            "muse_vn": [video("crayon shinchan", 1)],
            "ani_one_asia": [video("crayon shinchan", 2, "v2")],
        })
        self.assertTrue(db.logs[-1][2])
        self.assertEqual(db.logs[-1][3], 2)
        self.assertEqual(db.logs[-1][4], "")

    def test_cache_được_lưu_ra_đĩa_và_dùng_lại(self):
        self._run({"muse_vn": [video("crayon shinchan", 1)], "ani_one_asia": []})
        self.assertTrue(os.path.exists(self.cache_path), "phải lưu cache sau mỗi kênh")
        with open(self.cache_path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["version"], match.CACHE_VERSION)
        self.assertIn("crayon shinchan", saved["entries"])

    def test_chạy_LẦN_2_không_search_lại_tên_đã_biết(self):
        per = {"muse_vn": [video("crayon shinchan", 1)], "ani_one_asia": []}
        search_calls = []

        def counting_resolve(name, cache, want_series=True):
            if match.alias_key(name) in cache:            # hành vi thật của resolve
                return cache[match.alias_key(name)], 1.0, "cached"
            search_calls.append(name)
            cache[match.alias_key(name)] = MEDIA          # như resolve thật
            return MEDIA, 1.0, "alias"

        self._run(per, resolve=counting_resolve)
        self.assertEqual(search_calls, ["crayon shinchan"])
        self._run(per, resolve=counting_resolve)          # lần 2
        self.assertEqual(search_calls, ["crayon shinchan"],
                         "lần 2 phải dùng cache, không search lại")

    def test_no_cache_thì_không_đọc_đĩa(self):
        db = FakeDB()
        with patch.object(youtube, "collect_channel",
                          return_value=[video("crayon shinchan", 1)]), \
             patch.object(match, "resolve", return_value=(MEDIA, 1.0, "alias")), \
             patch.object(ingest_main, "_upsert_media",
                          side_effect=lambda DB, m: (
                              [{"anilist_id": 1}], {99468: 7})), \
             patch.object(match, "load_disk_cache") as load:
            with redirect_stdout(io.StringIO()):
                ingest_main.job_youtube(db, use_cache=False)
        load.assert_not_called()

    def test_tên_chưa_khớp_thì_báo_ra_để_thêm_alias(self):
        db, n, out = self._run(
            {"muse_vn": [video("Bộ phim lạ hoắc", 3)], "ani_one_asia": []},
            resolve=lambda name, cache, want_series=True: (None, 0.4, "—"))
        self.assertEqual([u for u in db.upserted if u[0] == "streaming_links"], [])
        self.assertIn("Bộ phim lạ hoắc", out)
        self.assertIn("aliases.json", out)

    def test_dry_run_không_ghi_DB(self):
        db, n, out = self._run(
            {"muse_vn": [video("crayon shinchan", 1)], "ani_one_asia": []}, dry=True)
        self.assertEqual([u for u in db.upserted if u[0] == "streaming_links"], [])

    def test_chỉ_định_một_kênh(self):
        db = FakeDB()
        with patch.object(youtube, "collect_channel",
                          return_value=[video("crayon shinchan", 1)]) as collect, \
             patch.object(match, "resolve", return_value=(MEDIA, 1.0, "alias")), \
             patch.object(ingest_main, "_upsert_media",
                          side_effect=lambda DB, m: ([{"anilist_id": 1}], {99468: 7})):
            with redirect_stdout(io.StringIO()):
                ingest_main.job_youtube(db, only_channel="ani_one_asia")
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(collect.call_args.args[0]["key"], "ani_one_asia")

    def test_kênh_không_khớp_thì_nổ_rõ_ràng(self):
        with self.assertRaises(RuntimeError) as ctx:
            with redirect_stdout(io.StringIO()):
                ingest_main.job_youtube(FakeDB(), only_channel="khong_ton_tai")
        self.assertIn("khong_ton_tai", str(ctx.exception))


class TestCollectChannel(unittest.TestCase):
    def test_lỗi_một_kênh_được_ném_ra_cho_job_xử_lý(self):
        with patch.object(youtube, "fetch_rss", side_effect=RuntimeError("network")):
            with self.assertRaises(RuntimeError):
                youtube.collect_channel(CH1, check_embed=False, verbose=False)

    def test_trả_video_của_riêng_một_kênh(self):
        entries = [dict(video_id="abc", title="Crayon Shin-chan Tập 3", url="u",
                        published="")]
        with patch.object(youtube, "fetch_rss", return_value=entries):
            out = youtube.collect_channel(CH1, check_embed=False, verbose=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["channel"], "muse_vn")
        self.assertEqual(out[0]["episode"], 3)


if __name__ == "__main__":
    unittest.main()
