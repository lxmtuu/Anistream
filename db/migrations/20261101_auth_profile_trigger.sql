-- ============================================================
-- 2026-11-01 · (1) Trigger tạo `profiles` khi có user mới
--                   (2) Siết RLS của `push_subscriptions`
--
-- Chạy file này SAU db/schema.sql. An toàn khi chạy lại nhiều lần (idempotent).
-- Nếu bạn chưa từng chạy schema.sql: dán schema.sql trước, rồi file này.
-- ============================================================

-- ── (1) VÌ SAO CẦN ─────────────────────────────────────────
-- `watchlist.user_id` tham chiếu `profiles(id)`, mà `profiles.id` tham chiếu
-- `auth.users(id)`. Nhưng KHÔNG có gì tạo dòng `profiles` khi người dùng đăng ký.
-- Hệ quả: ngay khi bật Supabase Auth, user đăng nhập xong bấm 🔖 →
--   insert into watchlist ... → lỗi 23503 (foreign key violates)
-- và tính năng "đồng bộ thư viện" chết ngay từ bước đầu tiên.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer              -- cần quyền ghi profiles dù đang chạy dưới user mới
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name, avatar_url, locale)
  values (
    new.id,
    coalesce(
      nullif(new.raw_user_meta_data->>'full_name', ''),
      nullif(new.raw_user_meta_data->>'name', ''),
      nullif(split_part(coalesce(new.email, ''), '@', 1), ''),
      'Người dùng AniStream'
    ),
    nullif(new.raw_user_meta_data->>'avatar_url', ''),
    coalesce(nullif(new.raw_user_meta_data->>'locale', ''), 'vi')
  )
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Tạo profile cho những user đã tồn tại trước khi có trigger này.
insert into public.profiles (id)
select u.id from auth.users u
on conflict (id) do nothing;


-- ── (2) VÌ SAO CẦN ─────────────────────────────────────────
-- Policy cũ chỉ kiểm tra `user_id is null`. Nghĩa là BẤT KỲ ai có anon key
-- (tức là ai cài app) đều có thể PATCH/SỬA MỌI dòng chưa gắn user:
--   - đặt is_active = false  → giết thông báo "tập mới" của người khác
--   - đổi anime_ids          → bắn thông báo sai bộ cho người khác
--   - INSERT token rác       → cron gửi vào hư không, tốn quota FCM
-- `device_id` là chuỗi 128-bit ngẫu nhiên do app sinh, nên kiểm tra nó qua
-- header là đủ chặt: muốn sửa dòng của ai phải biết device_id của người đó.

drop policy if exists "anon insert own device" on push_subscriptions;
create policy "anon insert own device" on push_subscriptions
  for insert with check (
    user_id is null
    and device_id = coalesce(
      nullif(current_setting('request.headers', true), '')::json ->> 'x-device-id', '')
  );

drop policy if exists "anon update own device" on push_subscriptions;
create policy "anon update own device" on push_subscriptions
  for update using (
    user_id is null
    and device_id = coalesce(
      nullif(current_setting('request.headers', true), '')::json ->> 'x-device-id', '')
  ) with check (
    user_id is null
    and device_id = coalesce(
      nullif(current_setting('request.headers', true), '')::json ->> 'x-device-id', '')
  );

-- ── (3) ingest_runs cần RLS ────────────────────────────────
-- Bảng audit của cron nằm trong schema `public` nên PostgREST cho phép truy cập
-- bằng anon key nếu không bật RLS. Không tạo policy nào → chỉ service_role vào được.
alter table public.ingest_runs enable row level security;

-- Không có policy SELECT: không ai đọc được token của người khác.
-- App phải gửi kèm header `x-device-id` cho mọi lệnh ghi (xem push_service.dart).
--
-- Ghi chú kỹ thuật: `current_setting('request.headers')` là cách Supabase cho
-- phép RLS đọc header. Nếu PostgREST tương lai bỏ nó → các lệnh ghi này bị từ
-- chối (fail-closed, không phải fail-open) và log app sẽ in "sync lỗi (…)";
-- khi đó chuyển sang Edge Function `/subscribe` dùng service_role.
