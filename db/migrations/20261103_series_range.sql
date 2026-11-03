-- Khoảng số tập Muse VN thực sự đã đăng, cho TỪNG tên series trên kênh.
--
-- VÌ SAO CẦN (03/11/2026): Muse đánh số tập CỘNG DỒN qua các mùa
-- (Slime S1 1–24, S2 25–48, S3 49–72) và nhiều khi bỏ hẳn chữ "S3" khỏi tiêu đề
-- (kiểm bằng oEmbed: https://youtu.be/iry712JcyDc = "…Slime - Tập 13").
-- Muốn định tuyến "tập 13" về đúng mùa thì phải biết CẢ khoảng đã thấy, không
-- chỉ tập của lần chạy này: RSS chỉ trả ~15 video/kênh, lần chạy sau chỉ thấy
-- tập 70–72 ⇒ nếu chỉ dùng khoảng của lần chạy thì mô hình đánh số sai mùa.
create table if not exists youtube_series_range (
  channel     text not null,
  series_name text not null,
  ep_min      int  not null default 0,
  ep_max      int  not null default 0,
  updated_at  timestamptz not null default now(),
  primary key (channel, series_name)
);

alter table youtube_series_range enable row level security;

comment on table youtube_series_range is
  'Tên series trên kênh YouTube → khoảng số tập đã thấy (để định tuyến tập cộng dồn qua các mùa).';

-- Nạp sẵn khoảng đã biết từ chẩn đoán cũ (job C đã ghi `max_episode` cho mọi
-- tên chưa ghép). `ep_min = 1` là giả định AN TOÀN: nếu sai, `_phu()` của
-- franchise sẽ không phủ và job C giữ nguyên hành vi cũ (không đoán bừa).
insert into youtube_series_range (channel, series_name, ep_min, ep_max)
select channel, series_name, 1, max_episode
from ingest_unmatched
where max_episode > 0
on conflict (channel, series_name) do update
  set ep_min = least(youtube_series_range.ep_min, excluded.ep_min),
      ep_max = greatest(youtube_series_range.ep_max, excluded.ep_max);
