/**
 * assemble.ts — biến row của Postgres thành DTO mà app Flutter hiểu.
 *
 * ⚠️ ĐÂY LÀ HỢP ĐỒNG API. Nếu đổi tên field ở đây, phải sửa
 *    `app/lib/core/models/anime.dart` cùng lúc, nếu không app sẽ trắng bảng.
 *
 * DTO (xem Anime.fromJson):
 *   id, slug, title, title_vi, title_native, cover, banner, score, year, season,
 *   format, status, episodes_total, genres[], synopsis, is_free,
 *   platforms[{name,url,verified}], episodes[{number,title,video_id,platform,airing_at}],
 *   popularity
 */

export interface AnimeRow {
  id: number;
  slug: string;
  title_romaji: string;
  title_english: string | null;
  title_vi: string | null;
  title_native: string | null;
  cover_url: string | null;
  banner_url: string | null;
  year: number | null;
  season: string | null;
  status: string | null;
  format: string | null;
  episodes_total: number | null;
  score: number | string | null;
  popularity: number | null;
  genres: string[] | null;
  synopsis_vi: string | null;
  synopsis_original?: string | null;
}

export interface EpisodeRow {
  anime_id: number;
  number: number;
  title: string | null;
  airing_at: string | null;
}

export interface LinkRow {
  anime_id: number;
  episode_number: number;
  platform: string;
  region: string;
  url: string;
  kind: string;
  is_verified: boolean;
  source_title?: string | null;
}

export interface EpisodeVideoOptionDto {
  video_id: string;
  platform: string;
  label: string;
}

export interface PlatformDto {
  name: string;
  url: string;
  verified: boolean;
}

export interface EpisodeDto {
  number: number;
  title: string;
  video_id: string | null;
  platform: string | null;
  airing_at: string | null;
  video_options: EpisodeVideoOptionDto[];
}

export interface AnimeDto {
  id: number;
  slug: string;
  title: string;
  title_vi: string | null;
  title_native: string | null;
  cover: string | null;
  banner: string | null;
  score: number | null;
  year: number | null;
  season: string | null;
  format: string | null;
  status: string | null;
  episodes_total: number | null;
  genres: string[];
  synopsis: string;
  is_free: boolean;
  platforms: PlatformDto[];
  episodes: EpisodeDto[];
  popularity: number;
}

const PLATFORM_LABEL: Record<string, string> = {
  crunchyroll: "Crunchyroll",
  netflix: "Netflix",
  bilibili: "Bilibili",
  muse_vn: "Muse VN",
  muse_asia: "Muse Asia",
  ani_one: "Ani-One",
  youtube: "YouTube",
  fpt_play: "FPT Play",
  galaxy_play: "Galaxy Play",
  iqiyi: "iQIYI",
  hidive: "HIDIVE",
  amazon: "Amazon Prime",
};

export function platformLabel(key: string): string {
  return PLATFORM_LABEL[key] ?? key;
}

/** Lấy YouTube video id từ URL (chỉ video official đã kiểm tra embeddable lúc ingest). */
export function youtubeId(url: string): string | null {
  const m = url.match(/(?:v=|youtu\.be\/|\/embed\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

function numOrNull(v: number | string | null): number | null {
  if (v === null) return null;
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : null;
}

export function toAnimeDto(
  row: AnimeRow,
  episodes: EpisodeRow[] = [],
  links: LinkRow[] = [],
): AnimeDto {
  const verified = links.filter((l) => l.is_verified);
  const freeLinks = verified.filter((l) => l.kind === "free_legal");
  const officialLinks = verified.filter((l) => l.kind === "official");

  // Mỗi video official là một URL riêng. Một tập có thể có nhiều bản (vd Vietsub
  // và lồng tiếng); ưu tiên VN, Vietsub rồi video có source_title rõ ràng làm mặc định,
  // nhưng giữ TẤT CẢ lựa chọn để trang chi tiết không làm video nào bị ẩn.
  const regionRank = (r?: string | null) => (r === "VN" ? 0 : r === "AS" ? 1 : 2);
  const versionRank = (title?: string | null) => {
    const t = (title ?? "").toLowerCase();
    if (/lồng\s*tiếng|dub/.test(t)) return 1;
    if (/viet\s*sub|việt\s*sub|phụ\s*đề/.test(t)) return 0;
    return 2;
  };
  const orderedFree = [...freeLinks].sort((a, b) =>
    regionRank(a.region) - regionRank(b.region)
      || versionRank(a.source_title) - versionRank(b.source_title)
      || (a.url ?? "").localeCompare(b.url ?? ""),
  );
  const optionsByEpisode = new Map<number, EpisodeVideoOptionDto[]>();
  for (const l of orderedFree) {
    const vid = l.platform === "youtube" ? youtubeId(l.url) : null;
    if (!vid) continue;
    const t = (l.source_title ?? "").toLowerCase();
    const label = /lồng\s*tiếng|dub/.test(t) ? "Lồng tiếng"
      : /viet\s*sub|việt\s*sub|phụ\s*đề/.test(t) ? "Vietsub"
      : platformLabel(l.platform);
    const options = optionsByEpisode.get(l.episode_number) ?? [];
    if (!options.some((o) => o.video_id === vid)) {
      options.push({ video_id: vid, platform: l.platform, label });
      optionsByEpisode.set(l.episode_number, options);
    }
  }
  const videoByEpisode = new Map<number, EpisodeVideoOptionDto>();
  for (const [number, options] of optionsByEpisode) {
    if (options[0]) videoByEpisode.set(number, options[0]);
  }

  const eps: EpisodeDto[] = episodes.map((e) => {
    const v = videoByEpisode.get(e.number);
    return {
      number: e.number,
      title: e.title ?? "",
      video_id: v?.video_id ?? null,
      platform: v?.platform ?? null,
      airing_at: e.airing_at,
      video_options: optionsByEpisode.get(e.number) ?? [],
    };
  });

  // Một tập có link có thể chưa tồn tại trong bảng lịch phát AniList.
  // Bổ sung vào DTO mà không ghi đè thông tin lịch phát hiện có.
  const existingEpisodes = new Set(eps.map((e) => e.number));
  for (const [number, v] of videoByEpisode) {
    if (number > 0 && !existingEpisodes.has(number)) {
      eps.push({ number, title: "", video_id: v.video_id, platform: v.platform,
        airing_at: null, video_options: optionsByEpisode.get(number) ?? [] });
    }
  }
  eps.sort((a, b) => a.number - b.number);

  // Link cho CẢ BỘ (episode_number = 0, vd "[Bản Lồng Tiếng] One Punch Man - Tập 01-24"
  // là 1 video 24 tập) phải luôn hiện, kể cả khi bộ đã có danh sách tập.
  // Bản cũ chỉ thêm khi `eps.length === 0` → người dùng mất hẳn bản gộp.
  // Đặt CUỐI danh sách để "Xem ngay" vẫn trỏ vào tập 1 (không phải video 24 tập).
  if (videoByEpisode.has(0) && !eps.some((e) => e.number === 0)) {
    const v = videoByEpisode.get(0)!;
    eps.push({
      number: 0,
      title: "Cả bộ",
      video_id: v.video_id,
      platform: v.platform,
      airing_at: null,
      video_options: optionsByEpisode.get(0) ?? [],
    });
  }

  // nền tảng chính thức (dedupe theo tên, giữ link đầu tiên)
  const seenPlatform = new Set<string>();
  const platforms: PlatformDto[] = [];
  for (const l of officialLinks) {
    const name = platformLabel(l.platform);
    if (seenPlatform.has(name)) continue;
    seenPlatform.add(name);
    platforms.push({ name, url: l.url, verified: true });
  }

  return {
    id: row.id,
    slug: row.slug,
    title: row.title_vi || row.title_romaji || row.title_english || `anime-${row.id}`,
    title_vi: row.title_vi,
    title_native: row.title_native,
    cover: row.cover_url,
    banner: row.banner_url,
    score: numOrNull(row.score),
    year: row.year,
    season: row.season,
    format: row.format,
    status: row.status,
    episodes_total: row.episodes_total,
    genres: row.genres ?? [],
    // Ưu tiên bản dịch tiếng Việt; chưa có thì dùng mô tả gốc của AniList
    // (trước đây luôn là "" nên trang chi tiết không có gì để đọc).
    synopsis: row.synopsis_vi || row.synopsis_original || "",
    is_free: freeLinks.length > 0,
    platforms,
    episodes: eps,
    popularity: row.popularity ?? 0,
  };
}

/** Gom row theo anime_id để tránh N+1. */
export function groupByAnime<T extends { anime_id: number }>(
  rows: T[],
): Map<number, T[]> {
  const map = new Map<number, T[]>();
  for (const r of rows) {
    const list = map.get(r.anime_id);
    if (list) list.push(r);
    else map.set(r.anime_id, [r]);
  }
  return map;
}

export interface ShelfDto {
  title: string;
  kind: string;
  ids: number[];
}

export function shelf(title: string, kind: string, ids: (number | null | undefined)[]): ShelfDto {
  const seen = new Set<number>();
  const out: number[] = [];
  for (const id of ids) {
    if (typeof id !== "number" || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return { title, kind, ids: out };
}

/**
 * Giữ lại các tập ĐÃ LÊN SÓNG trong `hours` giờ gần nhất — dùng cho shelf
 * "Tập mới hôm nay".
 *
 * Vì sao phải lọc ở đây chứ không chỉ ở query: DB có **506 tập** (66 bộ) mang
 * `airing_at` ở TƯƠNG LAI (đo 02/11/2026) — lịch phát của bộ đang chiếu được
 * ghi trước. Query cũ `airing_at >= now - 6h` **không có cận trên**, và vì nó
 * sắp xếp GIẢM DẦN nên 40 dòng đầu toàn là tập chưa chiếu (xa nhất lên đầu) ⇒
 * shelf "Tập mới hôm nay" toàn tập của tuần sau.
 *
 * `airing_at` rỗng = không rõ lịch ⇒ coi như đã lên sóng (không giấu bộ đi).
 */
export function recentAired<T extends { airing_at?: string | null }>(
  rows: T[],
  now: Date = new Date(),
  hours = 6,
): T[] {
  const tu = now.getTime() - hours * 3_600_000;
  const den = now.getTime();
  return rows.filter((r) => {
    if (!r.airing_at) return true;
    const t = Date.parse(r.airing_at);
    if (Number.isNaN(t)) return true;
    return t >= tu && t <= den;
  });
}
