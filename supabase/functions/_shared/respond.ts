/**
 * respond.ts — chuẩn hoá response, CORS và cache cho mọi Edge Function.
 *
 * Quy ước (xem LO_TRINH_ANIME_APP.md §4):
 *   thành công: { data: ..., meta: { generated_at, ttl } }
 *   lỗi:       { error: { code, message } }
 */

export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, prefer",
  "Access-Control-Max-Age": "86400",
};

export function preflight(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

export interface JsonOptions {
  status?: number;
  /** cache ở CDN (giây) — mặc định 300 */
  maxAge?: number;
  /** 0 = không cache */
  browserMaxAge?: number;
}

export function json<T>(data: T, opts: JsonOptions = {}): Response {
  const { status = 200, maxAge = 300, browserMaxAge = 0 } = opts;
  const headers: Record<string, string> = {
    ...CORS_HEADERS,
    "Content-Type": "application/json; charset=utf-8",
  };
  if (maxAge > 0) {
    headers["Cache-Control"] =
      `public, max-age=${browserMaxAge}, s-maxage=${maxAge}, ` +
      `stale-while-revalidate=${maxAge * 2}`;
  } else {
    headers["Cache-Control"] = "no-store";
  }
  return new Response(JSON.stringify(data), { status, headers });
}

export function ok<T>(data: T, meta: Record<string, unknown> = {}, opts: JsonOptions = {}) {
  return json(
    {
      data,
      meta: { generated_at: new Date().toISOString(), ...meta },
    },
    opts,
  );
}

export type ErrorCode =
  | "bad_request"
  | "unauthorized"
  | "not_found"
  | "rate_limited"
  | "internal";

const STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  unauthorized: 401,
  not_found: 404,
  rate_limited: 429,
  internal: 500,
};

export function fail(code: ErrorCode, message: string): Response {
  return json({ error: { code, message } }, { status: STATUS[code], maxAge: 0 });
}

/** Bọc handler: bắt mọi lỗi để client luôn nhận JSON, không nhận HTML 500. */
export function withGuard(
  handler: (req: Request) => Promise<Response>,
): (req: Request) => Promise<Response> {
  return async (req: Request) => {
    if (req.method === "OPTIONS") return preflight();
    if (req.method !== "GET" && req.method !== "POST") {
      return fail("bad_request", "Chỉ hỗ trợ GET/POST");
    }
    try {
      return await handler(req);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      console.error("unhandled:", message);
      return fail("internal", message);
    }
  };
}
