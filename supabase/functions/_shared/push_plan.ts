/**
 * push_plan.ts — logic THUẦN quyết định gửi gì cho ai.
 *
 * Tách riêng khỏi index.ts để test được bằng Node mà không cần Supabase/FCM.
 * Quy tắc chống spam:
 *   1. Mỗi thiết bị chỉ nhận 1 tin cho 1 bộ (không 3 tin khi có 3 tập mới).
 *   2. Bộ nào chọn tập có số LỚN NHẤT trong lô (tập mới nhất).
 *   3. Không gửi trùng cùng token+anime+episode.
 */

export interface FreshEpisode {
  anime_id: number;
  number: number;
  airing_at: string;
  title: string | null;
  anime: {
    slug: string;
    title_romaji: string;
    title_english: string | null;
    title_vi: string | null;
  };
}

export interface Subscription {
  id: number;
  token: string;
  platform: string;
  locale?: string;
  anime_ids: number[];
}

export interface PushPayload {
  title: string;
  body: string;
  data: Record<string, string>;
  channelId: string;
}

export interface PushTarget {
  token: string;
  payload: PushPayload;
}

export function displayTitle(e: FreshEpisode): string {
  return (
    e.anime.title_vi ||
    e.anime.title_romaji ||
    e.anime.title_english ||
    "Anime"
  );
}

/** Nội dung tin nhắn. Trung thực: không hứa "xem ngay ở đây". */
export function buildPayload(e: FreshEpisode): PushPayload {
  return {
    title: displayTitle(e),
    body: `Tập ${e.number} vừa phát sóng · bấm để xem lịch & nơi xem hợp pháp`,
    data: {
      route: `/anime/${e.anime.slug}`,
      anime_id: String(e.anime_id),
      slug: e.anime.slug,
      episode: String(e.number),
      type: "new_episode",
    },
    channelId: "new_episode",
  };
}

/** Lập kế hoạch gửi: danh sách (token, payload) đã khử trùng. */
export function planMessages(
  subs: Subscription[],
  fresh: FreshEpisode[],
): PushTarget[] {
  const targets: PushTarget[] = [];
  const used = new Set<string>();
  const usable = subs.filter((s) => s.token && s.anime_ids && s.anime_ids.length > 0);

  for (const s of usable) {
    const wanted = new Set(s.anime_ids);

    // tập mới nhất của mỗi bộ trong lô mà thiết bị này quan tâm
    const latestByAnime = new Map<number, FreshEpisode>();
    for (const e of fresh) {
      if (!wanted.has(e.anime_id)) continue;
      const prev = latestByAnime.get(e.anime_id);
      if (!prev || e.number > prev.number) latestByAnime.set(e.anime_id, e);
    }

    for (const e of latestByAnime.values()) {
      const key = `${s.token}:${e.anime_id}:${e.number}`;
      if (used.has(key)) continue;
      used.add(key);
      targets.push({ token: s.token, payload: buildPayload(e) });
    }
  }

  return targets;
}

/** Đếm số thiết bị quan tâm 1 bộ — dùng để ghi `recipients`. */
export function recipientsFor(subs: Subscription[], animeId: number): number {
  return subs.filter((s) => s.anime_ids.includes(animeId)).length;
}
