-- ─────────────────────────────────────────────────────────────────────────────
-- 20261103_ingest_unmatched.sql
--
-- VÌ SAO CẦN: job C (YouTube → streaming_links) chỉ in danh sách "tên series
-- chưa khớp" ra TERMINAL. Đo 02/11/2026:
--   · 163 bộ / 2028 tập metadata nhưng **chỉ 30 bộ có video**;
--   · 94 bộ liệt kê đủ tập mà **0 video** (black-clover 170, one-punch-man-2 12…);
--   · `youtube --deep` ghi 293 link nhưng tổng link KHÔNG đổi (đều là upsert đè)
--     ⇒ không thể biết là "Muse VN không có video đó" hay "hỏng ghép tên".
--
-- Terminal là nơi thông tin CHẾT: log GitHub Actions hết hạn sau 90 ngày, log
-- trên máy người dùng thì mất khi tắt shell. Không ai — kể cả người vận hành —
-- trả lời được câu "tuần này còn tên nào chưa khớp?" mà không chạy lại job.
--
-- Bảng này biến danh sách đó thành DỮ LIỆU:
--   kind = 'unmatched' → tiêu đề video không ghép được với bộ nào
--   kind = 'review'    → ghép được nhưng số tập VƯỢT tổng ⇒ cố ý không ghi
--                        (nghi sai bộ/mùa, xem `_link_rows`)
--
-- `last_seen_at` cho phép job C xoá tên đã khớp ở lần chạy sau (prune) ⇒ bảng
-- luôn phản ánh HIỆN TẠI, không phải lịch sử tích luỹ.
--
-- Idempotent: chạy nhiều lần không lỗi.
-- ─────────────────────────────────────────────────────────────────────────────

create table if not exists ingest_unmatched (
  id          bigserial primary key,
  source      text        not null default 'youtube',
  channel     text        not null,
  series_name text        not null,
  kind        text        not null default 'unmatched'
              check (kind in ('unmatched', 'review')),
  videos      int         not null default 0,
  first_seen_at timestamptz not null default now(),
  last_seen_at  timestamptz not null default now(),
  unique (source, channel, series_name, kind)
);

comment on table ingest_unmatched is
  'Tên series trong tiêu đề video chưa ghép được với anime (hoặc vượt tổng số '
  'tập). Ghi bởi job C mỗi lần chạy; tên đã khớp sẽ bị xoá ở lần chạy sau.';

-- Tên chưa khớp NÊN ĐƯỢC XEM thường xuyên (để thêm alias) — index theo số video
-- để mở ra là thấy ngay cái đáng sửa nhất.
create index if not exists ingest_unmatched_videos_idx
  on ingest_unmatched (videos desc);

alter table ingest_unmatched enable row level security;

-- Không policy nào: chỉ service key (ingest worker) đọc/ghi được. Đây là dữ
-- liệu VẬN HÀNH, không phải dữ liệu cho app.
