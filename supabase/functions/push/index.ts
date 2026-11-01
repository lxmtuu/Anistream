/**
 * POST /functions/v1/push?window=25&dry_run=false
 *
 * Cron gọi mỗi 10–15 phút: tìm tập VỪA phát (mặc định 25 phút gần nhất),
 * gửi push tới những thiết bị có bộ đó trong `push_subscriptions.anime_ids`,
 * rồi ghi `sent_episode_pushes` để KHÔNG BAO GIỜ gửi trùng.
 *
 * Bảo vệ: header `x-cron-secret` phải khớp secret PUSH_CRON_SECRET.
 * Nếu chưa set secret → chỉ cho chạy dry_run (an toàn mặc định).
 *
 * Test nhanh:
 *   curl -X POST "$BASE/push?dry_run=true" -H "x-cron-secret: $PUSH_CRON_SECRET"
 */
import { fail, ok, withGuard } from "../_shared/respond.ts";
import { adminClient } from "../_shared/supabase.ts";
import { sendMany } from "../_shared/fcm.ts";
import { toInt } from "../_shared/query.ts";
import {
  FreshEpisode,
  planMessages,
  recipientsFor,
  Subscription,
} from "../_shared/push_plan.ts";

type EpisodeRow = FreshEpisode & { anime: { is_published: boolean } };
type SubRow = Subscription;

Deno.serve(
  withGuard(async (req: Request) => {
    // ── xác thực cron ──
    const secret = Deno.env.get("PUSH_CRON_SECRET");
    const given = req.headers.get("x-cron-secret") ?? "";
    const url = new URL(req.url);
    const dryRun = url.searchParams.get("dry_run") === "true";

    if (secret && given !== secret) {
      return fail("unauthorized", "Sai x-cron-secret");
    }
    if (!secret && !dryRun) {
      return fail(
        "unauthorized",
        "Chưa set PUSH_CRON_SECRET → chỉ cho phép ?dry_run=true",
      );
    }

    const windowMin = toInt(url.searchParams.get("window"), 25, 5, 180);
    const limit = toInt(url.searchParams.get("limit"), 40, 1, 100);

    const sb = adminClient();
    const now = new Date();
    const from = new Date(now.getTime() - windowMin * 60_000);

    // ── 1. tập vừa phát ──
    const { data: epData, error: epErr } = await sb
      .from("episodes")
      .select(
        "anime_id, number, airing_at, title, " +
          "anime:anime!inner(slug, title_romaji, title_english, title_vi, is_published)",
      )
      .gte("airing_at", from.toISOString())
      .lte("airing_at", now.toISOString())
      .order("airing_at", { ascending: true })
      .limit(limit);

    if (epErr) throw new Error(`episodes: ${epErr.message}`);

    const episodes = ((epData ?? []) as unknown as EpisodeRow[])
      .filter((e) => e.anime?.is_published && e.number > 0);

    if (episodes.length === 0) {
      return ok(
        { window_minutes: windowMin, episodes: 0, devices: 0, sent: 0, skipped: 0 },
        { ttl: 0, note: "không có tập mới" },
        { maxAge: 0 },
      );
    }

    // ── 2. bỏ những cặp (anime, tập) đã gửi ──
    const animeIds = [...new Set(episodes.map((e) => e.anime_id))];
    const { data: sentData } = await sb
      .from("sent_episode_pushes")
      .select("anime_id, episode_number")
      .in("anime_id", animeIds);

    const alreadySent = new Set(
      ((sentData ?? []) as { anime_id: number; episode_number: number }[])
        .map((r) => `${r.anime_id}:${r.episode_number}`),
    );

    const fresh = episodes.filter((e) => !alreadySent.has(`${e.anime_id}:${e.number}`));

    if (fresh.length === 0) {
      return ok(
        {
          window_minutes: windowMin,
          episodes: episodes.length,
          new_episodes: 0,
          devices: 0,
          sent: 0,
          skipped: episodes.length,
        },
        { ttl: 0, note: "tất cả đã gửi trước đó" },
        { maxAge: 0 },
      );
    }

    // ── 3. thiết bị quan tâm (overlaps = giao của 2 mảng) ──
    const freshAnimeIds = [...new Set(fresh.map((e) => e.anime_id))];
    const { data: subData, error: subErr } = await sb
      .from("push_subscriptions")
      .select("id, token, platform, locale, anime_ids")
      .eq("is_active", true)
      .overlaps("anime_ids", freshAnimeIds)
      .limit(5000);

    if (subErr) throw new Error(`push_subscriptions: ${subErr.message}`);

    const subs = (subData ?? []) as SubRow[];

    // ── 4. dựng message (logic thuần, đã unit-test: _shared/push_plan.ts) ──
    const targets = planMessages(subs, fresh);

    // ── 5. dry run: chỉ báo cáo ──
    if (dryRun) {
      return ok(
        {
          dry_run: true,
          window_minutes: windowMin,
          new_episodes: fresh.map((e) => ({
            anime_id: e.anime_id,
            slug: e.anime.slug,
            title: e.anime.title_vi || e.anime.title_romaji,
            episode: e.number,
            airing_at: e.airing_at,
          })),
          devices: subs.length,
          messages_to_send: targets.length,
          preview: targets.slice(0, 3).map((t) => t.payload),
        },
        { ttl: 0 },
        { maxAge: 0 },
      );
    }

    if (targets.length === 0) {
      return ok(
        {
          window_minutes: windowMin,
          new_episodes: fresh.length,
          devices: subs.length,
          sent: 0,
          note: "có tập mới nhưng không thiết bị nào theo dõi",
        },
        { ttl: 0 },
        { maxAge: 0 },
      );
    }

    // ── 6. gửi ──
    const result = await sendMany(targets, 12);

    // ── 7. vô hiệu hoá token chết ──
    if (result.dead.length > 0) {
      await sb
        .from("push_subscriptions")
        .update({ is_active: false })
        .in("token", [...new Set(result.dead)]);
    }

    // ── 8. ghi chống trùng (mỗi cặp anime/tập 1 lần) ──
    const rows = fresh.map((e) => ({
      anime_id: e.anime_id,
      episode_number: e.number,
      recipients: recipientsFor(subs, e.anime_id),
      failed: result.failed,
    }));
    const { error: markErr } = await sb
      .from("sent_episode_pushes")
      .upsert(rows, { onConflict: "anime_id,episode_number" });
    if (markErr) console.error("không ghi được sent_episode_pushes:", markErr.message);

    return ok(
      {
        window_minutes: windowMin,
        new_episodes: fresh.length,
        devices: subs.length,
        messages: targets.length,
        sent: result.sent,
        failed: result.failed,
        deactivated_tokens: result.dead.length,
        errors_sample: result.errors.slice(0, 3),
      },
      { ttl: 0 },
      { maxAge: 0 },
    );
  }),
);
