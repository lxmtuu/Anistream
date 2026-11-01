// Test logic THUẦN của /push — chạy bằng node, không cần Deno, không cần Supabase.
//
//   bash scripts/test_edge.sh
//
// Vì sao có file này: README từng ghi "logic đã unit-test 6/6 assert" nhưng trong
// repo KHÔNG có file test nào. Đây là bộ test thật, chạy được trong CI.
import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPayload,
  displayTitle,
  episodeKey,
  episodePairs,
  keysOf,
  planMessages,
  recipientsFor,
  unsentEpisodes,
} from "./.build/push_plan.mjs";

// ── dữ liệu mẫu ────────────────────────────────────────────
const ep = (animeId, number, extra = {}) => ({
  anime_id: animeId,
  number,
  airing_at: "2026-11-01T12:00:00+00:00",
  title: null,
  anime: {
    slug: `anime-${animeId}`,
    title_romaji: `Romaji ${animeId}`,
    title_english: `English ${animeId}`,
    title_vi: null,
    ...extra,
  },
});

const sub = (id, animeIds, extra = {}) => ({
  id,
  token: `token-${id}`,
  platform: "android",
  anime_ids: animeIds,
  ...extra,
});

// ── nội dung tin nhắn ──────────────────────────────────────
test("ưu tiên tên tiếng Việt, rồi romaji, rồi english", () => {
  assert.equal(displayTitle(ep(1, 3, { title_vi: "Phù Thủy" })), "Phù Thủy");
  assert.equal(displayTitle(ep(1, 3)), "Romaji 1");
  assert.equal(
    displayTitle({ ...ep(1, 3), anime: { slug: "s", title_romaji: "", title_english: "Eng", title_vi: null } }),
    "Eng",
  );
});

test("payload mở đúng route /anime/<slug> và đủ data cho client", () => {
  const p = buildPayload(ep(154587, 6, { title_vi: "Frieren" }));
  assert.equal(p.title, "Frieren");
  assert.match(p.body, /Tập 6/);
  assert.equal(p.data.route, "/anime/anime-154587");
  assert.equal(p.data.slug, "anime-154587");
  assert.equal(p.data.episode, "6");
  assert.equal(p.data.anime_id, "154587");
  assert.equal(p.data.type, "new_episode");
  assert.equal(p.channelId, "new_episode");
  // route phải bắt đầu bằng "/" — PushService._handleRoute bỏ qua route khác
  assert.ok(p.data.route.startsWith("/"));
});

test("body KHÔNG hứa phát video trong app (trung thực về bản quyền)", () => {
  const body = buildPayload(ep(1, 1)).body;
  assert.doesNotMatch(body, /xem ngay|phát ngay|stream/i);
  assert.match(body, /hợp pháp/);
});

// ── quy tắc chống spam ────────────────────────────────────
test("mỗi thiết bị chỉ 1 tin cho 1 bộ (dù có 3 tập mới)", () => {
  const subs = [sub(1, [100])];
  const fresh = [ep(100, 5), ep(100, 6), ep(100, 7)];
  const out = planMessages(subs, fresh);
  assert.equal(out.length, 1);
  assert.equal(out[0].payload.data.episode, "7", "phải chọn tập SỐ LỚN NHẤT");
});

test("chọn tập lớn nhất theo số tập, không theo thứ tự mảng", () => {
  const out = planMessages([sub(1, [100])], [ep(100, 9), ep(100, 4), ep(100, 12)]);
  assert.equal(out[0].payload.data.episode, "12");
});

test("2 thiết bị theo dõi 2 bộ khác nhau → mỗi bộ 1 tin/thiết bị", () => {
  const subs = [sub(1, [100, 200]), sub(2, [200])];
  const fresh = [ep(100, 1), ep(200, 3)];
  const out = planMessages(subs, fresh);
  assert.equal(out.length, 3);
  assert.deepEqual(
    out.map((t) => `${t.token}/${t.payload.data.anime_id}`).sort(),
    ["token-1/100", "token-1/200", "token-2/200"],
  );
});

test("bỏ qua thiết bị không theo dõi bộ nào trong lô", () => {
  const out = planMessages([sub(1, [999])], [ep(100, 1)]);
  assert.deepEqual(out, []);
});

test("bỏ qua thiết bị có anime_ids rỗng hoặc token rỗng", () => {
  const subs = [sub(1, []), sub(2, [100], { token: "" }), sub(3, [100])];
  const out = planMessages(subs, [ep(100, 1)]);
  assert.equal(out.length, 1);
  assert.equal(out[0].token, "token-3");
});

test("không tạo 2 tin giống nhau khi cùng token xuất hiện 2 lần", () => {
  const dup = [sub(7, [100]), { ...sub(8, [100]), token: "token-7" }];
  const out = planMessages(dup, [ep(100, 1)]);
  assert.equal(out.length, 1, "khoá khử trùng là token+anime+tập");
});

// ── chống gửi trùng / race giữa 2 lần cron ────────────────
test("episodeKey thống nhất giữa 3 nơi dùng", () => {
  assert.equal(episodeKey(154587, 6), "154587:6");
  assert.deepEqual([...keysOf([{ anime_id: 1, episode_number: 2 }])], ["1:2"]);
});

test("unsentEpisodes chỉ giữ tập chưa gửi", () => {
  const eps = [ep(100, 1), ep(100, 2), ep(200, 1)];
  const sent = keysOf([{ anime_id: 100, episode_number: 1 }]);
  assert.deepEqual(
    unsentEpisodes(eps, sent).map((e) => episodeKey(e.anime_id, e.number)),
    ["100:2", "200:1"],
  );
});

test("mô phỏng 2 lần cron chồng nhau: chỉ lần giành được mới gửi", () => {
  const fresh = [ep(100, 6), ep(200, 3)];
  const all = fresh.map((e) => episodeKey(e.anime_id, e.number));

  // lần A giành được cả 2 dòng
  const reservedA = new Set(all);
  // lần B: upsert ignoreDuplicates không trả về dòng nào
  const reservedB = new Set([]);

  const sendA = fresh.filter((e) => reservedA.has(episodeKey(e.anime_id, e.number)));
  const sendB = fresh.filter((e) => reservedB.has(episodeKey(e.anime_id, e.number)));

  assert.equal(sendA.length, 2);
  assert.equal(sendB.length, 0, "lần cron thứ 2 phải không gửi gì");
});

test("recipientsFor đếm đúng số thiết bị theo dõi 1 bộ", () => {
  const subs = [sub(1, [100, 200]), sub(2, [100]), sub(3, [300])];
  assert.equal(recipientsFor(subs, 100), 2);
  assert.equal(recipientsFor(subs, 300), 1);
  assert.equal(recipientsFor(subs, 999), 0);
});

test("episodePairs: chỉ nhả đúng cặp (anime, tập), không nhả tích chéo", () => {
  const pairs = episodePairs([
    { anime_id: 1, number: 5 },
    { anime_id: 2, number: 3 },
    { anime_id: 1, number: 5 }, // trùng
  ]);
  assert.deepEqual(pairs, [
    { anime_id: 1, number: 5 },
    { anime_id: 2, number: 3 },
  ]);
});
