-- View `anime_thieu_tap`: thêm nhóm "ĐÃ CHIẾU XONG mà THIẾU TẬP".
--
-- Vì sao: job D chỉ chọn bộ theo (a) thiếu title_vi/synopsis_vi/episodes_total,
-- (b) `status = RELEASING` khi `--refresh`, (c) nằm trong view này. Bộ đã chiếu
-- xong, có 3–66 tập nhưng tổng là 25–175 thì KHÔNG thuộc nhóm nào ⇒ không bao
-- giờ được lấp. Đo 02/11/2026: **15 bộ thiếu 339 tập**
-- (`fairy-tail` 66/175, `beelzebub` 1/60, `shangri-la-frontier` 4/25,
--  `ragna-crimson` 1/24, `dark-gathering` 3/25 …).
--
-- Chỉ áp cho FINISHED: bộ đang chiếu (RELEASING) thiếu tập là BÌNH THƯỜNG và đã
-- có Job D' (`tmdb --refresh`) lo hằng ngày. NOT_YET_RELEASED thì trống là đúng.
--
-- Trang chi tiết đang hiện "25 tập" nhưng danh sách chỉ có 4 dòng — đúng thứ
-- người dùng thấy là sai.
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
      -- (1) chưa có tập nào
      not exists (select 1 from public.episodes e where e.anime_id = a.id)
      -- (2) hoặc có QUÁ NHIỀU dòng trùng ngày chiếu so với `episodes_total`
      or exists (
          select 1
          from (
              select
                  count(*) as so_dong,
                  count(*) filter (where e.airing_at is not null) as so_dong_ngay,
                  count(distinct e.airing_at::date) as so_ngay
              from public.episodes e
              where e.anime_id = a.id
          ) t
          where t.so_dong_ngay - t.so_ngay >= 3
            and t.so_dong <> a.episodes_total
      )
      -- (3) hoặc ĐÃ CHIẾU XONG mà còn thiếu tập
      or (
          a.status = 'FINISHED'
          and (select count(*) from public.episodes e where e.anime_id = a.id)
              < a.episodes_total
      )
  );

comment on view public.anime_thieu_tap is
  'Anime có episodes_total > 0 nhưng (1) danh sách tập TRỐNG, (2) có >= 3 dòng '
  'dư so với số ngày chiếu và số dòng <> episodes_total (cùng ngưỡng qa.py), '
  'hoặc (3) FINISHED mà số tập < episodes_total. Job TMDB dùng để lấp.';

grant select on public.anime_thieu_tap to anon, authenticated;
