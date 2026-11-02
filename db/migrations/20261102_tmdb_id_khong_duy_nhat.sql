-- ─────────────────────────────────────────────────────────────────────────────
-- 20261102_tmdb_id_khong_duy_nhat.sql
--
-- VÌ SAO CẦN: `anime.tmdb_id` đang có ràng buộc UNIQUE, nhưng TMDB **gộp cả
-- series vào một id** còn AniList **tách mỗi mùa thành một entry**. Vì vậy
-- "One-Punch Man" (mùa 1) và "One Punch Man 2" (mùa 2) BẮT BUỘC phải cùng
-- một `tmdb_id` — ràng buộc cũ làm mọi lần ghi mùa 2 đều thất bại:
--
--     patch anime lỗi 409: duplicate key value violates unique constraint
--     "anime_tmdb_id_key"  Key (tmdb_id)=(207347) already exists
--
-- Đo 02/11/2026 (một lần chạy `tmdb --limit-tmdb 200`): **13 bộ** bị 409 như
-- vậy — Blue Box, You and I Are Polar Opposites, Apothecary Diaries S3, Black
-- Clover S2, Takagi-san S2, The Ramparts of Ice, As a Reincarnated Aristocrat,
-- A Wild Last Boss Appeared, Sasaki and Peeps, The Detective Is Already Dead
-- S2, HOTEL INHUMANS, With Vengeance Sincerely… — và vì `DB.patch` ném lỗi
-- nên **job bỏ luôn phần danh sách tập** của chính bộ đó.
--
-- Mất UNIQUE KHÔNG làm mất an toàn: `tmdb_id` chỉ là khoá tra cứu sang TMDB,
-- mùa nào lấy tập nào do `tmdb.pick_season()` quyết định dựa trên tên bộ.
-- Khoá định danh thật của bảng vẫn là `slug` / `anilist_id` / `mal_id` (đều
-- còn UNIQUE).
--
-- Idempotent: chạy nhiều lần không lỗi.
-- ─────────────────────────────────────────────────────────────────────────────

alter table anime drop constraint if exists anime_tmdb_id_key;

-- Vẫn cần tra cứu nhanh theo tmdb_id (job D/fetch) → giữ index thường.
create index if not exists anime_tmdb_id_idx on anime (tmdb_id);

comment on column anime.tmdb_id is
  'ID series trên TMDB. KHÔNG duy nhất: nhiều entry AniList (mỗi mùa) dùng chung một series TMDB.';
