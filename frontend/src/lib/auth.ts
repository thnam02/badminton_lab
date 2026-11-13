import { API_BASE } from "./api";
import type { Role } from "./session";

export type Me = { role: Role; name: string };

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* ignore */
  }
  return `Request failed (${res.status})`;
}

export async function login(username: string, password: string): Promise<Me> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as Me;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

/** The signed-in user, or null when not signed in. */
export async function fetchMe(): Promise<Me | null> {
  const res = await fetch(`${API_BASE}/auth/me`, { credentials: "include", cache: "no-store" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as Me;
}
