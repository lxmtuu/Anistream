/**
 * GET /functions/v1/anime?slug=sousou-no-frieren
 * GET /functions/v1/anime?id=154587
 *
 * Chi tiết 1 bộ: episodes (kèm video_id official) + nền tảng chính thức +
 * quan hệ (cùng thể loại) để hiển thị "Liên quan".
 *
 * Dùng khi người dùng vào deep link /anime/<slug> mà chưa load /home.
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
import { toInt } from "../_shared/query.ts";

const CARD_COLUMNS =
  "id, slug, title_romaji, title_english, title_vi, title_native, cover_url, " +
  "banner_url, year, season, status, format, episodes_total, score, popularity, " +
  "genres, synopsis_vi, synopsis_original";

Deno.serve(
  withGuard(async (req: Request) => {
    const url = new URL(req.url);
    const slug = url.searchParams.get("slug");
    const idRaw = url.searchParams.get("id");

    if (!slug && !idRaw) {
      return fail("bad_request", "Cần ?slug= hoặc ?id=");
    }

    const sb = adminClient();

    let base = sb.from("anime").select(CARD_COLUMNS);
    base = slug ? base.eq("slug", slug) : base.eq("id", toInt(idRaw, 0, 1, 2_000_000_000));

    const { data: found, error } = await base.limit(1);
    if (error) throw new Error(error.message);

    const rows = (found ?? []) as unknown as AnimeRow[];
    if (rows.length === 0) return fail("not_found", "Không tìm thấy anime");
    const row = rows[0];

    const [epRes, linkRes] = await Promise.all([
      sb
        .from("episodes")
        .select("anime_id, number, title, airing_at")
        .eq("anime_id", row.id)
        .order("number", { ascending: true })
        .limit(600),
      sb
        .from("streaming_links")
        .select("anime_id, episode_number, platform, region, url, kind, is_verified")
        .eq("anime_id", row.id)
        .eq("is_verified", true)
        .limit(600),
    ]);
    if (epRes.error) throw new Error(epRes.error.message);
    if (linkRes.error) throw new Error(linkRes.error.message);

    const detail = toAnimeDto(
      row,
      (epRes.data ?? []) as EpisodeRow[],
      (linkRes.data ?? []) as LinkRow[],
    );

    // ── liên quan: cùng thể loại, ưu tiên điểm cao ──
    const relatedGenre = detail.genres[0];
    let related: unknown[] = [];
    if (relatedGenre) {
      const { data: rel } = await sb
        .from("anime")
        .select(CARD_COLUMNS)
        .contains("genres", [relatedGenre])
        .neq("id", row.id)
        .eq("is_published", true)
        .order("popularity", { ascending: false })
        .limit(10);

      const relRows = (rel ?? []) as unknown as AnimeRow[];
      const relIds = relRows.map((r) => r.id);
      const links = relIds.length
        ? await sb
          .from("streaming_links")
          .select("anime_id, episode_number, platform, region, url, kind, is_verified")
          .in("anime_id", relIds)
          .eq("is_verified", true)
          .limit(400)
        : { data: [] as LinkRow[] };

      const byAnime = groupByAnime((links.data ?? []) as LinkRow[]);
      related = relRows.map((r) => toAnimeDto(r, [], byAnime.get(r.id) ?? []));
    }

    return ok(
      { anime: detail, related },
      { ttl: 3600 },
      { maxAge: 3600, browserMaxAge: 300 },
    );
  }),
);
