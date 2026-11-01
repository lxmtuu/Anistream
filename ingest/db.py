"""
db.py — lớp ghi dữ liệu xuống Supabase (PostgREST) + chế độ dry-run.

Không dùng SDK để giữ dependency nhẹ (chỉ cần `requests`).
Khi SUPABASE_URL/SERVICE_KEY trống hoặc DRY_RUN=1 → chỉ in ra số liệu, không ghi.
"""
import datetime as dt
from typing import Iterable, Dict, List, Any

import requests

from . import config

BATCH = 200          # số row mỗi request PostgREST



class DB:
    def __init__(self, dry_run: bool | None = None):
        self.dry = config.DRY_RUN if dry_run is None else dry_run
        self.url = config.SUPABASE_URL
        self.key = config.SUPABASE_SERVICE_KEY
        if not self.dry and not config.has_supabase():
            raise RuntimeError(
                "Thiếu SUPABASE_URL / SUPABASE_SERVICE_KEY.\n"
                "  → Điền vào .env (xem .env.example) hoặc chạy với --dry-run."
            )

    # ── core ───────────────────────────────────────────────
    def upsert(self, table: str, rows: Iterable[Dict], on_conflict: str,
               fallback_per_row: bool = False) -> List[Dict]:
        """Upsert theo lô. Trả về các row đã ghi (khi không dry-run).

        `fallback_per_row=True`: nếu cả lô bị từ chối, thử lại TỪNG row và bỏ qua
        row lỗi thay vì làm chết cả job. Cần cho `streaming_links` vì bảng này có
        thêm unique index `(platform, url)`: một video bị gán cho 2 anime khác nhau
        (do alias đổi giữa các lần chạy) sẽ làm cả lô 200 row trả 409 và job C
        chết — dù chỉ 1 row sai.
        """
        rows = [r for r in rows if r]
        if not rows:
            return []
        if self.dry:
            print(f"  [dry-run] upsert {table}: {len(rows)} rows "
                  f"(conflict: {on_conflict})")
            return rows

        out: List[Dict] = []
        failed: List[str] = []

        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            try:
                out.extend(self._post_batch(table, batch, on_conflict))
            except RuntimeError as e:
                if not fallback_per_row or len(batch) == 1:
                    raise
                print(f"  ! lô {i}–{i + len(batch) - 1} của {table} lỗi → "
                      f"thử lại từng row: {str(e)[:160]}")
                for row in batch:
                    try:
                        out.extend(self._post_batch(table, [row], on_conflict))
                    except RuntimeError as row_err:
                        failed.append(f"{row.get('url') or row}: {str(row_err)[:120]}")

        if failed:
            print(f"  ! {len(failed)}/{len(rows)} row {table} bị bỏ qua:")
            for f in failed[:10]:
                print(f"      - {f}")
            if len(failed) > 10:
                print(f"      … và {len(failed) - 10} row nữa")
        return out

    def _post_batch(self, table: str, batch: List[Dict], on_conflict: str) -> List[Dict]:
        r = requests.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            json=batch,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            timeout=config.HTTP_TIMEOUT * 2,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"upsert {table} lỗi {r.status_code}: {r.text[:500]}")
        return r.json()

    def patch(self, table: str, filters: Dict[str, Any], values: Dict[str, Any]) -> int:
        """UPDATE một phần (PATCH) — dùng khi chỉ muốn sửa vài cột.

        Vì sao không dùng `upsert`: upsert cần payload có đủ cột NOT NULL (slug,
        title_romaji) và dễ ghi đè nhầm dữ liệu khác. PATCH chỉ đụng đúng cột
        truyền vào, an toàn hơn cho việc làm giàu dữ liệu (title_vi, synopsis_vi…).

        Trả số dòng đã sửa (PostgREST trả 204 khi `return=minimal` → 0..n không
        biết chính xác, nên trả 1 khi thành công để job đếm được).
        """
        if not values:
            return 0
        if self.dry:
            print(f"  [dry-run] patch {table} {filters} ← {list(values)}")
            return 0
        params = {k: f"eq.{v}" for k, v in filters.items()}
        r = requests.patch(
            f"{self.url}/rest/v1/{table}",
            params=params,
            json=values,
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code not in (200, 204):
            raise RuntimeError(f"patch {table} lỗi {r.status_code}: {r.text[:300]}")
        return 1

    def select(self, table: str, query: str) -> List[Dict]:
        if self.dry:
            return []
        r = requests.get(
            f"{self.url}/rest/v1/{table}?{query}",
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
            timeout=config.HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def log_ingest(self, source: str, job: str, ok: bool, rows: int, error: str = ""):
        """Ghi audit vào ingest_runs — để biết cron có chạy hay không.

        Lưu ý: `finished_at` phải là TIMESTAMP THẬT. Trước đây gửi chuỗi "now()"
        → Postgres báo `invalid input syntax for type timestamp` (400), nhưng vì
        không kiểm tra response nên lỗi hoàn toàn im lặng: bảng `ingest_runs`
        không bao giờ có dòng nào, và không ai biết cron có chạy hay không.
        """
        if self.dry:
            print(f"  [dry-run] ingest_runs ← {source}/{job} ok={ok} rows={rows}"
                  + (f" err={error[:120]}" if error else ""))
            return
        try:
            r = requests.post(
                f"{self.url}/rest/v1/ingest_runs",
                json={
                    "source": source,
                    "job": job,
                    "ok": ok,
                    "rows_upserted": rows,
                    "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "error": error or None,
                },
                headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json",
                         "Prefer": "return=minimal"},
                timeout=config.HTTP_TIMEOUT,
            )
            if r.status_code not in (200, 201, 204):
                print(f"  ! ingest_runs từ chối ({r.status_code}): {r.text[:200]}")
        except Exception as e:      # audit không được làm chết job
            print(f"  ! không ghi được ingest_runs: {e}")
