-- ─────────────────────────────────────────────────────────────────────────────
-- 20261103_anime_alias.sql
--
-- VÌ SAO CẦN: Muse VN đăng bằng **tên tiếng Việt** ("Đại chiến người Khổng Lồ",
-- "Thất hình đại tội", "Lúc đó tôi đã chuyển sinh thành Slime"). Những tên này
-- KHÔNG có trong AniList, và TMDB chỉ có bản dịch cho một phần.
--
-- Đo 03/11/2026 sau khi sửa ghép tên: 51 tên vẫn không vào được DB / 601 video,
-- trong đó những bộ lớn nhất của kênh — mà DB hoàn toàn KHÔNG có entry:
--   "Đại chiến người Khổng Lồ S1"  50 video   (AniList: Shingeki no Kyojin)
--   "Đại chiến người Khổng Lồ S3"  45 video
--   "Thất hình đại tội S2/S3"      24 video mỗi mùa
--   "SPY×FAMILY S3"                26 video
-- Cầu nối duy nhất tin được: TMDB search theo TÊN VIỆT → `original_name` (tiếng
-- Nhật) → AniList search theo tên Nhật. Kết quả (bộ nào ↔ tên Việt nào) phải
-- được LƯU LẠI, nếu không lần chạy sau lại phải search 51 tên × 3 request.
--
-- `alias_key` là tên đã chuẩn hoá ở phía Python (`_khoa_ten`: NFKC + casefold +
-- bỏ dấu câu) để job C tra cứu O(1) và để unique index chặn trùng.
--
-- Kèm: `ingest_unmatched.max_episode` — số tập LỚN NHẤT thấy trong tiêu đề. Cần
-- để chọn đúng entry AniList (bộ 25 tập vs bộ 12 tập cùng tên).
--
-- Idempotent: chạy nhiều lần không lỗi.
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists anime_alias (
  id         bigserial primary key,
  anime_id   bigint not null references anime(id) on delete cascade,
  alias      text   not null,
  alias_key  text   not null,
  source     text   not null default 'tmdb_vi',
  created_at timestamptz not null default now(),
  unique (anime_id, alias_key)
);

comment on table anime_alias is
  'Tên KHÁC của một bộ (thường là tên tiếng Việt Muse VN dùng trong tiêu đề '
  'video). Job C dựng chỉ mục tên từ đây để ghép video → bộ.';

create index if not exists anime_alias_key_idx on anime_alias (alias_key);

alter table anime_alias enable row level security;

-- `max_episode`: số tập lớn nhất gặp trong tiêu đề của series chưa ghép được.
alter table ingest_unmatched
  add column if not exists max_episode int not null default 0;
