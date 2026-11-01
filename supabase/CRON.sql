-- ─────────────────────────────────────────────────────────────────────────────
-- CRON.sql — cron cho ingest, chạy NGAY TRONG Supabase (không cần dịch vụ ngoài).
--
-- Vì sao cần: cron của GitHub Actions trên repo này đã đo được 0 lần chạy trong
-- 10 giờ. Không có gì chạy thì Job A (lịch phát), C (video Muse), D (TMDB),
-- E (mùa mới), F (Jikan) đều đứng im.
--
-- Chạy file này trong Supabase → SQL Editor, THEO THỨ TỰ. Bước 3 cần PAT của bạn.
-- Kiểm lại sau khi xong:  bash scripts/check_cron.sh   (phải exit 0)
-- ─────────────────────────────────────────────────────────────────────────────

-- 1) Bật extension (có sẵn trên Supabase, không tốn phí)
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 2) Bảng giữ cấu hình — RLS bật, KHÔNG có policy ⇒ anon/authenticated không đọc
--    được. Chỉ service_role (chạy phía server) đọc được PAT.
create table if not exists private_cron_config (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
alter table private_cron_config enable row level security;
revoke all on private_cron_config from anon, authenticated;

-- 3) Điền PAT (Fine-grained, chỉ repo lxmtuu/Anistream, quyền Actions: write).
--    Thay github_pat_xxx bằng token của bạn rồi chạy 2 dòng này.
-- insert into private_cron_config (key, value)
--   values ('gh_token', 'github_pat_xxx')
--   on conflict (key) do update set value = excluded.value, updated_at = now();

-- 4) Hàm kích hoạt workflow. `p_command` ∈ schedule|catalog|youtube|tmdb|seasons|jikan|all
--    Trả về id của request (để tra trong bảng net._http_response nếu cần).
create or replace function trigger_ingest(p_command text default 'all')
returns bigint
language plpgsql
security definer
set search_path = public, net, private_cron_config
as $$
declare
  v_token text;
  v_req   bigint;
begin
  select value into v_token from private_cron_config where key = 'gh_token';
  if v_token is null or v_token = '' then
    raise exception 'Chưa có gh_token trong private_cron_config (xem bước 3 của supabase/CRON.sql)';
  end if;

  select net.http_post(
    url     := 'https://api.github.com/repos/lxmtuu/Anistream/actions/workflows/ingest.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization',       'Bearer ' || v_token,
      'Accept',              'application/vnd.github+json',
      'X-GitHub-Api-Version','2022-11-28',
      'Content-Type',        'application/json'
    ),
    body    := jsonb_build_object('ref', 'main',
                                  'inputs', jsonb_build_object('command', p_command)),
    timeout_milliseconds := 15000
  ) into v_req;

  return v_req;
end;
$$;

revoke all on function trigger_ingest(text) from anon, authenticated;

-- 5) Lịch chạy (giờ UTC — VN = UTC+7).
--    Job A: lịch phát, mỗi 30 phút
select cron.schedule(
  'anistream-schedule', '*/30 * * * *',
  $$select trigger_ingest('schedule')$$
);

--    Job C: video Muse VN, mỗi 6 giờ
select cron.schedule(
  'anistream-youtube', '10 */6 * * *',
  $$select trigger_ingest('youtube')$$
);

--    Job D/E/F: TMDB + mùa mới + Jikan, mỗi ngày 20:40 UTC (03:40 giờ VN)
select cron.schedule(
  'anistream-daily', '40 20 * * *',
  $$select trigger_ingest('all')$$
);

-- 6) Kiểm tra
--    select jobid, jobname, schedule, active from cron.job order by jobid;
--    select * from net._http_response order by created desc limit 5;   -- 204 = OK
--    select trigger_ingest('all');                                    -- gọi thử ngay

-- Gỡ lịch (nếu cần):
--    select cron.unschedule('anistream-schedule');
--    select cron.unschedule('anistream-youtube');
--    select cron.unschedule('anistream-daily');
