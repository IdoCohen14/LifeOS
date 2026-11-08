import { test, expect } from "@playwright/test";
import { prepareFixtures, openConnection } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test("Braude subscription hides secrets and projects read-only calendar events", async ({ page }) => {
  // Keep this fixed-date calendar fixture on its own local day.
  await page.clock.setFixedTime(new Date("2026-10-26T08:00:00Z"));
  let configured = false;
  let connected = false;
  const privateUrl = "https://moodle27.braude.ac.il/calendar/export_execute.php?userid=fixture&authtoken=private-fixture";
  await page.route("**/api/integrations/moodle/status", route => route.fulfill({ json: {
    configured, connected, state: connected ? "connected" : configured ? "configured" : "disconnected",
    error: null, syncing: false, stale: false, last_success: connected ? 1792994400 : null,
  } }));
  await page.route("**/api/integrations/moodle/config", route => {
    expect(route.request().postDataJSON().url).toBe(privateUrl);
    configured = true;
    return route.fulfill({ json: { configured: true } });
  });
  await page.route("**/api/integrations/moodle/sync?background=true", route => {
    connected = true;
    return route.fulfill({ status: 202, json: { queued: true } });
  });
  await page.route("**/api/integrations/moodle/events", route => route.fulfill({ json: connected ? [{
    id: "moodle-fixture", title: "Moodle fixture deadline", notes: "Test only", source: "moodle",
    source_url: "https://moodle27.braude.ac.il/mod/assign/view.php?id=123", all_day: false,
    start: "2026-10-26T10:00:00Z", end: "2026-10-26T10:01:00Z", created_at: "2026-10-26T00:00:00Z",
  }] : [] }));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await openConnection(page, "Moodle");
  const input = page.getByLabel("קישור מנוי ליומן Moodle", { exact: true });
  await expect(input).toHaveAttribute("type", "password");
  await input.fill(privateUrl);
  await page.getByRole("button", { name: "חיבור Moodle", exact: true }).click();
  await expect(input).toHaveCount(0);
  await expect(page.getByRole("button", { name: "סנכרון Moodle עכשיו", exact: true })).toBeVisible();
  await expect(page.getByText("private-fixture", { exact: false })).toHaveCount(0);
  const disconnect = page.getByRole("button", { name: "ניתוק Moodle", exact: true });
  await disconnect.click();
  await page.getByRole("dialog").getByRole("button", { name: "סגירה", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(disconnect).toBeFocused();
  await page.screenshot({ path: "../../.runtime/screenshots/moodle-settings.png", fullPage: true });
  await page.goto("/");
  await page.locator(".compact-agenda > summary").click();
  await expect(page.getByRole("listitem").getByText("Moodle fixture deadline", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "עריכה: Moodle fixture deadline", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "מחיקה: Moodle fixture deadline", exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../.runtime/screenshots/moodle-dashboard-mobile.png", fullPage: true });
});
