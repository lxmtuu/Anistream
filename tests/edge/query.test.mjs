// Test logic THUẦN của _shared/query.ts — chạy bằng node, không cần Deno/Supabase.
//
//   bash scripts/test_edge.sh
//
// Vì sao có file này: trên project thật, `GET /search?q=a&page=2` khi catalog trống
// trả HTTP 500 "Requested range not satisfiable" (PostgREST PGRST103). Đó là lỗi
// thật của /search (vuốt quá trang cuối), đã được vá bằng isRangeNotSatisfiable.
import test from "node:test";
import assert from "node:assert/strict";

import {
  currentSeason,
  ilikeSafe,
  isRangeNotSatisfiable,
  resolveSort,
  selectAll,
  toInt,
} from "./.build/query.mjs";

test("isRangeNotSatisfiable: nhận đúng lỗi PGRST103 của PostgREST", () => {
  assert.equal(
    isRangeNotSatisfiable({
      code: "PGRST103",
      message: "Requested range not satisfiable",
    }),
    true,
  );
});

test("isRangeNotSatisfiable: vẫn nhận ra khi thiếu code nhưng message khớp", () => {
  assert.equal(
    isRangeNotSatisfiable({ message: "Requested range not satisfiable" }),
    true,
  );
  assert.equal(
    isRangeNotSatisfiable({ code: "XX000", details: "requested range not satisfiable" }),
    true,
  );
});

test("isRangeNotSatisfiable: KHÔNG nuốt lỗi khác (phải nổ to)", () => {
  assert.equal(isRangeNotSatisfiable(null), false);
  assert.equal(isRangeNotSatisfiable(undefined), false);
  assert.equal(
    isRangeNotSatisfiable({ code: "42P01", message: 'relation "anime" does not exist' }),
    false,
  );
  assert.equal(isRangeNotSatisfiable({ message: "timeout" }), false);
});

test("toInt: kẹp trong [min,max], fallback khi rác", () => {
  assert.equal(toInt("5", 1, 1, 50), 5);
  assert.equal(toInt("999", 1, 1, 50), 50);
  assert.equal(toInt("-3", 1, 1, 50), 1);
  assert.equal(toInt(null, 24, 1, 48), 24);
  assert.equal(toInt("abc", 24, 1, 48), 24);
});

test("ilikeSafe: escape % _ \\ để không phá filter PostgREST", () => {
  assert.equal(ilikeSafe("100%"), "100\\%");
  assert.equal(ilikeSafe("a_b"), "a\\_b");
  assert.equal(ilikeSafe("a\\b"), "a\\\\b");
  assert.ok(ilikeSafe("x".repeat(200)).length <= 60);
});

test("resolveSort: chỉ cho cột đã biết, mặc định popular", () => {
  assert.deepEqual(resolveSort("top"), { column: "score", ascending: false });
  assert.deepEqual(resolveSort("bậy-bạ"), { column: "popularity", ascending: false });
  assert.deepEqual(resolveSort(null), { column: "popularity", ascending: false });
});

test("currentSeason: tính theo UTC", () => {
  assert.equal(currentSeason(new Date("2026-01-15T00:00:00Z")), "WINTER");
  assert.equal(currentSeason(new Date("2026-04-15T00:00:00Z")), "SPRING");
  assert.equal(currentSeason(new Date("2026-08-15T00:00:00Z")), "SUMMER");
  assert.equal(currentSeason(new Date("2026-11-01T00:00:00Z")), "FALL");
});

test("selectAll: đọc hết nhiều trang (PostgREST cắt ở 1000 dòng)", async () => {
  const all = Array.from({ length: 2345 }, (_, i) => i);
  const calls = [];
  const got = await selectAll(async (from, to) => {
    calls.push([from, to]);
    return { data: all.slice(from, to + 1), error: null };
  });
  assert.equal(got.length, 2345);
  assert.deepEqual(calls, [[0, 999], [1000, 1999], [2000, 2999]]);
});

test("selectAll: dừng ngay khi trang ngắn", async () => {
  const calls = [];
  const got = await selectAll(async (from, to) => {
    calls.push([from, to]);
    return { data: from === 0 ? [1, 2, 3] : [], error: null };
  });
  assert.deepEqual(got, [1, 2, 3]);
  assert.equal(calls.length, 1);
});

test("selectAll: lỗi query phải ném ra (không trả rỗng im lặng)", async () => {
  await assert.rejects(
    () => selectAll(async () => ({ data: null, error: { message: "boom" } })),
    /boom/,
  );
});
