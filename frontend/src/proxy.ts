import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, guardRedirect, verifySession } from "@/lib/session";

/** Only the admin may open /admin/*, only the coach /coach/*. The API checks again. */
export async function proxy(request: NextRequest) {
  const session = await verifySession(
    request.cookies.get(SESSION_COOKIE)?.value,
    process.env.SESSION_SECRET
  );
  const target = guardRedirect(request.nextUrl.pathname, session);
  return target ? NextResponse.redirect(new URL(target, request.url)) : NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/coach/:path*"],
};
