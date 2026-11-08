import { expect, test } from "@playwright/test";
import { prepareFixtures } from "./helpers";
test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("manual academic workspace, linked tasks, grades, timetable and attributed files", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await page.getByRole("link", { name: "המרחב האקדמי", exact: true }).click();
  await page.locator(".academic-manual-tools > summary").click();
  await page.getByRole("button", { name: "סמסטר חדש", exact: true }).click();
  await page.getByLabel("שם הסמסטר", { exact: true }).fill("סמסטר בדיקה");
  await page.getByLabel("תאריך התחלה", { exact: true }).fill("2026-10-01");
  await page.getByLabel("תאריך סיום", { exact: true }).fill("2027-02-01");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "קורס חדש", exact: true }).click();
  await page
    .getByLabel("שם הקורס", { exact: true })
    .fill("אלגברה לינארית — בדיקה");
  await page.getByLabel("מרצה", { exact: true }).fill("מרצה לדוגמה");
  await page.getByLabel("נקודות זכות", { exact: true }).fill("4");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await page.locator(".section-fold").filter({ has: page.locator(".course-grid") }).locator("summary").first().click();
  await page.getByRole("button", { name: /אלגברה לינארית — בדיקה/ }).click();
  await page.getByRole("button", { name: "מטלה או מבחן", exact: true }).click();
  await page.getByLabel("כותרת", { exact: true }).fill("תרגיל וקטורים");
  await page.getByLabel("מועד", { exact: true }).fill("2026-11-04");
  await page.getByLabel("שעות עבודה משוערות", { exact: true }).fill("3");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByText("תרגיל וקטורים", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /המשימות שלי/ }).click();
  await expect(page.getByText("תרגיל וקטורים", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "השלמה: תרגיל וקטורים" }).click();
  await page.getByRole("link", { name: "המרחב האקדמי", exact: true }).click();
  await page.locator(".section-fold").filter({ has: page.locator(".course-grid") }).locator("summary").first().click();
  await page.getByRole("button", { name: /אלגברה לינארית — בדיקה/ }).click();
  await page.getByLabel("להציג גם פריטים שהושלמו", { exact: true }).check();
  await expect(
    page.getByRole("checkbox", { name: "השלמה: תרגיל וקטורים" }),
  ).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "מטלה או מבחן", exact: true }).click();
  await page.getByLabel("כותרת", { exact: true }).fill("מבחן אמצע");
  await page.getByLabel("סוג", { exact: true }).selectOption("exam");
  await page.getByLabel("מועד", { exact: true }).fill("2026-11-12");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await page.getByRole("tab", { name: "מערכת שעות", exact: true }).click();
  await page.getByRole("button", { name: "מפגש שבועי", exact: true }).click();
  await page.getByLabel("יום בשבוע", { exact: true }).selectOption("0");
  await page.getByLabel("שעת התחלה", { exact: true }).fill("10:00");
  await page.getByLabel("שעת סיום", { exact: true }).fill("12:00");
  await page.getByLabel("מיקום", { exact: true }).fill("חדר בדיקה 101");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByText("חדר בדיקה 101", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "ציונים", exact: true }).click();
  await page.getByRole("button", { name: "ציון חדש", exact: true }).click();
  await page.getByLabel("רכיב הציון", { exact: true }).fill("ציון לדוגמה");
  await page.getByLabel("ציון שהתקבל", { exact: true }).fill("92");
  await page.getByLabel("משקל באחוזים (רשות)", { exact: true }).fill("100");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.locator(".grade-summary strong")).toHaveText("92");
  await page.getByRole("tab", { name: "קבצים", exact: true }).click();
  await page.getByLabel("בחירת קובץ", { exact: true }).setInputFiles({
    name: "סיכום בדיקה.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("מרחב וקטורי ומטריצות — חומר ניסיוני בלבד"),
  });
  await page.route("**/api/academic/documents", route => route.fulfill({
    status: 429, headers: { "Retry-After": "1" }, json: { detail: "fixture extraction busy" },
  }), { times: 1 });
  await page.getByRole("button", { name: "העלאה", exact: true }).click();
  await expect(page.getByText("עיבוד קבצים אחרים עדיין מתבצע. המתינו מעט ונסו להעלות שוב; הקובץ שבחרתם נשאר בטופס.", { exact: true })).toBeVisible();
  expect(await page.getByLabel("בחירת קובץ", { exact: true }).evaluate(input => (input as HTMLInputElement).files?.length)).toBe(1);
  await page.getByRole("button", { name: "העלאה", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "סיכום בדיקה.md", exact: true }),
  ).toBeVisible();
  await page.getByLabel("חיפוש בקבצים", { exact: true }).fill("וקטורי");
  await page.getByRole("button", { name: "חיפוש", exact: true }).click();
  await expect(page.locator(".search-result")).toHaveCount(1);
  await expect(page.locator(".search-result .subtle-badge")).toHaveText("מסמך");
  await page.locator(".search-result").click();
  await expect(
    page
      .getByRole("dialog")
      .getByText("מרחב וקטורי ומטריצות — חומר ניסיוני בלבד", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "סגירה", exact: true }).click();
  await page.getByRole("tab", { name: "מטלות ומבחנים", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/academic-course-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/academic-course-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "כל הקורסים", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/academic-overview-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("link", { name: "היומן שלי", exact: true }).click();
  await page.getByRole("button", { name: "חודש", exact: true }).click();
  await expect(
    page
      .locator(".calendar-chip")
      .filter({ hasText: "מבחן אמצע" })
      .first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await page.getByLabel("מראה", { exact: true }).selectOption("light");
  await page.getByRole("button", { name: "שמירת הגדרות", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("link", { name: "המרחב האקדמי", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/academic-overview-light.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
