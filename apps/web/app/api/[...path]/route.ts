import { NextRequest, NextResponse } from "next/server";
import { deploymentConfig } from "@/lib/deployment.server";

const allowed =
  /^(mode|accounts\/(?:register|password|access(?:\/(?:key|recover))?|deletion\/(?:preview|confirm)|oauth\/callback)|session|settings|tasks(?:\/[0-9a-f-]{36})?|events(?:\/[0-9a-f-]{36})?|integrations\/google\/(?:status|config|authorize|callback|sync|calendars|disconnect|events)|integrations\/gmail\/(?:status|authorize|sync|disconnect|messages|queue|review|calendar)|integrations\/braude\/(?:status|config|sync|disconnect|events)|integrations\/moodle\/(?:status|config|sync|disconnect|events|changes)|recovery\/(?:schedule|export|restore\/[0-9a-f-]{36}\/confirm|backups(?:\/[0-9a-f-]{36}(?:\/(?:inspect|restore-preview))?)?)|recommendations(?:\/dismiss)?|push\/(?:config|lookup|subscriptions(?:\/[0-9a-f-]{36})?)|review\/(?:weekly|academic)|recurrence\/(?:preview|confirm|proposals\/[0-9a-f-]{36}|series(?:\/[0-9a-f-]{36}\/(?:deletion-preview|reschedule-preview))?|(?:deletions|reschedules)\/(?:confirm|[0-9a-f-]{36}))|planning\/(?:preferences|suggestions(?:\/(?:propose|dismiss))?|propose|proposals\/[0-9a-f-]{36})|briefings\/(?:schedule|check)|notifications(?:\/(?:preferences|read|action))?|assistant\/(?:help|status|chat|confirm|history|preferences|requests(?:\/[0-9a-f-]{36})?)|academic\/(?:(?:course-batches|timetable-batches)\/(?:preview|[0-9a-f-]{36}(?:\/confirm)?)|calendar|(?:terms|courses|items|timetable|grades)(?:\/[0-9a-f-]{36})?|documents(?:\/search|\/[0-9a-f-]{36}(?:\/download)?)?))$/;
export const dynamic = "force-dynamic";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  let deployment;
  try { deployment = deploymentConfig(); }
  catch { return NextResponse.json({ detail: "Invalid deployment configuration" }, { status: 503 }); }
  const origin = deployment.origin;
  if (request.headers.get("host") !== new URL(origin).host)
    return NextResponse.json({ detail: `Use ${origin}` }, { status: 403 });
  const accountMode = deployment.accountMode;
  const oauthCallback =
    request.method === "GET" &&
    (request.nextUrl.pathname === (accountMode ? "/api/accounts/oauth/callback" : "/api/integrations/google/callback"));
  if (request.headers.get("sec-fetch-site") === "cross-site" && !oauthCallback)
    return NextResponse.json({ detail: "Untrusted site" }, { status: 403 });
  if (request.method !== "GET" && request.headers.get("origin") !== origin)
    return NextResponse.json({ detail: "Untrusted origin" }, { status: 403 });
  const path = (await context.params).path.join("/");
  if (!allowed.test(path))
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  const backendPath = accountMode && path !== "mode" && !path.startsWith("accounts/")
    ? path === "session" ? "accounts/session" : `accounts/workspace/${path}`
    : path;
  const key = process.env.LIFEOS_API_KEY;
  if (!key)
    return NextResponse.json(
      { detail: "Start LifeOS with scripts/run.py" },
      { status: 503 },
    );
  let body: Uint8Array | undefined;
  if (request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > (path === "academic/documents" ? 12 * 1024 * 1024 : 65536)) {
        await reader.cancel();
        return NextResponse.json(
          { detail: "Request too large" },
          { status: 413 },
        );
      }
      chunks.push(value);
    }
    body = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.length;
    }
  }
  try {
    const upstream = await fetch(
      `http://127.0.0.1:${deployment.apiPort}/${backendPath}${request.nextUrl.search}`,
      {
        method: request.method,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(
          path === "assistant/chat" ? 85000 : path.startsWith("recovery/") ? 45000 : path === "academic/documents" ? 20000 : 15000,
        ),
        headers: {
          "X-LifeOS-Key": key,
          "Content-Type": "application/json",
          Cookie: request.headers.get("cookie") || "",
          "X-CSRF-Token": request.headers.get("x-csrf-token") || "",
          ...(request.headers.get("origin")
            ? { Origin: request.headers.get("origin")! }
            : {}),
        },
        ...(body ? { body: Buffer.from(body) } : {}),
      },
    );
    const headers = new Headers({
      "Cache-Control": "no-store",
      "Content-Type": "application/json",
    });
    const cookie = upstream.headers.get("set-cookie");
    if (upstream.status === 303) {
      const location = upstream.headers.get("location");
      if (location?.startsWith("/?view=settings")) {
        const redirect = NextResponse.redirect(new URL(location, origin), 303);
        redirect.headers.set("Cache-Control", "no-store");
        return redirect;
      }
    }
    if (cookie) headers.set("set-cookie", cookie);
    const attachment = upstream.headers.get("content-disposition");
    if (attachment) {
      headers.set("content-disposition", attachment);
      headers.set("content-type", "application/octet-stream");
    }
    return new NextResponse(
      upstream.status === 204 ? null : await upstream.arrayBuffer(),
      { status: upstream.status, headers },
    );
  } catch {
    return NextResponse.json(
      { detail: "Local API unavailable; restart LifeOS and retry" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
