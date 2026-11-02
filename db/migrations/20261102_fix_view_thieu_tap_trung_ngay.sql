-- View `anime_thieu_tap`: bỏ qua tập trùng ngày chiếu HỢP LỆ.
--
-- Vì sao: định nghĩa cũ coi "có 2 tập cùng NGÀY chiếu" là danh sách tập SAI.
-- Đo 02/11/2026: 4 bộ bị kết luận oan và bị job TMDB hỏi lại MỖI NGÀY:
--   `chitose-kun-wa-ramune-bin-no-naka`      13 tập / 12 ngày (double-episode)
--   `tensei-goblin-dakedo-shitsumon-aru`     tập 5 và 6 khác GIỜ trong ngày
--   `yasei-no-last-boss-ga-arawareta-2nd`    idem
--   `fool-night`                             3 tập cùng ngày (AniList phát 1 lượt)
--
-- Ngưỡng mới GIỐNG HỆT `ingest/qa.py` (`tap_trung_ngay_chieu`):
--   dư >= 3 dòng so với số NGÀY chiếu  VÀ  tổng số dòng <> `episodes_total`
-- (ca thật `tensei-…-3rd-season`: 24 dòng / 12 ngày, tổng 12 → dư 12, 24 <> 12).
-- Một hai dòng dư là double-episode bình thường nên KHÔNG được đánh dấu.
--
-- "Dư" chỉ tính trên các dòng CÓ `airing_at`: nhiều bộ (fairy-tail 66/175,
-- the-new-gate, dark-gathering…) có tập thiếu ngày chiếu — đó là lỗ hổng khác
-- (`so_dong - so_ngay` của chúng = 0), KHÔNG phải dấu hiệu đánh số lại.
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
  );

comment on view public.anime_thieu_tap is
  'Anime có episodes_total > 0 nhưng danh sách tập TRỐNG, hoặc có >= 3 dòng dư '
  'so với số ngày chiếu và số dòng <> episodes_total (cùng ngưỡng với '
  'ingest/qa.py). Tập trùng ngày HỢP LỆ (double-episode) không còn bị đánh dấu.';

grant select on public.anime_thieu_tap to anon, authenticated;
