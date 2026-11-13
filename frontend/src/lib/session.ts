/**
 * Session cookie check shared by the proxy (server) and tests.
 * Format, written by the backend (app/auth.py): base64url(JSON {role, exp}).base64url(HMAC-SHA256).
 */

export const SESSION_COOKIE = "bl_session";

export type Role = "admin" | "coach";

export type SessionInfo = { role: Role; exp: number };

function base64UrlEncode(bytes: ArrayBuffer): string {
  let binary = "";
  for (const b of new Uint8Array(bytes)) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlDecode(text: string): string {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  return atob(padded);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function verifySession(
  token: string | undefined,
  secret: string | undefined,
  nowSeconds: number = Date.now() / 1000
): Promise<SessionInfo | null> {
  if (!token || !secret) return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [payload, signature] = parts;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const expected = base64UrlEncode(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload))
  );
  if (!timingSafeEqual(signature, expected)) return null;
  try {
    const data = JSON.parse(base64UrlDecode(payload)) as { role?: unknown; exp?: unknown };
    if ((data.role !== "admin" && data.role !== "coach") || typeof data.exp !== "number") return null;
    if (data.exp < nowSeconds) return null;
    return { role: data.role, exp: data.exp };
  } catch {
    return null;
  }
}

/** Where a signed-in user of this role belongs. */
export function homeFor(role: Role): string {
  return role === "admin" ? "/admin" : "/coach";
}

/** The redirect for a page request, or null to let it through. */
export function guardRedirect(pathname: string, session: SessionInfo | null): string | null {
  const area = pathname.startsWith("/admin") ? "admin" : pathname.startsWith("/coach") ? "coach" : null;
  if (area === null) return null;
  if (!session) return `/login?next=${encodeURIComponent(pathname)}`;
  if (session.role !== area) return homeFor(session.role);
  return null;
}
