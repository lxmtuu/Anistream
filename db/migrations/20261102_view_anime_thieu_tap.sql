-- View: những bộ có danh sách tập ĐÁNG SỬA.
--
-- Vì sao cần: job TMDB trước đây chỉ chọn bộ theo `title_vi/synopsis_vi/
-- episodes_total is null` (chế độ bổ sung) hoặc `status = RELEASING` (chế độ
-- --refresh). Bộ đã có tên tiếng Việt + `episodes_total` nhưng **0 tập** (đo
-- 02/11/2026: 32 bộ) không nằm trong cả hai → không bao giờ được thử lại.
--
-- 02/11/2026 (lần 2): `tensei-kizoku-…-3rd-season` có 12 tập đúng (số 1..12)
-- CỘNG 12 dòng trùng (số 25..36, **cùng ngày chiếu**) dư từ lần đánh số trước.
-- Bộ này không còn "0 tập" nên cũng không bao giờ được ghé lại → trang chi
-- tiết hiện 24 tập trong khi chỉ có 12 tập thật.
--
-- Điều kiện (và là ĐỊNH NGHĨA "danh sách tập sai"):
--   · `episodes_total > 0`  — bỏ phim lẻ/OVA 1 tập chưa rõ tổng;
--   · đã/chưa chiếu (NOT_YET_RELEASED thì trống là ĐÚNG → loại);
--   · chưa có tập nào, **hoặc** có hai tập trùng NGÀY CHIẾU (một ngày không
--     thể có 2 tập của cùng một bộ — luôn là hệ quả của đánh số lại).
create or replace view public.anime_thieu_tap as
select
    a.id, a.slug, a.anilist_id, a.tmdb_id,
    a.title_romaji, a.title_english, a.title_native,
    a.title_vi, a.synopsis_vi,
    a.year, a.status, a.episodes_total, a.popularity, a.tmdb_checked_at
from public.anime a
where coalesce(a.episodes_total, 0) > 0
  and a.status <> 'NOT_YET_RELEASED'
  and (
      not exists (
          select 1 from public.episodes e where e.anime_id = a.id
      )
      or exists (
          select 1
          from public.episodes e1
          join public.episodes e2
            on e2.anime_id = e1.anime_id
           and e2.number <> e1.number
           and e2.airing_at::date = e1.airing_at::date
          where e1.anime_id = a.id
      )
  );

comment on view public.anime_thieu_tap is
  'Anime có episodes_total > 0 nhưng danh sách tập TRỐNG hoặc có 2 tập trùng '
  'ngày chiếu — job TMDB dùng để sửa thay vì bỏ qua vĩnh viễn.';

grant select on public.anime_thieu_tap to anon, authenticated;
