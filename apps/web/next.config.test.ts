import { afterEach, describe, expect, it, vi } from "vitest";
import config from "./next.config";

afterEach(() => vi.unstubAllEnvs());

describe("content security policy boundaries", () => {
  it.each(["production", "development"])("blocks attribute scripts and embedded objects in %s", async (mode) => {
    vi.stubEnv("NODE_ENV", mode);
    const routes = await config.headers!();
    const headers = routes.find((route) => route.source === "/:path*")!.headers;
    const policy = headers.find((header) => header.key === "Content-Security-Policy")!.value;
    const directives = new Map(policy.split(";").map((directive) => {
      const [name, ...values] = directive.trim().split(/\s+/);
      return [name, values.join(" ")];
    }));
    expect(directives.get("script-src-attr")).toBe("'none'");
    expect(directives.get("object-src")).toBe("'none'");
    expect(directives.get("frame-ancestors")).toBe("'none'");
    expect(directives.get("form-action")).toBe("'self'");
    expect(directives.get("script-src")).toContain("'unsafe-inline'");
    expect(directives.get("script-src")!.includes("'unsafe-eval'")).toBe(mode === "development");
    expect(directives.get("connect-src")!.includes("ws://")).toBe(mode === "development");
  });
});
