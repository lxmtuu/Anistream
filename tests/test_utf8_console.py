"""Console Windows (cp1252/cp437) làm ingest CHẾT khi stdout là đường ống.

Lỗi thật 03/11/2026 trên Git Bash:
    python3 -m ingest.main youtube --deep ... | tee youtube.log
    UnicodeEncodeError: 'charmap' codec can't encode character '\u1eac'

Tiêu đề job có chữ Việt ("GHI THẬT"), mà cp1252 không có `Ậ` ⇒ chết trước khi
lấy được video nào. Test này canh `_utf8_stdout` và chạy thật qua subprocess với
PYTHONIOENCODING=cp1252.
"""
import os
import subprocess
import sys
import unittest

from ingest import main as ingest_main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeStream:
    def __init__(self, has_reconfigure=True):
        self.calls = []
        self._has = has_reconfigure

    def reconfigure(self, **kw):
        if not self._has:
            raise AttributeError("no reconfigure")
        self.calls.append(kw)

    def write(self, s):
        return len(s)


class TestUtf8Stdout(unittest.TestCase):

    def test_ep_utf8_cho_ca_stdout_va_stderr(self):
        out, err = FakeStream(), FakeStream()
        old = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            ingest_main._utf8_stdout()
        finally:
            sys.stdout, sys.stderr = old
        for s in (out, err):
            self.assertEqual(s.calls[0]["encoding"], "utf-8")
            self.assertEqual(s.calls[0]["errors"], "replace",
                             "phải 'replace' — thà hiện ? còn hơn chết cả job")

    def test_stream_khong_co_reconfigure_khong_no(self):
        out = FakeStream(has_reconfigure=False)
        old = sys.stdout
        sys.stdout = out
        try:
            ingest_main._utf8_stdout()      # không được ném
        finally:
            sys.stdout = old

    def test_subprocess_pipe_voi_cp1252_khong_chet(self):
        """Đúng cảnh thật: stdout là pipe + console Windows cp1252."""
        code = (
            "import sys;"
            "sys.stdout.reconfigure(encoding='cp1252');"
            "from ingest import main;"
            "main._utf8_stdout();"
            "print('GHI THẬT vào Supabase · Ậ ệ ộ');"
        )
        env = dict(os.environ, PYTHONPATH=ROOT, PYTHONIOENCODING="")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertIn("GHI THẬT", r.stdout.decode("utf-8", "replace"))

    def test_tieu_de_job_khong_con_ky_tu_chet(self):
        for s in ("GHI THẬT vào Supabase", "DRY-RUN (không ghi DB)"):
            s.encode("cp1252", "replace")       # không được ném


if __name__ == "__main__":
    unittest.main()
