import { test, expect } from "@playwright/test";
import { prepareFixtures } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("keyboard navigation identifies content and keeps focus visible and contained", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  const main = page.getByRole("main");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "דילוג לתוכן" }).focus();
  await page.keyboard.press("Enter");
  await expect(main).toBeFocused();
  const calendar = page.getByRole("link", { name: "היומן שלי", exact: true });
  await calendar.focus();
  await page.keyboard.press("Enter");
  await expect(main).toHaveAccessibleName("היומן שלי");
  await expect(main).toBeFocused();
  const region = page.getByRole("region", { name: "יומן — ניתן לגלול לרוחב" });
  await region.focus();
  await expect(region).toBeFocused();
  expect(await region.evaluate(element => getComputedStyle(element).outlineStyle)).toBe("solid");

  const add = page.getByRole("button", { name: "אירוע חדש", exact: true }).first();
  await add.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 18; index++) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  for (let index = 0; index < 18; index++) {
    await page.keyboard.press("Shift+Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(add).toBeFocused();
  const settings = page.getByRole("link", { name: "הגדרות", exact: true });
  await settings.focus();
  await page.keyboard.press("Enter");
  await expect(settings).toHaveAttribute("aria-current", "page");
  await expect(main).toHaveAccessibleName("הגדרות");
  await expect(main).toBeFocused();
  const displayName = page.getByLabel("איך לקרוא לך?", { exact: true });
  await displayName.focus();
  const refreshed = page.waitForResponse(response => response.url().endsWith("/api/tasks") && response.ok());
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await refreshed;
  await expect(displayName).toBeFocused();
  await page.setViewportSize({ width: 320, height: 740 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../.runtime/screenshots/accessibility-mobile.png", fullPage: true });
  await page.getByLabel("שפה", { exact: true }).selectOption("en");
  await page.getByLabel("מראה", { exact: true }).selectOption("light");
  await page.getByRole("button", { name: "שמירת הגדרות" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(main).toHaveAccessibleName("Settings");
  await page.getByRole("link", { name: "Calendar", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(main).toBeFocused();
  await expect(main).toHaveAccessibleName("My calendar");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const englishRegion = page.getByRole("region", { name: "Calendar — scroll horizontally" });
  await englishRegion.focus();
  expect(await englishRegion.evaluate(element => getComputedStyle(element).outlineStyle)).toBe("solid");
  await page.screenshot({ path: "../../.runtime/screenshots/accessibility-calendar-en.png", fullPage: true });
});
