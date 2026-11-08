// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";
import { unstable_doesMiddlewareMatch as unstable_doesProxyMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";

vi.mock("./lib/csp-manifest.mjs", () => ({
  buildDirectory: vi.fn(() => "/fixture-build"),
  verifyManifest: vi.fn(() => ({ hashes: ["'sha256-fixture'"] })),
  scriptPolicy: vi.fn(() => "script-src 'self' 'sha256-fixture'"),
}));
afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); vi.clearAllMocks(); });

it("sets validated production CSP without making the page dynamic", async () => {
  vi.stubEnv("NODE_ENV", "production");
  const { proxy } = await import("./proxy");
  const result=proxy(new NextRequest("https://fixture.test/"));
  expect(result.headers.get("content-security-policy")).toBe("script-src 'self' 'sha256-fixture'; style-src-attr 'none'");
  expect(result.headers.get("x-middleware-next")).toBe("1");
});

it("fails closed if a direct Next start bypassed manifest preflight", async () => {
  vi.stubEnv("NODE_ENV", "production");
  const { verifyManifest } = await import("./lib/csp-manifest.mjs");
  vi.mocked(verifyManifest).mockImplementationOnce(() => { throw Error("fixture missing"); });
  const { proxy } = await import("./proxy");
  const result=proxy(new NextRequest("https://fixture.test/"));
  expect(result.status).toBe(503);
  expect(result.headers.get("cache-control")).toBe("no-store");
  expect(result.headers.get("content-type")).toContain("text/plain");
});

it("leaves development's live compilation policy in place", async () => {
  vi.stubEnv("NODE_ENV", "development");
  const { proxy } = await import("./proxy");
  const { verifyManifest } = await import("./lib/csp-manifest.mjs");
  expect(proxy(new NextRequest("https://fixture.test/")).headers.get("content-security-policy")).toBeNull();
  expect(verifyManifest).not.toHaveBeenCalled();
});

it("restricts only the root document including query views without changing the cached base policy", async () => {
  vi.stubEnv("NODE_ENV", "production");
  const { proxy } = await import("./proxy");
  for(const path of ["/?view=timetable", "/?view=academic"])
    expect(proxy(new NextRequest(`https://fixture.test${path}`)).headers.get("content-security-policy")).toContain("style-src-attr 'none'");
  for(const path of ["/missing", "/500", "/icon-missing-page"])
    expect(proxy(new NextRequest(`https://fixture.test${path}`)).headers.get("content-security-policy")).toBe("script-src 'self' 'sha256-fixture'");
});

it("covers HTML routes but excludes API, assets, offline and Push worker", async () => {
  const { config } = await import("./proxy");
  for (const path of ["/", "/missing", "/500", "/icon-missing-page"])
    expect(unstable_doesProxyMatch({config,nextConfig:{},url:`https://fixture.test${path}`})).toBe(true);
  for (const path of ["/api/session", "/_next/static/fixture.js", "/sw.js", "/offline.html", "/manifest.webmanifest", "/icon-192.png"])
    expect(unstable_doesProxyMatch({config,nextConfig:{},url:`https://fixture.test${path}`})).toBe(false);
});
