/**
 * GET /functions/v1/search?q=frieren&genre=Action&year=2026&season=FALL&sort=popular&page=1&limit=24
 *
 * - `q` rỗng + không có filter → 400 (tránh query full table)
 * - search mờ dùng index GIN trigram có sẵn trong db/schema.sql
 * - cache 600s (kết quả tìm kiếm đổi rất chậm)
 */
import { fail, ok, withGuard } from "../_shared/respond.ts";
import { adminClient } from "../_shared/supabase.ts";
import {
  AnimeRow,
  EpisodeRow,
  groupByAnime,
  LinkRow,
  toAnimeDto,
} from "../_shared/assemble.ts";
import {
  ilikeSafe,
  isRangeNotSatisfiable,
  resolveSort,
  selectAll,
  toInt,
} from "../_shared/query.ts";

Deno.serve(
  withGuard(async (req: Request) => {
    const url = new URL(req.url);
    const q = (url.searchParams.get("q") ?? "").trim();
    const genre = url.searchParams.get("genre");
    const year = url.searchParams.get("year");
    const season = url.searchParams.get("season");
    const sort = resolveSort(url.searchParams.get("sort"));
    const page = toInt(url.searchParams.get("page"), 1, 1, 50);
    const limit = toInt(url.searchParams.get("limit"), 24, 1, 48);

    if (!q && !genre && !year && !season) {
      return fail("bad_request", "Cần ít nhất 1 tham số: q, genre, year hoặc season");
    }
    if (q.length > 60) {
      return fail("bad_request", "q quá dài (tối đa 60 ký tự)");
    }

    const sb = adminClient();
    const from = (page - 1) * limit;
    const like = q ? `%${ilikeSafe(q)}%` : null;

    // Builder của supabase-js chỉ dùng được MỘT lần → gói phần filter vào hàm để
    // dựng lại khi cần đếm tổng (nhánh trang vượt quá cuối).
    const buildQuery = (head = false) => {
      let b = sb
        .from("anime")
        .select(
          "id, slug, title_romaji, title_english, title_vi, title_native, cover_url, " +
            "banner_url, year, season, status, format, episodes_total, score, " +
            "popularity, genres, synopsis_vi, synopsis_original",
          { count: "exact", head },
        )
        .eq("is_published", true);
      if (like) {
        b = b.or(
          [
            `title_romaji.ilike.${like}`,
            `title_english.ilike.${like}`,
            `title_vi.ilike.${like}`,
            `title_native.ilike.${like}`,
          ].join(","),
        );
      }
      if (genre) b = b.contains("genres", [genre]);
      if (year) b = b.eq("year", toInt(year, 0, 1950, 2100));
      if (season) b = b.eq("season", season.toUpperCase());
      return b;
    };

    const res = await buildQuery()
      .order(sort.column, { ascending: sort.ascending, nullsFirst: false })
      .range(from, from + limit - 1);

    let rows: AnimeRow[] = [];
    let total = 0;

    if (res.error) {
      if (!isRangeNotSatisfiable(res.error)) throw new Error(res.error.message);
      // Vuốt quá trang cuối → trang rỗng, nhưng `total` vẫn phải đúng.
      const counted = await buildQuery(true);
      if (counted.error) throw new Error(counted.error.message);
      total = counted.count ?? 0;
    } else {
      rows = (res.data ?? []) as unknown as AnimeRow[];
      total = res.count ?? rows.length;
    }

    const ids = rows.map((r) => r.id);

    let epsByAnime = new Map<number, EpisodeRow[]>();
    let linksByAnime = new Map<number, LinkRow[]>();

    if (ids.length > 0) {
      // 48 bộ × tối đa 180 tập (One Piece, Xian Ni) vượt xa 1000 dòng mà
      // PostgREST trả về → phải đọc hết trang, không dùng limit cứng.
      const [episodeRows, linkRows] = await Promise.all([
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
      epsByAnime = groupByAnime(episodeRows);
      linksByAnime = groupByAnime(linkRows);
    }

    const items = rows.map((r) =>
      toAnimeDto(r, epsByAnime.get(r.id) ?? [], linksByAnime.get(r.id) ?? []),
    );

    return ok(
      {
        items,
        page,
        limit,
        total,
        has_more: total > from + items.length,
      },
      { ttl: 600, query: q },
      { maxAge: 600, browserMaxAge: 120 },
    );
  }),
);
