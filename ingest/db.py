"""
db.py — lớp ghi dữ liệu xuống Supabase (PostgREST) + chế độ dry-run.

Không dùng SDK để giữ dependency nhẹ (chỉ cần `requests`).
Khi SUPABASE_URL/SERVICE_KEY trống hoặc DRY_RUN=1 → chỉ in ra số liệu, không ghi.
"""
from typing import Iterable, Dict, List, Any
import requests

from . import config


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
    def upsert(self, table: str, rows: Iterable[Dict], on_conflict: str) -> List[Dict]:
        rows = [r for r in rows if r]
        if not rows:
            return []
        if self.dry:
            print(f"  [dry-run] upsert {table}: {len(rows)} rows "
                  f"(conflict: {on_conflict})")
            return rows
        out = []
        # chia lô 200 rows để không vượt giới hạn payload
        for i in range(0, len(rows), 200):
            batch = rows[i:i + 200]
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
            out.extend(r.json())
        return out

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
        """Ghi audit vào ingest_runs — để biết cron có chạy hay không."""
        if self.dry:
            print(f"  [dry-run] ingest_runs ← {source}/{job} ok={ok} rows={rows}"
                  + (f" err={error[:120]}" if error else ""))
            return
        try:
            requests.post(
                f"{self.url}/rest/v1/ingest_runs",
                json={"source": source, "job": job, "ok": ok,
                      "rows_upserted": rows, "finished_at": "now()", "error": error or None},
                headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json",
                         "Prefer": "return=minimal"},
                timeout=config.HTTP_TIMEOUT,
            )
        except Exception as e:      # audit không được làm chết job
            print(f"  ! không ghi được ingest_runs: {e}")
