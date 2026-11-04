-- Preserve distinct official YouTube uploads (e.g. Vietsub + lồng tiếng) for one episode.
-- A YouTube URL is the identity of a video; episode_number is a grouping key, not unique.
-- The edge DTO selects a default and exposes all options to the detail page.
alter table public.streaming_links
  add column if not exists source_title text,
  drop constraint if exists streaming_links_anime_id_platform_region_episode_number_key;

create index if not exists streaming_links_episode_lookup_idx
  on public.streaming_links (anime_id, episode_number, platform, region);
