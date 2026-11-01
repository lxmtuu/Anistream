/** query.ts — tiện ích tính mùa, parse tham số, chặn input bẩn. */

export type Season = "WINTER" | "SPRING" | "SUMMER" | "FALL";

/** Mùa tính theo UTC (AniList/TMDB đều dùng UTC — đừng tính theo giờ VN). */
export function currentSeason(d: Date = new Date()): Season {
  const m = d.getUTCMonth() + 1;
  if (m <= 3) return "WINTER";
  if (m <= 6) return "SPRING";
  if (m <= 9) return "SUMMER";
  return "FALL";
}

export function toInt(
  raw: string | null,
  fallback: number,
  min: number,
  max: number,
): number {
  const n = raw === null ? NaN : Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

export function parseDate(raw: string | null, fallback: Date): Date {
  if (!raw) return fallback;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? fallback : d;
}

/** Chỉ cho phép các cột sort đã biết — tránh injection qua tham số. */
const SORTS: Record<string, { column: string; ascending: boolean }> = {
  popular: { column: "popularity", ascending: false },
  top: { column: "score", ascending: false },
  newest: { column: "year", ascending: false },
  oldest: { column: "year", ascending: true },
  title: { column: "title_romaji", ascending: true },
};

export function resolveSort(raw: string | null) {
  return SORTS[raw ?? "popular"] ?? SORTS.popular;
}

/**
 * PostgREST trả 416 kèm code `PGRST103` ("Requested range not satisfiable") khi
 * `offset` vượt quá tổng số dòng — chuyện thường gặp khi người dùng vuốt tới quá
 * trang cuối (infinite scroll). Đây KHÔNG phải lỗi hệ thống: phải trả trang rỗng
 * kèm `total` đúng, không được để thành HTTP 500.
 *
 * Thực tế đã bắt được lỗi này: `GET /search?q=a&page=2` trên DB trống → 500.
 */
export function isRangeNotSatisfiable(
  err: { code?: string; message?: string; details?: string } | null | undefined,
): boolean {
  if (!err) return false;
  return err.code === "PGRST103" ||
    /range not satisfiable/i.test(`${err.message ?? ""} ${err.details ?? ""}`);
}

/** Escape ký tự đặc biệt cho filter `ilike` của PostgREST. */
export function ilikeSafe(q: string): string {
  return q.replace(/[%_\\]/g, (c) => `\\${c}`).slice(0, 60);
}

/**
 * Supabase/PostgREST cắt MỌI response ở "Max Rows" (mặc định 1000) — `.limit(1200)`
 * vẫn chỉ trả 1000 dòng. Với danh sách tập/link của ~60 bộ thì 1000 dòng là quá
 * ít: bộ nằm sau dòng 1000 sẽ hiện 0 tập dù dữ liệu có thật.
 */
export const MAX_ROWS = 1000;

/**
 * Đọc hết các trang cho tới khi gặp trang ngắn.
 *
 * `make(from, to)` phải dựng query có `.order(...)` ỔN ĐỊNH (khoá duy nhất), nếu
 * không các trang có thể chồng nhau/thiếu dòng.
 */
export async function selectAll<T>(
  // Kiểu để lỏng (`unknown`) vì PostgREST trả union success/failure — ép kiểu
  // chặt ở đây chỉ làm TypeScript cãi nhau mà không thêm an toàn.
  make: (from: number, to: number) => PromiseLike<unknown>,
  maxRows = 5000,
): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; from < maxRows; from += MAX_ROWS) {
    const res = (await make(from, from + MAX_ROWS - 1)) as {
      data?: T[] | null;
      error?: { message?: string } | null;
    };
    if (res?.error) throw new Error(res.error.message ?? "query lỗi");
    const rows = res?.data ?? [];
    out.push(...rows);
    if (rows.length < MAX_ROWS) break;
  }
  return out;
}
