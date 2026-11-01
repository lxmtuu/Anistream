-- ─────────────────────────────────────────────────────────────────────────────
-- 20261101_synopsis_original.sql
--
-- VÌ SAO CẦN: cột `anime.synopsis_vi` chưa bao giờ được ghi (ingest không có
-- bước dịch nào, và `TMDB_API_KEY` chỉ được đọc ra chứ không dùng) → API trả
-- `synopsis: ""` cho TOÀN BỘ anime → trang chi tiết trống phần giới thiệu.
--
-- AniList đã trả sẵn `description` (thường tiếng Anh) nhưng code cũ vứt đi.
-- Bản vá này thêm cột để chứa bản gốc, làm nội dung dự phòng; khi có bản dịch
-- tiếng Việt thì `synopsis_vi` vẫn được ưu tiên.
--
-- Idempotent: chạy nhiều lần không lỗi.
-- ─────────────────────────────────────────────────────────────────────────────

alter table anime add column if not exists synopsis_original text;

comment on column anime.synopsis_original is
  'Mô tả gốc (AniList description, đã strip HTML). Dùng khi synopsis_vi còn trống.';

-- Đổ dữ liệu cho các dòng đã có: KHÔNG tự bịa nội dung. Chạy lại
-- `python3 -m ingest.main schedule` (hoặc `catalog`) để ingest điền cột này
-- từ AniList. Sau đó kiểm tra:
--   select count(*) from anime where synopsis_original is not null;
