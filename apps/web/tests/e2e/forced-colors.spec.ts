import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("forced colors keeps selected controls and keyboard state distinguishable", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  expect((await page.request.post("/api/tasks", {
    headers: { Origin: BASE, "X-CSRF-Token": session.csrf },
    data: { title: "Forced colors fixture", completed: true },
  })).ok()).toBe(true);
  await page.goto("/?view=tasks");
  const completed = page.getByRole("button", { name: "הושלמו", exact: true });
  await completed.focus();
  await page.keyboard.press("Space");
  await expect(completed).toHaveAttribute("aria-pressed", "true");
  expect(await completed.evaluate(e => parseFloat(getComputedStyle(e).borderTopWidth))).toBeGreaterThanOrEqual(2);
  expect(await completed.evaluate(e => Number(getComputedStyle(e).fontWeight))).toBeGreaterThanOrEqual(600);
  const check = page.getByRole("checkbox", { name: "פתיחה מחדש: Forced colors fixture" });
  await expect(check).toHaveAttribute("aria-checked", "true");
  await expect(check.locator("svg")).toBeVisible();
  expect(await check.evaluate(e => getComputedStyle(e).color !== getComputedStyle(e).backgroundColor)).toBe(true);
  await page.screenshot({ path: "../../.runtime/screenshots/forced-colors-mobile.png", fullPage: true });
  await page.getByRole("link", { name: "יומן", exact: true }).click();
  const today = page.locator(".today-number");
  await expect(today).toHaveAttribute("aria-current", "date");
  const label = await page.locator('.day-number[aria-pressed="false"]').first().getAttribute("aria-label");
  const date = page.getByRole("button", { name: label!, exact: true });
  await date.focus();
  await page.keyboard.press("Space");
  await expect(date).toHaveAttribute("aria-pressed", "true");
  expect(await today.evaluate(e => getComputedStyle(e).borderTopStyle)).toBe("dashed");
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  const settings = page.getByRole("link", { name: "הגדרות", exact: true });
  await expect(settings).toHaveAttribute("aria-current", "page");
  expect(await settings.evaluate(e => parseFloat(getComputedStyle(e).borderBottomWidth))).toBeGreaterThanOrEqual(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
