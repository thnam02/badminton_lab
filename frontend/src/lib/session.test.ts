// @vitest-environment node
import { describe, expect, it } from "vitest";
import { guardRedirect, verifySession } from "./session";

// Signed by the backend (app/auth.py create_token) with this secret.
const SECRET = "cross-check-secret";
const COACH_TOKEN =
  "eyJyb2xlIjoiY29hY2giLCJleHAiOjMyNzY4MDAwMDB9.fVbZgDTnqRAl8k1NJBMb2_UoAI-l8Rag9XNQitVh8wM";
const ADMIN_TOKEN =
  "eyJyb2xlIjoiYWRtaW4iLCJleHAiOjMyNzY4MDAwMDB9.j7twXi3p0fhrTStHJ4Jm4HrlpoQcMvLGElG6iKD2Jr0";

describe("verifySession", () => {
  it("accepts tokens the backend signed", async () => {
    expect(await verifySession(COACH_TOKEN, SECRET, 1_700_000_000)).toEqual({
      role: "coach",
      exp: 3_276_800_000,
    });
    expect((await verifySession(ADMIN_TOKEN, SECRET, 1_700_000_000))?.role).toBe("admin");
  });

  it("rejects tampered, expired, unsigned or wrongly signed tokens", async () => {
    const [payload, sig] = COACH_TOKEN.split(".");
    const adminPayload = ADMIN_TOKEN.split(".")[0];
    expect(await verifySession(`${adminPayload}.${sig}`, SECRET)).toBeNull();
    expect(await verifySession(`${payload}.${sig.slice(0, -2)}AA`, SECRET)).toBeNull();
    expect(await verifySession(COACH_TOKEN, "other-secret")).toBeNull();
    expect(await verifySession(COACH_TOKEN, SECRET, 3_276_800_001)).toBeNull();
    expect(await verifySession(undefined, SECRET)).toBeNull();
    expect(await verifySession(COACH_TOKEN, undefined)).toBeNull();
    expect(await verifySession("not-a-token", SECRET)).toBeNull();
  });
});

describe("guardRedirect", () => {
  const coach = { role: "coach" as const, exp: 0 };
  const admin = { role: "admin" as const, exp: 0 };

  it("sends visitors without a session to the login page", () => {
    expect(guardRedirect("/coach/datasets/x", null)).toBe("/login?next=%2Fcoach%2Fdatasets%2Fx");
    expect(guardRedirect("/admin", null)).toBe("/login?next=%2Fadmin");
  });

  it("keeps each role in its own area", () => {
    expect(guardRedirect("/admin/datasets/new", coach)).toBe("/coach");
    expect(guardRedirect("/coach", admin)).toBe("/admin");
    expect(guardRedirect("/coach/datasets/x", coach)).toBeNull();
    expect(guardRedirect("/admin", admin)).toBeNull();
  });

  it("leaves the player pages alone", () => {
    expect(guardRedirect("/analyze", null)).toBeNull();
    expect(guardRedirect("/history", null)).toBeNull();
  });
});
