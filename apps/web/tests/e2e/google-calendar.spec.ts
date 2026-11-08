import { test, expect } from "@playwright/test";
import { prepareFixtures, BASE, openConnection } from "./helpers";
test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test("Google-only configuration stays disconnected until real consent", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await openConnection(page, "Google Calendar");
  await expect(
    page.getByRole("heading", { name: "Google Calendar", exact: true }),
  ).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await expect(page.getByText("הגדרה ראשונה ב־Google", { exact: true })).toHaveCount(0);
  const session = await page.request.get("/api/session");
  const { csrf } = await session.json();
  const configured = await page.request.post("/api/integrations/google/config", {
    headers: { "X-CSRF-Token": csrf, Origin: BASE },
    data: { client_id: "fixture.apps.googleusercontent.com", client_secret: "fixture-secret-never-real" },
  });
  expect(configured.status()).toBe(200);
  await page.reload();
  await openConnection(page, "Google Calendar");
  await expect(page.getByRole("button", { name: "חיבור Google Calendar", exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "סנכרון עכשיו", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("fixture-secret-never-real", { exact: true }),
  ).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/google-calendar-settings.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/google-calendar-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const callback = await request.get(
    "/api/integrations/google/callback?state=forged&code=bad",
    { headers: { "Sec-Fetch-Site": "cross-site" } },
  );
  expect(callback.status()).toBe(400);
  const bad = await request.post("/api/integrations/google/sync", {
    headers: { Origin: "https://evil.example" },
  });
  expect(bad.status()).toBe(403);
  expect(BASE.startsWith("http://127.0.0.1:")).toBe(true);
  expect(errors).toEqual([]);
  await page.route("**/api/integrations/google/status", route => route.fulfill({
    json: { configured: true, connected: true, state: "error", error: "calendar_cache_limit_exceeded",
      syncing: false, stale: true, calendars: [], last_success: null, next_sync: null,
      window_days: { past: 30, future: 365 } },
  }));
  await page.reload();
  await openConnection(page, "Google Calendar");
  await expect(page.getByText("הסנכרון נעצר בגלל כמות המידע. אפשר לבחור פחות לוחות שנה ולנסות שוב. המידע השמור נשאר ללא שינוי.", { exact: true })).toBeVisible();
});
