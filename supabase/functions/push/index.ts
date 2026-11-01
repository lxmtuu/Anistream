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
  episodeKey,
  episodePairs,
  FreshEpisode,
  keysOf,
  planMessages,
  recipientsFor,
  Subscription,
  unsentEpisodes,
} from "../_shared/push_plan.ts";

type EpisodeRow = FreshEpisode & { anime: { is_published: boolean } };
type SubRow = Subscription;

/** Nhả quyền gửi: xoá dòng "đã gửi" của các tập vừa giành nhưng chưa gửi được. */
async function releaseReservations(
  sb: ReturnType<typeof adminClient>,
  fresh: FreshEpisode[],
): Promise<void> {
  if (fresh.length === 0) return;
  // Xoá theo TỪNG CẶP. Dùng 2 lần `.in()` là AND → xoá tích chéo và nhả nhầm
  // quyền của tập chưa gửi ⇒ cron sau gửi trùng.
  for (const p of episodePairs(fresh)) {
    const { error } = await sb
      .from("sent_episode_pushes")
      .delete()
      .eq("anime_id", p.anime_id)
      .eq("episode_number", p.number);
    if (error) console.error("không nhả được reservation:", error.message);
  }
}

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
      .gt("number", 0)          // tập 0 = "cả bộ", không phải tập mới
      .order("airing_at", { ascending: true })
      .limit(limit);

    if (epErr) throw new Error(`episodes: ${epErr.message}`);

    const episodes = ((epData ?? []) as unknown as EpisodeRow[])
      .filter((e) => e.anime?.is_published);

    if (episodes.length === 0) {
      return ok(
        { window_minutes: windowMin, episodes: 0, devices: 0, sent: 0, skipped: 0 },
        { ttl: 0, note: "không có tập mới" },
        { maxAge: 0 },
      );
    }

    // ── 2. GIÀNH QUYỀN GỬI TRƯỚC khi gửi (chống 2 lần cron chồng nhau) ──
    // Trước đây: đọc xem đã gửi chưa → gửi → ghi "đã gửi". Hai lần cron chạy
    // chồng nhau (cron 10–15 phút, hoặc bấm tay đúng lúc) đều đọc thấy "chưa
    // gửi" và cùng gửi → người dùng nhận 2 thông báo cho cùng 1 tập.
    // Giờ: INSERT trước với ignoreDuplicates → chỉ lần nào giành được dòng mới
    // có quyền gửi. Đây là khoá bằng unique key (anime_id, episode_number).
    const animeIds = [...new Set(episodes.map((e) => e.anime_id))];
    const { data: sentData } = await sb
      .from("sent_episode_pushes")
      .select("anime_id, episode_number")
      .in("anime_id", animeIds);

    const alreadySent = keysOf(
      (sentData ?? []) as { anime_id: number; episode_number: number }[],
    );
    const candidates = unsentEpisodes(episodes, alreadySent);

    if (candidates.length === 0) {
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

    let fresh = candidates;
    if (!dryRun) {
      const reserveRows = candidates.map((e) => ({
        anime_id: e.anime_id,
        episode_number: e.number,
        recipients: 0,
        failed: 0,
      }));
      const { data: reservedData, error: reserveErr } = await sb
        .from("sent_episode_pushes")
        .upsert(reserveRows, {
          onConflict: "anime_id,episode_number",
          ignoreDuplicates: true,     // dòng đã có thì KHÔNG ghi đè, và không trả về
        })
        .select("anime_id, episode_number");

      if (reserveErr) throw new Error(`reserve sent_episode_pushes: ${reserveErr.message}`);

      const got = keysOf(
        (reservedData ?? []) as { anime_id: number; episode_number: number }[],
      );
      fresh = candidates.filter((e) => got.has(episodeKey(e.anime_id, e.number)));

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
          { ttl: 0, note: "lần cron khác đang/đã gửi — bỏ qua để không gửi trùng" },
          { maxAge: 0 },
        );
      }
    }

    // ── 3. thiết bị quan tâm (overlaps = giao của 2 mảng) ──
    const freshAnimeIds = [...new Set(fresh.map((e) => e.anime_id))];
    const SUBS_CAP = 5000;
    const { data: subData, error: subErr } = await sb
      .from("push_subscriptions")
      .select("id, token, platform, locale, anime_ids")
      .eq("is_active", true)
      .overlaps("anime_ids", freshAnimeIds)
      .limit(SUBS_CAP);

    if (subErr) throw new Error(`push_subscriptions: ${subErr.message}`);

    const subs = (subData ?? []) as SubRow[];
    // Không im lặng khi bị cắt: nếu chạm trần thì một số thiết bị sẽ không nhận tin.
    const subsTruncated = subs.length >= SUBS_CAP;

    // ── 4. dựng message (logic thuần, đã test: tests/edge/push_plan.test.mjs) ──
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
          devices_truncated: subsTruncated,
          messages_to_send: targets.length,
          preview: targets.slice(0, 3).map((t) => t.payload),
        },
        { ttl: 0 },
        { maxAge: 0 },
      );
    }

    // Không ai theo dõi → NHẢ quyền gửi, để sau này có người theo dõi thì vẫn gửi được.
    if (targets.length === 0) {
      await releaseReservations(sb, fresh);
      return ok(
        {
          window_minutes: windowMin,
          new_episodes: fresh.length,
          devices: subs.length,
          devices_truncated: subsTruncated,
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

    // ── 8. chốt sổ ──
    // Nếu gửi được 0 tin (FCM lỗi cấu hình, Google từ chối, mạng…) thì PHẢI nhả
    // quyền gửi. Trước đây vẫn ghi "đã gửi" → tập đó KHÔNG BAO GIỜ được gửi lại,
    // kể cả sau khi bạn sửa xong FCM_SERVICE_ACCOUNT. Đó là mất dữ liệu im lặng.
    if (result.sent === 0) {
      await releaseReservations(sb, fresh);
      return ok(
        {
          window_minutes: windowMin,
          new_episodes: fresh.length,
          devices: subs.length,
          devices_truncated: subsTruncated,
          messages: targets.length,
          sent: 0,
          failed: result.failed,
          released_reservations: fresh.length,
          errors_sample: result.errors.slice(0, 3),
        },
        { ttl: 0, note: "gửi thất bại toàn bộ → đã nhả quyền để lần sau thử lại" },
        { maxAge: 0 },
      );
    }

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
