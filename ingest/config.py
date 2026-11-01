"""
config.py — cấu hình từ biến môi trường (.env)
"""
import os

def _load_dotenv(path=".env"):
    """Đọc .env đơn giản, không cần thư viện ngoài."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# Kênh YouTube bật ingest. Mặc định CHỈ Muse Việt Nam (kênh có bản Việt sub/lồng
# tiếng và là nguồn chính của app). Thêm kênh khác:
#   YOUTUBE_CHANNELS=muse_vn,ani_one_asia
YOUTUBE_CHANNELS = [
    k.strip() for k in os.environ.get("YOUTUBE_CHANNELS", "muse_vn").split(",")
    if k.strip()
]

DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
USER_AGENT = "AniStreamIngest/1.0 (+https://github.com/yourname/anistream)"
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "25"))


def has_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
