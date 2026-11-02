-- ============================================================
-- AniStream — Schema Postgres / Supabase (MVP → v1)
-- Chạy trong Supabase SQL Editor (hoặc psql).
-- Triết lý: metadata là "bản sao có kiểm soát" của AniList/Kitsu,
--          KHÔNG lưu file video. Link xem trỏ tới nền tảng hợp pháp.
-- ============================================================

create extension if not exists "pgcrypto";
create extension if not exists "pg_trgm";      -- search mờ (fuzzy) theo tên

-- ── ENUM ────────────────────────────────────────────────────
do $$ begin
  create type anime_status as enum
    ('FINISHED','RELEASING','NOT_YET_RELEASED','CANCELLED','HIATUS');
exception when duplicate_object then null; end $$;

do $$ begin
  create type watch_status as enum
    ('watching','plan_to_watch','completed','on_hold','dropped');
exception when duplicate_object then null; end $$;

do $$ begin
  create type media_season as enum ('WINTER','SPRING','SUMMER','FALL');
exception when duplicate_object then null; end $$;

-- ── 1. ANIME (catalog) ──────────────────────────────────────
create table if not exists anime (
  id              bigserial primary key,
  slug            text        not null unique,          -- 'sousou-no-frieren'
  anilist_id      bigint      unique,                   -- khóa ngoại chuẩn
  mal_id          bigint      unique,
  kitsu_id        text        unique,
  tmdb_id         bigint,                               -- KHÔNG unique: nhiều
                                                        -- mùa AniList dùng chung
                                                        -- 1 series TMDB

  title_romaji    text        not null,
  title_english   text,
  title_native    text,
  title_vi        text,                                 -- từ TMDB vi-VN hoặc dịch tay
  synopsis_vi     text,                                 -- bản dịch tiếng Việt (TMDB/dịch tay)
  synopsis_original text,                               -- mô tả gốc từ AniList (dự phòng khi chưa dịch)

  cover_url       text,
  banner_url      text,
  trailer_url     text,

  year            smallint,
  season          media_season,
  status          anime_status,
  format          text,                                 -- TV | MOVIE | OVA | ONA | TV_SHORT
  episodes_total  smallint,
  duration_min    smallint,
  score           numeric(4,1),                         -- 0–10 (đã chuẩn hóa)
  popularity      int         default 0,
  genres          text[]      default '{}',
  studios         text[]      default '{}',

  -- điều khiển ingest
  source          text        not null default 'anilist',
  is_published    boolean     not null default true,
  last_synced_at  timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists anime_title_trgm_idx
  on anime using gin ((coalesce(title_vi, title_romaji)) gin_trgm_ops);
create index if not exists anime_genres_idx on anime using gin (genres);
create index if not exists anime_season_idx on anime (season, year);
create index if not exists anime_popularity_idx on anime (popularity desc);

-- ── 2. EPISODES ─────────────────────────────────────────────
create table if not exists episodes (
  id             bigserial primary key,
  anime_id       bigint not null references anime(id) on delete cascade,
  number         int    not null,
  title          text,
  title_vi       text,
  thumbnail_url  text,
  airing_at      timestamptz,                           -- từ AniList airingAt
  duration_min   smallint,
  is_filler      boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (anime_id, number)
);

create index if not exists episodes_airing_idx on episodes (airing_at desc);

-- ── 3. STREAMING LINKS (deep link hợp pháp) ─────────────────
create table if not exists streaming_links (
  id             bigserial primary key,
  anime_id       bigint not null references anime(id) on delete cascade,
  episode_number int not null default 0,                -- 0 = link cho cả bộ
  platform       text not null,                         -- netflix|crunchyroll|bilibili|muse_vn|fpt_play|youtube...
  region         char(2) not null default 'VN',
  url            text not null,
  kind           text not null default 'official',      -- official|trailer|free_legal
  is_verified    boolean not null default false,
  verified_at    timestamptz,
  created_at     timestamptz not null default now(),
  unique (anime_id, platform, region, episode_number)
);
-- chống trùng cùng 1 video được gán 2 lần
create unique index if not exists streaming_links_url_uidx
  on streaming_links (platform, url);

create index if not exists streaming_links_anime_idx on streaming_links (anime_id);

-- ── 4. PROFILES ─────────────────────────────────────────────
create table if not exists profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  username     text unique,
  display_name text,
  avatar_url   text,
  locale       text not null default 'vi',
  plan         text not null default 'free',            -- free|plus
  created_at   timestamptz not null default now()
);

-- ── 5. WATCHLIST (theo dõi + tiến độ) ───────────────────────
create table if not exists watchlist (
  user_id     uuid not null references profiles(id) on delete cascade,
  anime_id    bigint not null references anime(id) on delete cascade,
  status      watch_status not null default 'plan_to_watch',
  progress    int not null default 0,                   -- số tập đã xem
  score       smallint check (score between 1 and 10),
  note        text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (user_id, anime_id)
);

-- ── 6. WATCH HISTORY (resume + "xem tiếp") ──────────────────
create table if not exists watch_history (
  id               bigserial primary key,
  user_id          uuid not null references profiles(id) on delete cascade,
  anime_id         bigint not null references anime(id) on delete cascade,
  episode_number   int not null,
  position_sec     int not null default 0,
  completed        boolean not null default false,
  watched_at       timestamptz not null default now(),
  unique (user_id, anime_id, episode_number)
);

create index if not exists watch_history_recent_idx
  on watch_history (user_id, watched_at desc);

-- ── 7. PUSH / THEO DÕI TẬP MỚI ──────────────────────────────
create table if not exists push_tokens (
  user_id    uuid not null references profiles(id) on delete cascade,
  token      text not null,
  platform   text not null,                             -- ios|android|desktop|web
  created_at timestamptz not null default now(),
  primary key (user_id, token)
);

create table if not exists episode_alerts (
  user_id    uuid not null references profiles(id) on delete cascade,
  anime_id   bigint not null references anime(id) on delete cascade,
  channel    text not null default 'push',              -- push|email
  enabled    boolean not null default true,
  primary key (user_id, anime_id)
);


-- ── 7b. PUSH SUBSCRIPTIONS (thay episode_alerts ở v1) ───────
-- Thiết kế để hoạt động KHÔNG cần đăng nhập: mỗi thiết bị có device_id ngẫu nhiên
-- do app sinh và lưu cục bộ. anime_ids = danh sách bộ người dùng muốn nhận tin
-- (đồng bộ từ watchlist khi thay đổi). Khi có auth (bước 4) thì gắn thêm user_id.
create table if not exists push_subscriptions (
  id         bigserial primary key,
  device_id  text not null,
  token      text not null,
  platform   text not null check (platform in ('ios','android','desktop','web')),
  user_id    uuid references profiles(id) on delete set null,  -- nullable: chưa cần login
  anime_ids  bigint[] not null default '{}',
  locale     text not null default 'vi',
  is_active  boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (device_id, token)
);

create index if not exists push_subs_anime_idx on push_subscriptions using gin (anime_ids);
create index if not exists push_subs_active_idx on push_subscriptions (is_active) where is_active;

-- ── 7c. SENT EPISODE PUSHES (chống gửi trùng) ───────────────
-- Mỗi cặp (anime, tập) chỉ gửi 1 lần. Cron chạy lại nhiều lần cũng không spam.
create table if not exists sent_episode_pushes (
  anime_id       bigint not null references anime(id) on delete cascade,
  episode_number int    not null,
  sent_at        timestamptz not null default now(),
  recipients     int not null default 0,
  failed         int not null default 0,
  primary key (anime_id, episode_number)
);

-- ── 7d. RLS cho push_subscriptions ──────────────────────────
alter table push_subscriptions enable row level security;

-- app ẩn danh (anon key) được tự tạo/sửa dòng CỦA MÌNH (user_id phải null).
-- Không cho đọc (không có policy select) → không ai liệt kê được token của người khác.
-- `device_id` là chuỗi 128-bit ngẫu nhiên do app sinh → kiểm tra nó qua header
-- để người khác KHÔNG sửa được dòng của mình. Chỉ `user_id is null` là quá lỏng:
-- ai có anon key cũng PATCH được mọi dòng chưa gắn user (tắt thông báo của
-- người khác, đổi anime_ids...). App gửi header `x-device-id` (push_service.dart).
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

drop policy if exists "user own subs" on push_subscriptions;
create policy "user own subs" on push_subscriptions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- sent_episode_pushes: KHÔNG tạo policy → chỉ service_role (cron) truy cập được.
alter table sent_episode_pushes enable row level security;

-- ── 8. INGEST LOG (bắt buộc có, để debug cron) ──────────────
create table if not exists ingest_runs (
  id            bigserial primary key,
  source        text not null,                          -- anilist|kitsu|tmdb
  job           text not null,                          -- schedule|catalog|enrich
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  rows_upserted int default 0,
  ok            boolean,
  error         text
);

-- ── 9. updated_at tự động ───────────────────────────────────
create or replace function touch_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

do $$
declare t text;
begin
  foreach t in array array['anime','episodes','watchlist','push_subscriptions'] loop
    execute format(
      'drop trigger if exists trg_%1$s_touch on %1$s;
       create trigger trg_%1$s_touch before update on %1$s
       for each row execute function touch_updated_at();', t);
  end loop;
end $$;

-- ── 9b. TỰ TẠO PROFILE KHI ĐĂNG KÝ ──────────────────────────
-- `watchlist.user_id` → `profiles(id)` → `auth.users(id)`. Không có trigger này
-- thì user đăng nhập xong bấm 🔖 sẽ lỗi 23503 (foreign key violates) vì chưa có
-- dòng `profiles` tương ứng. (Chi tiết: db/migrations/20261101_auth_profile_trigger.sql)
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
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

insert into public.profiles (id)
select u.id from auth.users u
on conflict (id) do nothing;

-- ── 10. RLS (Supabase) ──────────────────────────────────────
-- Catalog là dữ liệu công khai: chỉ đọc.
alter table anime            enable row level security;
alter table episodes         enable row level security;
alter table streaming_links  enable row level security;
alter table profiles         enable row level security;
alter table watchlist        enable row level security;
alter table watch_history    enable row level security;
alter table push_tokens      enable row level security;
alter table episode_alerts   enable row level security;
-- ingest_runs: bật RLS, KHÔNG tạo policy → chỉ service_role (cron) đọc/ghi được.
-- Thiếu dòng này thì ai có anon key cũng đọc/ghi/xoá được bảng audit.
alter table ingest_runs      enable row level security;

drop policy if exists "catalog read" on anime;
create policy "catalog read" on anime for select using (is_published);

drop policy if exists "episodes read" on episodes;
create policy "episodes read" on episodes for select using (true);

drop policy if exists "links read" on streaming_links;
create policy "links read" on streaming_links for select using (is_verified);

drop policy if exists "own profile" on profiles;
create policy "own profile" on profiles for all
  using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "own watchlist" on watchlist;
create policy "own watchlist" on watchlist for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own history" on watch_history;
create policy "own history" on watch_history for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own tokens" on push_tokens;
create policy "own tokens" on push_tokens for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own alerts" on episode_alerts;
create policy "own alerts" on episode_alerts for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Ghi catalog chỉ qua service_role key (Edge Function / cron) → không cần policy insert.

-- ── 11. VIEW tiện cho API ───────────────────────────────────
create or replace view v_anime_card as
select a.id, a.slug, a.title_vi, a.title_romaji, a.title_english,
       a.cover_url, a.year, a.season, a.status, a.score, a.genres,
       a.episodes_total,
       e.next_episode, e.next_airing_at
from anime a
left join lateral (
  select number as next_episode, airing_at as next_airing_at
  from episodes
  where anime_id = a.id and airing_at > now()
  order by airing_at asc limit 1
) e on true
where a.is_published;

-- ── 12. VIEW kho phim FREE HỢP PHÁP (lớp 1 của app) ────────
create or replace view v_free_catalog as
select a.id as anime_id, a.slug, coalesce(a.title_vi, a.title_romaji) as title,
       a.cover_url, a.score, a.year,
       sl.episode_number, sl.platform, sl.region, sl.url,
       sl.is_verified, a.updated_at
from streaming_links sl
join anime a on a.id = sl.anime_id
where sl.kind = 'free_legal' and sl.is_verified and a.is_published
order by a.popularity desc, sl.episode_number asc;

-- ── 13. VIEW "tập mới hôm nay" (feed chính của app) ─────────
create or replace view v_new_episodes as
select e.id, e.anime_id, e.number, e.airing_at, e.title,
       a.slug, a.title_vi, a.title_romaji, a.cover_url, a.score
from episodes e
join anime a on a.id = e.anime_id
where e.airing_at between now() - interval '2 days' and now() + interval '7 days'
  and a.is_published
order by e.airing_at asc;
