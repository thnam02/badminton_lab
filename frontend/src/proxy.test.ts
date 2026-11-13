// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { config, proxy } from "./proxy";

const SECRET = "cross-check-secret";
const COACH_TOKEN =
  "eyJyb2xlIjoiY29hY2giLCJleHAiOjMyNzY4MDAwMDB9.fVbZgDTnqRAl8k1NJBMb2_UoAI-l8Rag9XNQitVh8wM";

function request(path: string, cookie?: string) {
  return new NextRequest(`http://localhost:3000${path}`, {
    headers: cookie ? { cookie: `bl_session=${cookie}` } : {},
  });
}

beforeEach(() => {
  process.env.SESSION_SECRET = SECRET;
});

afterEach(() => {
  delete process.env.SESSION_SECRET;
});

describe("proxy", () => {
  it("only runs on the admin and coach areas", () => {
    expect(config.matcher).toEqual(["/admin/:path*", "/coach/:path*"]);
  });

  it("redirects signed-out visitors to the login page", async () => {
    const res = await proxy(request("/coach/datasets/abc"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/login?next=%2Fcoach%2Fdatasets%2Fabc"
    );
  });

  it("lets the coach into /coach and sends them away from /admin", async () => {
    const ok = await proxy(request("/coach", COACH_TOKEN));
    expect(ok.headers.get("location")).toBeNull();
    const blocked = await proxy(request("/admin/datasets/new", COACH_TOKEN));
    expect(blocked.headers.get("location")).toBe("http://localhost:3000/coach");
  });

  it("rejects a cookie signed with another secret", async () => {
    process.env.SESSION_SECRET = "rotated";
    const res = await proxy(request("/coach", COACH_TOKEN));
    expect(res.headers.get("location")).toBe("http://localhost:3000/login?next=%2Fcoach");
  });
});
