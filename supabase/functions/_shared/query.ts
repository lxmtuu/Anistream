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

/** Escape ký tự đặc biệt cho filter `ilike` của PostgREST. */
export function ilikeSafe(q: string): string {
  return q.replace(/[%_\\]/g, (c) => `\\${c}`).slice(0, 60);
}
