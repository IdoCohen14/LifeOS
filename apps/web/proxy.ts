import { NextResponse, type NextRequest } from "next/server";
import { buildDirectory, scriptPolicy, verifyManifest } from "./lib/csp-manifest.mjs";

let policy: string | undefined;

export function proxy(request: NextRequest) {
  if (process.env.NODE_ENV === "development") return NextResponse.next();
  try {
    policy ??= scriptPolicy(verifyManifest(buildDirectory()).hashes);
    const response = NextResponse.next();
    response.headers.set(
      "Content-Security-Policy",
      request.nextUrl.pathname === "/" ? `${policy}; style-src-attr 'none'` : policy,
    );
    return response;
  } catch {
    // Direct `next start` also fails closed if it bypasses the normal preflight.
    return new NextResponse("LifeOS build verification unavailable", {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
}

export const config = {
  matcher: ["/((?!api(?:/|$)|_next/|sw\\.js$|manifest\\.webmanifest$|offline\\.html$|icon\\.svg$|icon-(?:192|512)\\.png$).*)"],
};
