-- View: những bộ ĐÁNG có tập nhưng bảng `episodes` đang trống.
--
-- Vì sao cần: job TMDB trước đây chỉ chọn bộ theo `title_vi/synopsis_vi/
-- episodes_total is null` (chế độ bổ sung) hoặc `status = RELEASING` (chế độ
-- --refresh). Bộ đã có tên tiếng Việt + `episodes_total` nhưng **0 tập** (đo
-- 02/11/2026: 32 bộ) không nằm trong cả hai → không bao giờ được thử lại, dù
-- TMDB có đủ dữ liệu. Đây chính là lý do "cứ 0 tập mãi".
--
-- View chỉ ĐỌC, không ghi; điều kiện:
--   · `episodes_total > 0`  — bỏ phim lẻ/OVA 1 tập chưa rõ tổng;
--   · chưa phát sóng (NOT_YET_RELEASED) thì để trống là ĐÚNG → loại;
--   · chưa có tập nào trong `episodes`.
create or replace view public.anime_thieu_tap as
select
    a.id, a.slug, a.anilist_id, a.tmdb_id,
    a.title_romaji, a.title_english, a.title_native,
    a.title_vi, a.synopsis_vi,
    a.year, a.status, a.episodes_total, a.popularity, a.tmdb_checked_at
from public.anime a
where coalesce(a.episodes_total, 0) > 0
  and a.status <> 'NOT_YET_RELEASED'
  and not exists (
      select 1 from public.episodes e where e.anime_id = a.id
  );

comment on view public.anime_thieu_tap is
  'Anime có episodes_total > 0, đã/chưa chiếu nhưng bảng episodes trống — '
  'job TMDB dùng để thử lại thay vì bỏ qua vĩnh viễn.';

grant select on public.anime_thieu_tap to anon, authenticated;
