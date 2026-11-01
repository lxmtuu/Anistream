"""net.py — gọi HTTP có tự chẩn đoán mạng.

Vì sao cần: đo 02/11/2026 trên máy Windows của chủ dự án, **39/39** bộ Jikan đều
`ConnectTimeout` — job in ra 39 dòng lỗi rồi… **exit 0**. Đó đúng là kiểu hỏng tệ
nhất: "cron xanh mà việc thật không xảy ra".

Nguyên nhân hay gặp nhất của ConnectTimeout hàng loạt trên Windows/ISP Việt Nam là
**IPv6**: hệ điều hành ưu tiên AAAA, nhưng đường IPv6 ra ngoài không thông → mỗi
kết nối treo tới hết timeout. Cách chữa: khi request ĐẦU TIÊN lỗi kết nối, ép
IPv4 rồi thử lại ngay (chỉ áp cho tiến trình hiện tại).

Ở đây chỉ làm đúng 2 việc:
  · thử lại khi lỗi KẾT NỐI (kèm nhảy sang IPv4),
  · hết lượt → raise `NetworkError` với gợi ý cụ thể để người vận hành sửa.
"""
import socket
from typing import Any, Dict, Optional

import requests
import urllib3.util.connection as urllib3_connection

_ipv4_forced = False


class NetworkError(RuntimeError):
    """Không kết nối được (khác với HTTP 4xx/5xx — cái đó do tầng gọi xử lý)."""


def force_ipv4() -> bool:
    """Ép mọi kết nối trong tiến trình dùng IPv4. Trả True nếu vừa bật."""
    global _ipv4_forced
    if _ipv4_forced:
        return False
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
    _ipv4_forced = True
    return True


def ipv4_forced() -> bool:
    return _ipv4_forced


def get(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 25,
    retries: int = 3,
    session: Optional[Any] = None,
    verbose: bool = True,
) -> requests.Response:
    """GET có thử lại + tự chuyển IPv4 khi lỗi kết nối.

    Lỗi HTTP (429/5xx/404) KHÔNG được xử lý ở đây — trả nguyên response để tầng
    trên quyết định (Jikan cần tôn trọng `Retry-After`, AniList cần retry 429).
    """
    do = (session or requests).get
    last: Optional[Exception] = None

    for attempt in range(retries):
        try:
            return do(url, params=params or {}, headers=headers or {}, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last = e
            # Lần lỗi ĐẦU TIÊN: rất có thể do IPv6 → ép IPv4 rồi thử lại ngay.
            if force_ipv4() and verbose:
                print(f"  … không kết nối được {url} ({type(e).__name__}) "
                      f"→ thử lại bằng IPv4")
            elif verbose:
                print(f"  … lỗi kết nối {url} ({type(e).__name__}), "
                      f"thử lại {attempt + 1}/{retries}")
            if attempt == retries - 1:
                break

    raise NetworkError(
        f"không kết nối được tới {url} sau {retries} lần: "
        f"{type(last).__name__}: {str(last)[:160]}\n"
        "  Kiểm tra nhanh (Git Bash): curl -4 -sS -m 20 -o /dev/null -w '%{http_code}\\n' "
        f"{url}\n"
        "  · 000/SSL error → mạng/ISP chặn hoặc proxy công ty cần cấu hình HTTPS_PROXY\n"
        "  · 200 → mạng ổn, chạy lại lệnh"
    )
