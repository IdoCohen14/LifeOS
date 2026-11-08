import { test, expect } from "@playwright/test";
import { openSettingsSection } from "./helpers";

test("transferred legacy session opens the account workspace and explicit OAuth upgrades cookie", async ({ browser }) => {
  test.skip(process.env.LIFEOS_TRANSITION_E2E !== "1", "Requires migrated .runtime fixture");
  const base = process.env.LIFEOS_TEST_BASE_URL;
  if (!base || new URL(base).hostname !== "127.0.0.1" || new URL(base).port === "3000") throw new Error("Isolated fixture server required");
  const context = await browser.newContext({ baseURL: base });
  try {
    expect(await (await context.request.get("/api/mode")).json()).toMatchObject({ account_mode: true, test_mode: true });
    await context.addCookies([{ name: "lifeos_session", value: "transition-fixture-token", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Strict" }]);
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("היום שלי");
    await expect(page.getByText("Private title", { exact: true })).toBeVisible();
    const session = await (await context.request.get("/api/session")).json();
    expect(session.login).toBe("demo-owner");
    const authorized = await context.request.post("/api/integrations/google/authorize", { headers: { Origin: base, "X-CSRF-Token": session.csrf } });
    expect(authorized.status()).toBe(200);
    expect((await authorized.json()).authorization_url).toContain("accounts.google.com");
    expect((await context.cookies(base)).find(cookie => cookie.name === "lifeos_session")?.sameSite).toBe("Lax");
    await page.getByRole("link", { name: "הגדרות", exact: true }).click();
    await openSettingsSection(page, "גיבוי ושחזור");
    await expect(page.getByRole("heading", { name: "גיבוי החשבון", exact: true })).toBeVisible();
    await openSettingsSection(page, "כניסה ואבטחה");
    await expect(page.getByRole("heading", { name: "סיסמת החשבון", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  } finally { await context.close(); }
});
