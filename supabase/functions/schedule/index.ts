/**
 * GET /functions/v1/schedule?from=2026-11-01&to=2026-11-08&limit=200
 *
 * Lịch phát — dùng cho tab "Lịch phát" và cho job push notification.
 * Mặc định: từ bây giờ → +7 ngày.
 *
 * `?alerts=true` → chỉ trả những bộ có ít nhất 1 thiết bị đang theo dõi
 * (nguồn: push_subscriptions.anime_ids — xem supabase/functions/push/).
 */
import { fail, ok, withGuard } from "../_shared/respond.ts";
import { adminClient } from "../_shared/supabase.ts";
import { platformLabel, youtubeId } from "../_shared/assemble.ts";
import { parseDate, toInt } from "../_shared/query.ts";

const DAY = 86_400_000;

Deno.serve(
  withGuard(async (req: Request) => {
    const url = new URL(req.url);
    const now = new Date();
    const from = parseDate(url.searchParams.get("from"), new Date(now.getTime() - 2 * DAY));
    const to = parseDate(url.searchParams.get("to"), new Date(now.getTime() + 7 * DAY));
    const limit = toInt(url.searchParams.get("limit"), 200, 1, 500);
    const alertsOnly = url.searchParams.get("alerts") === "true";

    if (to.getTime() <= from.getTime()) {
      return fail("bad_request", "`to` phải sau `from`");
    }
    if (to.getTime() - from.getTime() > 31 * DAY) {
      return fail("bad_request", "Khoảng thời gian tối đa 31 ngày");
    }

    const sb = adminClient();

    // anime_ids có người theo dõi (nếu chỉ lấy alerts)
    let watchedIds: number[] | null = null;
    if (alertsOnly) {
      const { data: subs, error: subErr } = await sb
        .from("push_subscriptions")
        .select("anime_ids")
        .eq("is_active", true)
        .limit(5000);
      if (subErr) throw new Error(subErr.message);
      const set = new Set<number>();
      for (const row of (subs ?? []) as { anime_ids: number[] | null }[]) {
        for (const id of row.anime_ids ?? []) set.add(id);
      }
      watchedIds = [...set];
      if (watchedIds.length === 0) {
        return ok({ slots: [], from: from.toISOString(), to: to.toISOString() },
          { ttl: 60, empty: true }, { maxAge: 60 });
      }
    }

    let q = sb
      .from("episodes")
      .select("anime_id, number, title, airing_at, anime:anime!inner(" +
        "id, slug, title_romaji, title_english, title_vi, cover_url, score, is_published)")
      .gte("airing_at", from.toISOString())
      .lte("airing_at", to.toISOString())
      .order("airing_at", { ascending: true })
      .limit(limit);

    const filterIds = watchedIds;
    if (filterIds && filterIds.length > 0) q = q.in("anime_id", filterIds);

    const { data, error } = await q;
    if (error) throw new Error(error.message);

    type Row = {
      anime_id: number;
      number: number;
      title: string | null;
      airing_at: string;
      anime: {
        id: number;
        slug: string;
        title_romaji: string;
        title_english: string | null;
        title_vi: string | null;
        cover_url: string | null;
        score: number | string | null;
        is_published: boolean;
      };
    };

    const rows = ((data ?? []) as unknown as Row[]).filter((r) => r.anime?.is_published);
    const ids = [...new Set(rows.map((r) => r.anime_id))];

    // link free để app biết bấm ▶ được hay không
    const freeByAnime = new Map<number, { videoId: string | null; platform: string }>();
    if (ids.length > 0) {
      const { data: links } = await sb
        .from("streaming_links")
        .select("anime_id, episode_number, platform, url, kind, is_verified, source_title")
        .in("anime_id", ids)
        .eq("kind", "free_legal")
        .eq("is_verified", true)
        .limit(1000);
      for (const l of (links ?? []) as {
        anime_id: number;
        platform: string;
        url: string;
      }[]) {
        freeByAnime.set(l.anime_id, {
          videoId: l.platform === "youtube" ? youtubeId(l.url) : null,
          platform: platformLabel(l.platform),
        });
      }
    }

    return ok(
      {
        from: from.toISOString(),
        to: to.toISOString(),
        slots: rows.map((r) => ({
          anime_id: r.anime_id,
          slug: r.anime.slug,
          title: r.anime.title_vi || r.anime.title_romaji || r.anime.title_english,
          cover: r.anime.cover_url,
          score: r.anime.score === null ? null : Number(r.anime.score),
          episode: r.number,
          episode_title: r.title,
          airing_at: r.airing_at,
          free: freeByAnime.has(r.anime_id),
          free_platform: freeByAnime.get(r.anime_id)?.platform ?? null,
          video_id: freeByAnime.get(r.anime_id)?.videoId ?? null,
        })),
      },
      { ttl: 300, count: rows.length },
      { maxAge: 300, browserMaxAge: 60 },
    );
  }),
);
