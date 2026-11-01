/**
 * GET /functions/v1/home
 *
 * Toàn bộ dữ liệu trang chủ trong MỘT request (app mở < 1.2s):
 *   shelves: xem ngay (free) · tập mới · mùa này · điểm cao
 *   schedule: 7 ngày tới (để tab Lịch phát dùng lại payload, không gọi thêm)
 *
 * Cache: 300s ở CDN → 1.000 người dùng cùng lúc cũng chỉ tốn vài query.
 */
import { ok, withGuard } from "../_shared/respond.ts";
import { adminClient } from "../_shared/supabase.ts";
import {
  AnimeRow,
  EpisodeRow,
  groupByAnime,
  LinkRow,
  shelf,
  toAnimeDto,
} from "../_shared/assemble.ts";
import { currentSeason, selectAll } from "../_shared/query.ts";

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

Deno.serve(
  withGuard(async (_req: Request) => {
    const sb = adminClient();
    const now = new Date();
    const nowIso = now.toISOString();
    const recentIso = new Date(now.getTime() - 6 * HOUR).toISOString();
    const weekIso = new Date(now.getTime() + 7 * DAY).toISOString();
    const season = currentSeason(now);
    const year = now.getUTCFullYear();

    // ── 1. lấy id cho từng shelf (query nhẹ, chỉ select id) ──
    const [recentEp, seasonRes, topRes, freeRes, schedRes] = await Promise.all([
      sb
        .from("episodes")
        .select("anime_id, number, airing_at")
        .gte("airing_at", recentIso)
        // giảm dần để 40 dòng là 40 tập MỚI nhất (tăng dần sẽ cắt mất tập mới)
        .order("airing_at", { ascending: false })
        .limit(40),

      sb
        .from("anime")
        .select("id")
        .eq("season", season)
        .eq("year", year)
        .eq("is_published", true)
        .order("popularity", { ascending: false })
        .limit(20),

      sb
        .from("anime")
        .select("id")
        .eq("is_published", true)
        .order("score", { ascending: false, nullsFirst: false })
        .limit(20),

      // KHÔNG đặt limit thấp ở đây: DB đã có 485 link free_legal, `limit(300)`
      // khiến vài bộ miễn phí biến mất khỏi shelf "Xem ngay" một cách ngẫu nhiên.
      sb
        .from("streaming_links")
        .select("anime_id")
        .eq("kind", "free_legal")
        .eq("is_verified", true)
        .order("anime_id", { ascending: true })
        .limit(2000),

      sb
        .from("episodes")
        .select("anime_id, number, airing_at")
        .gte("airing_at", nowIso)
        .lte("airing_at", weekIso)
        .order("airing_at", { ascending: true })
        .limit(60),
    ]);

    for (const [name, res] of Object.entries({
      recentEp,
      seasonRes,
      topRes,
      freeRes,
      schedRes,
    })) {
      if (res.error) throw new Error(`${name}: ${res.error.message}`);
    }

    const recentRows = (recentEp.data ?? []) as Pick<
      EpisodeRow,
      "anime_id" | "number" | "airing_at"
    >[];
    const scheduleRows = (schedRes.data ?? []) as {
      anime_id: number;
      number: number;
      airing_at: string;
    }[];

    const freeIds: number[] = [];
    for (const r of (freeRes.data ?? []) as { anime_id: number }[]) {
      if (!freeIds.includes(r.anime_id)) freeIds.push(r.anime_id);
    }

    const seasonIds = ((seasonRes.data ?? []) as { id: number }[]).map((r) => r.id);
    const topIds = ((topRes.data ?? []) as { id: number }[]).map((r) => r.id);
    const recentIds = recentRows.map((r) => r.anime_id);

    // ── 2. gom id duy nhất, giới hạn để response không phình ──
    const ids = [...new Set([...freeIds, ...recentIds, ...seasonIds, ...topIds])].slice(
      0,
      60,
    );
    if (ids.length === 0) {
      return ok(
        { generated_at: nowIso, anime: [], shelves: [], schedule: [] },
        { ttl: 60, empty: true },
        { maxAge: 60 },
      );
    }

    // ── 3. lấy dữ liệu đầy đủ cho các anime đó (3 query song song) ──
    // `limit(1200)` thực tế chỉ trả 1000 dòng (PostgREST Max Rows) → bộ nằm sau
    // dòng 1000 hiện 0 tập. `selectAll` tự đọc hết trang; order phải ỔN ĐỊNH.
    const [animeRes, episodeRows, linkRows] = await Promise.all([
      sb.from("anime").select("*").in("id", ids),
      selectAll<EpisodeRow>((from, to) =>
        sb
          .from("episodes")
          .select("anime_id, number, title, airing_at")
          .in("anime_id", ids)
          .order("anime_id", { ascending: true })
          .order("number", { ascending: true })
          .range(from, to)
      ),
      selectAll<LinkRow>((from, to) =>
        sb
          .from("streaming_links")
          .select("anime_id, episode_number, platform, region, url, kind, is_verified")
          .in("anime_id", ids)
          .eq("is_verified", true)
          .order("anime_id", { ascending: true })
          .order("episode_number", { ascending: true })
          .range(from, to)
      ),
    ]);

    if (animeRes.error) throw new Error(`anime: ${animeRes.error.message}`);

    const animeRows = (animeRes.data ?? []) as AnimeRow[];
    const epsByAnime = groupByAnime(episodeRows);
    const linksByAnime = groupByAnime(linkRows);

    // sắp xếp theo mức phổ biến để shelf "xem ngay" có bộ hot trước
    animeRows.sort((a, b) => (b.popularity ?? 0) - (a.popularity ?? 0));

    const anime = animeRows.map((row) =>
      toAnimeDto(row, epsByAnime.get(row.id) ?? [], linksByAnime.get(row.id) ?? []),
    );

    // chỉ giữ id thật sự tồn tại (shelf có thể trỏ tới bộ đã unpublish)
    const valid = new Set(anime.map((a) => a.id));
    const keep = (list: number[]) => list.filter((id) => valid.has(id));

    return ok(
      {
        generated_at: nowIso,
        season: { season, year },
        anime,
        shelves: [
          shelf("Xem ngay — miễn phí, hợp pháp", "free", keep(freeIds)),
          shelf("Tập mới hôm nay", "new_episodes", keep(recentIds)),
          shelf(`Mùa ${season} ${year}`, "season", keep(seasonIds)),
          shelf("Điểm cao nhất", "top", keep(topIds)),
        ].filter((s) => s.ids.length > 0),
        schedule: scheduleRows
          .filter((r) => valid.has(r.anime_id))
          .map((r) => ({
            anime_id: r.anime_id,
            episode: r.number,
            airing_at: r.airing_at,
          })),
      },
      { ttl: 300, count: anime.length },
      { maxAge: 300, browserMaxAge: 60 },
    );
  }),
);
