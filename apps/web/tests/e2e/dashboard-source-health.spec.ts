import { expect, test } from "@playwright/test";
import { prepareFixtures } from "./helpers";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("cached dashboard data has a visible stale notice without expanding connection details", async ({ page }) => {
  let stale = false;
  await page.route("**/api/integrations/braude/status", route => route.fulfill({ json: {
    configured: true, connected: !stale, stale, error: stale ? "fixture_connection_error" : null,
    last_success: Date.now() / 1000 - (stale ? 86400 : 0), revision: 1,
  } }));
  await page.route("**/api/integrations/braude/events", route => route.fulfill({ json: [{
    id: "cached-source-fixture", title: "Cached class fixture", notes: "הרצאה\nחדר: L709",
    source: "braude", all_day: false, start: new Date(Date.now() - 30000).toISOString(),
    end: new Date(Date.now() + 1800000).toISOString(), created_at: new Date().toISOString(),
  }] }));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator(".day-focus").getByText("Cached class fixture", { exact: true })).toBeVisible();
  await expect(page.locator(".dashboard-source-notice")).toHaveCount(0);
  stale = true;
  await page.reload();
  await expect(page.locator(".day-focus").getByText("Cached class fixture", { exact: true })).toBeVisible();
  await expect(page.locator(".dashboard-source-notice")).toBeVisible();
  await expect(page.locator(".dashboard-more")).not.toHaveAttribute("open", "");
  await page.locator(".dashboard-source-notice").getByRole("button", { name: "בדיקת חיבורים", exact: true }).click();
  await expect(page).toHaveURL(/view=settings/);
});
