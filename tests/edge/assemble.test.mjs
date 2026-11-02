// Test logic thuần của _shared/assemble.ts — chạy bằng node, không cần Deno/Supabase.
//
//   bash scripts/test_edge.sh
//
// Vì sao có file này: Muse/Ani-One hay đăng BẢN GỘP cả bộ trong 1 video
// ("[Bản Lồng Tiếng] One Punch Man - Tập 01-24"). Ingest lưu chúng với
// episode_number = 0. Bản cũ của assemble CHỈ thêm entry đó khi anime không có
// tập nào khác (`eps.length === 0`) → người dùng mất hẳn bản gộp trên app.
import test from "node:test";
import assert from "node:assert/strict";

import { recentAired, toAnimeDto, youtubeId } from "./.build/assemble.mjs";

const ROW = {
  id: 1, slug: "one-punch-man", title_romaji: "One Punch Man",
  title_english: "One Punch Man", title_vi: null, title_native: null,
  cover_url: null, banner_url: null, year: 2015, season: "FALL", status: "FINISHED",
  format: "TV", episodes_total: 12, score: 8.5, popularity: 1000, genres: ["Action"],
  synopsis_vi: null, synopsis_original: "Saitama",
};

const VID = "dQw4w9WgXcQ";

function link(episode, vid = VID) {
  return {
    anime_id: 1, episode_number: episode, platform: "youtube", region: "VN",
    url: `https://www.youtube.com/watch?v=${vid}`, kind: "free_legal", is_verified: true,
  };
}

test("youtubeId: lấy id từ watch/short/embed", () => {
  assert.equal(youtubeId(`https://www.youtube.com/watch?v=${VID}`), VID);
  assert.equal(youtubeId(`https://youtu.be/${VID}`), VID);
  assert.equal(youtubeId("https://example.com/x"), null);
});

test("bản gộp cả bộ (episode 0) PHẢI hiện dù bộ đã có tập", () => {
  const episodes = [{ anime_id: 1, number: 1, title: "", airing_at: null }];
  const dto = toAnimeDto(ROW, episodes, [link(1), link(0, "AAAAAAAAAAA")]);
  const full = dto.episodes.find((e) => e.number === 0);
  assert.ok(full, "phải có entry số 0 (bản gộp cả bộ)");
  assert.equal(full.video_id, "AAAAAAAAAAA");
});

test("bản gộp đặt CUỐI để 'Xem ngay' trỏ vào tập 1", () => {
  const episodes = [{ anime_id: 1, number: 1, title: "", airing_at: null }];
  const dto = toAnimeDto(ROW, episodes, [link(1), link(0, "AAAAAAAAAAA")]);
  assert.equal(dto.episodes[0].number, 1, "tập 1 phải đứng đầu");
  assert.equal(dto.episodes.at(-1).number, 0, "bản gộp đứng cuối");
});

test("bộ chỉ có bản gộp → vẫn có đúng 1 entry", () => {
  const dto = toAnimeDto(ROW, [], [link(0)]);
  assert.equal(dto.episodes.length, 1);
  assert.equal(dto.episodes[0].number, 0);
  assert.equal(dto.episodes[0].title, "Cả bộ");
});

test("không có link cho cả bộ → không tự sinh entry 0", () => {
  const dto = toAnimeDto(ROW, [{ anime_id: 1, number: 3, title: "", airing_at: null }],
    [link(3)]);
  assert.equal(dto.episodes.some((e) => e.number === 0), false);
});

test("is_free = có link free_legal đã verify", () => {
  assert.equal(toAnimeDto(ROW, [], [link(1)]).is_free, true);
  assert.equal(toAnimeDto(ROW, [], []).is_free, false);
});

test("cùng 1 tập có bản VN và bản AS → ưu tiên VN (không phụ thuộc thứ tự DB)", () => {
  const vn = { ...link(1), region: "VN", url: `https://www.youtube.com/watch?v=${"V".repeat(11)}` };
  const asia = { ...link(1), region: "AS", url: `https://www.youtube.com/watch?v=${"A".repeat(11)}` };
  const episodes = [{ anime_id: 1, number: 1, title: "", airing_at: null }];

  const dto1 = toAnimeDto(ROW, episodes, [asia, vn]);
  const dto2 = toAnimeDto(ROW, episodes, [vn, asia]);
  assert.equal(dto1.episodes[0].video_id, "V".repeat(11));
  assert.equal(dto2.episodes[0].video_id, "V".repeat(11), "đảo thứ tự vẫn phải ra VN");
});

test("chỉ có bản AS thì dùng AS (không bỏ trống)", () => {
  const asia = { ...link(1), region: "AS", url: `https://www.youtube.com/watch?v=${"A".repeat(11)}` };
  const dto = toAnimeDto(ROW, [{ anime_id: 1, number: 1, title: "", airing_at: null }], [asia]);
  assert.equal(dto.episodes[0].video_id, "A".repeat(11));
});

test("recentAired: bỏ tập CHƯA chiếu (506 tập tương lai / 66 bộ, đo 02/11/2026)", () => {
  const now = new Date("2026-11-02T12:00:00Z");
  const rows = [
    { anime_id: 1, number: 5, airing_at: "2026-11-02T09:00:00Z" },  // trong 6h → giữ
    { anime_id: 1, number: 6, airing_at: "2026-11-02T11:30:00Z" },  // vừa chiếu → giữ
    { anime_id: 2, number: 9, airing_at: "2026-11-09T12:00:00Z" },  // TUẦN SAU → bỏ
    { anime_id: 3, number: 1, airing_at: "2026-10-20T12:00:00Z" },  // cũ → bỏ
    { anime_id: 4, number: 3, airing_at: null },                    // không rõ lịch → giữ
  ];
  const kept = recentAired(rows, now).map((r) => `${r.anime_id}-${r.number}`);
  assert.deepEqual(kept, ["1-5", "1-6", "4-3"]);
});

test("recentAired: airing_at hỏng không làm mất tập", () => {
  const kept = recentAired([{ airing_at: "not-a-date" }], new Date("2026-11-02T12:00:00Z"));
  assert.equal(kept.length, 1);
});
