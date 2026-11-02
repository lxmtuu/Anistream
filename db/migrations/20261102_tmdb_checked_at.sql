-- ─────────────────────────────────────────────────────────────────────────────
-- 20261102_tmdb_checked_at.sql
--
-- VÌ SAO CẦN: job D chọn bộ theo điều kiện
--   or=(title_vi.is.null, synopsis_vi.is.null, episodes_total.is.null)
-- nên bộ nào TMDB **không có** (44 bộ) hoặc **không có bản dịch vi** (13 bộ) sẽ
-- được chọn LẠI Ở MỌI LẦN CHẠY, mãi mãi. Đo 02/11/2026: một lần chạy quét đủ
-- 161 bộ trong **792 giây** mà ghi được **0 bản ghi**.
--
-- Mỗi bộ tốn ~2–5 giây (search + detail + season). Quét lại những bộ đã biết là
-- không có gì = đốt thời gian và quota GitHub Actions mà không thêm dữ liệu.
--
-- Cột này ghi "lần cuối đã hỏi TMDB về bộ này". Job D bỏ qua bộ vừa hỏi gần đây:
--   · RELEASING (đang chiếu)  → 1 ngày  (cần bắt tập mới)
--   · còn lại                 → 7 ngày  (TMDB hiếm khi thêm dữ liệu cũ)
--
-- Không mất dữ liệu: bộ nào có thay đổi thì `tmdb_checked_at` vẫn được cập nhật,
-- và mọi bộ đều được xét lại trong tối đa 7 ngày.
--
-- Idempotent: chạy nhiều lần không lỗi.
-- ─────────────────────────────────────────────────────────────────────────────

alter table anime add column if not exists tmdb_checked_at timestamptz;

comment on column anime.tmdb_checked_at is
  'Lần cuối job D (TMDB) đã hỏi về bộ này. NULL = chưa từng hỏi.';

-- Lọc "bộ đã lâu chưa hỏi" là truy vấn chạy mỗi 30 phút → cần index.
create index if not exists anime_tmdb_checked_at_idx
  on anime (tmdb_checked_at);
