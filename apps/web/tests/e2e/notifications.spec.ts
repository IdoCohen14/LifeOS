import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures } from "./helpers";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("notification snooze, dismiss and restore persist without changing the task", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const headers = { Origin: BASE, "X-CSRF-Token": session.csrf };
  await page.request.put("/api/notifications/preferences", {
    headers,
    data: { quiet_enabled: false },
  });
  const task = await (
    await page.request.post("/api/tasks", {
      headers,
      data: { title: "Snooze browser fixture", due: "2020-01-01" },
    })
  ).json();
  await page.goto("/");
  await page
    .getByRole("button", { name: "מרכז התראות: 1 לא נקראו", exact: true })
    .click();
  let dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await dialog.getByText("פעולות נוספות", { exact: true }).click();
  await dialog
    .getByRole("button", { name: "דחיית ההתראה", exact: true })
    .click();
  await expect(dialog.getByText("אין התראות בקטגוריות שבחרת")).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "פעילות", exact: true }),
  ).toBeFocused();
  await dialog
    .getByRole("button", { name: "מוסתרות (1)", exact: true })
    .click();
  await expect(dialog.getByText(/נדחתה עד/)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await page.getByRole("button", { name: "מרכז התראות", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await dialog
    .getByRole("button", { name: "מוסתרות (1)", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "החזרת ההתראה", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "מוסתרות (0)", exact: true }),
  ).toBeFocused();
  await dialog.getByRole("button", { name: "פעילות", exact: true }).click();
  await dialog.getByText("פעולות נוספות", { exact: true }).click();
  await dialog
    .getByRole("button", { name: "הסתרת ההתראה", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "מוסתרות (1)", exact: true })
    .click();
  await expect(
    dialog.getByText("ההתראה הוסתרה", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 320, height: 740 });
  expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: "../../.runtime/screenshots/notifications-hidden-mobile.png",
  });
  expect(await (await page.request.get("/api/tasks")).json()).toEqual([task]);
});

test("notification center persists explicit read state, respects preferences and opens existing controls", async ({
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
      await page.request.put("/api/notifications/preferences", {
        headers,
        data: { quiet_enabled: false },
      })
    ).ok(),
  ).toBe(true);
  expect(
    (
      await page.request.post("/api/tasks", {
        headers,
        data: { title: "Notification browser fixture", due: "2020-01-01" },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/");
  const bell = page.getByRole("button", {
    name: "מרכז התראות: 1 לא נקראו",
    exact: true,
  });
  await bell.focus();
  await page.keyboard.press("Enter");
  let dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await expect(
    dialog.getByText("Notification browser fixture", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "סימון המוצגות כנקראו", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(bell).toBeFocused();
  await bell.click();
  await dialog
    .getByRole("button", { name: "סימון המוצגות כנקראו", exact: true })
    .click();
  await expect(
    dialog.getByText("מועד שעבר · נקראה", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.reload();
  await page.getByRole("button", { name: "מרכז התראות", exact: true }).click();
  await expect(
    dialog.getByText("מועד שעבר · נקראה", { exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "פתיחת הפריט", exact: true })
    .click();
  await expect(page.getByLabel("כותרת", { exact: true })).toHaveValue(
    "Notification browser fixture",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "מרכז התראות", exact: true }).click();
  await dialog.getByText("העדפות התראות", { exact: true }).click();
  await dialog.getByLabel("שעות שקטות", { exact: true }).check();
  await dialog.getByLabel("תחילת שעות שקטות", { exact: true }).fill("00:00");
  await dialog.getByLabel("סיום שעות שקטות", { exact: true }).fill("00:00");
  await dialog
    .getByRole("button", { name: "שמירת העדפות", exact: true })
    .click();
  await expect(dialog.getByText(/שעות שקטות פעילות/)).toBeVisible();
  await page.setViewportSize({ width: 320, height: 740 });
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(
    true,
  );
  expect(
    await dialog
      .locator(".notification-check")
      .first()
      .evaluate((e) => getComputedStyle(e).flexDirection),
  ).toBe("row");
  await dialog.evaluate((e) => e.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/notifications-he-mobile.png",
    fullPage: false,
  });
  await dialog.getByLabel("התראות בתוך האפליקציה", { exact: true }).uncheck();
  await dialog
    .getByRole("button", { name: "שמירת העדפות", exact: true })
    .click();
  await expect(dialog.getByText(/התראות בתוך האפליקציה כבויות/)).toBeVisible();
  await page.keyboard.press("Escape");
  expect(
    (
      await page.request.put("/api/settings", {
        headers,
        data: { language: "en", theme: "light" },
      })
    ).ok(),
  ).toBe(true);
  await page.reload();
  await page
    .getByRole("button", { name: "Notifications · Quiet hours", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "Notifications", exact: true });
  await expect(dialog.getByText(/In-app notifications are off/)).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});
