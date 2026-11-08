import { test, expect } from "@playwright/test";
import { prepareFixtures, BASE, openDashboardTool } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test("recommendations navigate and hide persistently without editing tasks", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.getByRole("link", { name: "הגדרות", exact: true })).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const response = await page.request.post("/api/tasks", {
    headers: { Origin: BASE, "X-CSRF-Token": session.csrf },
    data: { title: "Recommendation fixture", due: "2020-01-01", priority: "high" },
  });
  const task = await response.json();
  await page.reload();
  await openDashboardTool(page, "דברים שכדאי לשים לב אליהם");
  const panel = page.getByRole("region", { name: "לתשומת לבך", exact: true });
  await expect(panel.getByText("Recommendation fixture", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.screenshot({ path: "../../.runtime/screenshots/recommendations-active-mobile.png" });
  await panel.getByRole("button", { name: "פתיחת המשימות", exact: true }).click();
  await expect(page).toHaveURL(/view=tasks/);
  await page.goto("/");
  await openDashboardTool(page, "דברים שכדאי לשים לב אליהם");
  await panel.getByRole("button", { name: "הסתר ל־24 שעות: Recommendation fixture", exact: true }).click();
  await expect(panel.getByText("אין המלצות דחופות כרגע", { exact: true })).toBeVisible();
  await page.reload();
  await openDashboardTool(page, "דברים שכדאי לשים לב אליהם");
  await expect(panel.getByText("אין המלצות דחופות כרגע", { exact: true })).toBeVisible();
  const tasks = await (await page.request.get("/api/tasks")).json();
  expect(tasks.find((item: { id: string }) => item.id === task.id).completed).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await panel.screenshot({ path: "../../.runtime/screenshots/recommendations-mobile.png" });
});
