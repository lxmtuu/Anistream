/**
 * fcm.ts — Firebase Cloud Messaging HTTP v1 (miễn phí, không giới hạn).
 *
 * Vì sao phải dùng v1: "Legacy FCM server key" đã bị Google xoá (2024).
 * v1 yêu cầu OAuth2 access token sinh từ JWT RS256 của service account.
 *
 * Cần secret: FCM_SERVICE_ACCOUNT = nội dung JSON của service account
 *   (Firebase Console → Project settings → Service accounts → Generate new private key)
 *
 *   supabase secrets set FCM_SERVICE_ACCOUNT="$(cat service-account.json)"
 */

interface ServiceAccount {
  project_id: string;
  client_email: string;
  private_key: string;
}

export interface PushPayload {
  title: string;
  body: string;
  data?: Record<string, string>;
  channelId?: string;
}

export interface PushResult {
  ok: boolean;
  /** true = token chết, phải xoá/vô hiệu hoá */
  unregistered: boolean;
  error?: string;
}

let cachedToken: { value: string; expiresAt: number } | null = null;
let cachedAccount: ServiceAccount | null = null;

function account(): ServiceAccount {
  if (cachedAccount) return cachedAccount;
  const raw = Deno.env.get("FCM_SERVICE_ACCOUNT");
  if (!raw) throw new Error("Thiếu secret FCM_SERVICE_ACCOUNT");
  const json = JSON.parse(raw) as ServiceAccount;
  if (!json.project_id || !json.client_email || !json.private_key) {
    throw new Error("FCM_SERVICE_ACCOUNT không hợp lệ (thiếu project_id/client_email/private_key)");
  }
  cachedAccount = json;
  return json;
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pemToPkcs8(pem: string): Uint8Array {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const bin = atob(body);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Access token OAuth2, cache ~55 phút (Google cấp 1 giờ). */
async function accessToken(): Promise<string> {
  const now = Date.now();
  if (cachedToken && cachedToken.expiresAt > now + 60_000) {
    return cachedToken.value;
  }

  const sa = account();
  const header = { alg: "RS256", typ: "JWT" };
  const iat = Math.floor(now / 1000);
  const claims = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/firebase.messaging",
    aud: "https://oauth2.googleapis.com/token",
    iat,
    exp: iat + 3600,
  };

  const enc = new TextEncoder();
  const headerB64 = b64url(enc.encode(JSON.stringify(header)));
  const claimsB64 = b64url(enc.encode(JSON.stringify(claims)));
  const signingInput = `${headerB64}.${claimsB64}`;

  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToPkcs8(sa.private_key),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    enc.encode(signingInput),
  );
  const jwt = `${signingInput}.${b64url(new Uint8Array(sig))}`;

  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt,
    }),
  });

  if (!res.ok) {
    throw new Error(`OAuth2 lỗi ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }

  const json = await res.json() as { access_token: string; expires_in: number };
  cachedToken = {
    value: json.access_token,
    expiresAt: now + (json.expires_in ?? 3600) * 1000,
  };
  return cachedToken.value;
}

/** Gửi 1 thông báo tới 1 thiết bị. */
export async function sendToToken(
  token: string,
  payload: PushPayload,
): Promise<PushResult> {
  const sa = account();
  const url = `https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`;

  const body = {
    message: {
      token,
      notification: { title: payload.title, body: payload.body },
      data: payload.data ?? {},
      android: {
        priority: "high",
        notification: {
          channel_id: payload.channelId ?? "new_episode",
          color: "#7C5CFF",
          sound: "default",
        },
      },
      apns: {
        payload: { aps: { sound: "default", badge: 1 } },
      },
    },
  };

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${await accessToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.ok) return { ok: true, unregistered: false };

    const text = await res.text();
    // UNREGISTERED / NOT_FOUND / INVALID_ARGUMENT (token rỗng) → token chết
    const unregistered =
      res.status === 404 ||
      /UNREGISTERED|NOT_FOUND|registration token is not a valid/i.test(text);

    return { ok: false, unregistered, error: `${res.status} ${text.slice(0, 200)}` };
  } catch (e) {
    return {
      ok: false,
      unregistered: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/** Gửi song song có giới hạn (FCM không có batch endpoint ở v1). */
export async function sendMany(
  targets: { token: string; payload: PushPayload }[],
  concurrency = 12,
): Promise<{ sent: number; failed: number; dead: string[]; errors: string[] }> {
  let sent = 0;
  let failed = 0;
  const dead: string[] = [];
  const errors: string[] = [];

  for (let i = 0; i < targets.length; i += concurrency) {
    const chunk = targets.slice(i, i + concurrency);
    const results = await Promise.all(
      chunk.map((t) => sendToToken(t.token, t.payload)),
    );
    results.forEach((r, idx) => {
      if (r.ok) {
        sent++;
      } else {
        failed++;
        if (r.unregistered) dead.push(chunk[idx].token);
        if (r.error && errors.length < 10) errors.push(r.error);
      }
    });
  }

  return { sent, failed, dead, errors };
}
