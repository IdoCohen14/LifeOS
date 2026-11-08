import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("scheduled planning prepares due snapshots once and opens the live weekly view", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const headers = { Origin: BASE, "X-CSRF-Token": session.csrf };
  expect(
    (
      await page.request.post("/api/tasks", {
        headers,
        data: { title: "Scheduled source fixture", due: "2020-01-01" },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/?notifications=open");
  let dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await dialog.getByText("סיכומים מתוזמנים", { exact: true }).click();
  await dialog.getByLabel("סיכום יומי מתוזמן", { exact: true }).check();
  await dialog.getByLabel("שעת הסיכום היומי", { exact: true }).fill("00:00");
  await dialog.getByLabel("סיכום שבועי מתוזמן", { exact: true }).check();
  // Midnight is a valid Jerusalem schedule; choose today for an immediately due weekly period.
  const weekday = await page.evaluate(() => {
    const day = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Jerusalem",
      weekday: "short",
    }).format(new Date());
    return (
      { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 } as Record<
        string,
        number
      >
    )[day];
  });
  await dialog
    .getByLabel("יום הסיכום השבועי", { exact: true })
    .selectOption(String(weekday));
  await dialog.getByLabel("שעת הסיכום השבועי", { exact: true }).fill("00:00");
  await dialog
    .getByRole("button", { name: "שמירת תזמון", exact: true })
    .click();
  await expect(dialog.getByText("התזמון נשמר.", { exact: true })).toBeVisible();
  await dialog
    .getByRole("button", { name: "עדכון סיכומים כעת", exact: true })
    .click();
  await expect(
    dialog.getByText("הסיכום היומי שלך מוכן", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByText("הסיכום השבועי שלך מוכן", { exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "עדכון סיכומים כעת", exact: true })
    .click();
  await expect(
    dialog.getByText("אין כרגע סיכומים נוספים שמועדם הגיע.", { exact: true }),
  ).toBeVisible();
  const weekly = dialog
    .locator(".notification-list li")
    .filter({ hasText: "הסיכום השבועי שלך מוכן" });
  await expect(weekly.locator(".notification-snapshot")).toContainText(
    "Asia/Jerusalem",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await weekly.screenshot({
    path: "../../.runtime/screenshots/scheduled-weekly-card.png",
  });
  expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(
    true,
  );
  await weekly
    .getByRole("button", { name: "פתיחת הפריט", exact: true })
    .click();
  await expect(page).toHaveURL(/briefing=week/);
  await expect(
    page.getByRole("heading", { name: "השבוע הקרוב שלך", exact: true }),
  ).toBeVisible();
  await page.goto("/?notifications=open");
  dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await dialog.getByText("העדפות התראות", { exact: true }).click();
  await dialog.getByLabel("התראות סיכום מתוזמן", { exact: true }).uncheck();
  await dialog
    .getByRole("button", { name: "שמירת העדפות", exact: true })
    .click();
  await expect(
    dialog.getByText("הסיכום השבועי שלך מוכן", { exact: true }),
  ).toHaveCount(0);
  expect(
    (
      await page.request.put("/api/settings", {
        headers,
        data: { language: "en", theme: "light" },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/?notifications=open");
  await page.getByText("Scheduled briefings", { exact: true }).click();
  await expect(
    page.getByLabel("Scheduled daily briefing", { exact: true }),
  ).toBeChecked();
});
