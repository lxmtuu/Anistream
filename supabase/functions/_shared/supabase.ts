/**
 * supabase.ts — client server-side.
 *
 * Dùng SERVICE_ROLE key: các function này chỉ ĐỌC catalog công khai nên không có
 * rủi ro leo thang quyền. Không bao giờ trả key này về client.
 * (App chỉ giữ anon key; RLS vẫn bảo vệ dữ liệu người dùng nếu sau này client
 *  gọi thẳng PostgREST.)
 */
import { createClient, SupabaseClient } from "npm:@supabase/supabase-js@2";

let cached: SupabaseClient | null = null;

export function adminClient(): SupabaseClient {
  if (cached) return cached;

  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (!url || !key) {
    throw new Error(
      "Thiếu SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. " +
        "Supabase tự inject khi deploy; khi chạy local dùng `supabase functions serve --env-file .env`.",
    );
  }

  cached = createClient(url, key, {
    auth: { persistSession: false },
    global: { headers: { "x-application-name": "anistream-api" } },
  });
  return cached;
}
