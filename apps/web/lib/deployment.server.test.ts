// @vitest-environment node
import { expect, it } from "vitest";
import { deploymentConfig } from "./deployment.server";

it("keeps local defaults and canonicalizes the configured HTTPS origin", () => {
  expect(deploymentConfig({}).origin).toBe("http://127.0.0.1:3000");
  expect(deploymentConfig({ LIFEOS_DEPLOYMENT_MODE: "server", LIFEOS_PUBLIC_ORIGIN: "https://LifeOS.Example:443/" })).toMatchObject({ origin: "https://lifeos.example", accountMode: true, server: true });
});

it.each(["", "http://lifeos.example", "https://localhost", "https://127.0.0.1", "https://user:secret@lifeos.example", "https://lifeos.example/path", "https://lifeos.example?x=1", "https://lifeos.example#x", "https://lifeos..example", "https://lifeos.local", "https://lifeos.example:0"])("rejects invalid public origin %s", origin => {
  expect(() => deploymentConfig({ LIFEOS_DEPLOYMENT_MODE: "server", LIFEOS_PUBLIC_ORIGIN: origin })).toThrow();
});

it("requires explicit server mode for a public origin", () => {
  expect(() => deploymentConfig({ LIFEOS_PUBLIC_ORIGIN: "https://lifeos.example" })).toThrow();
});
