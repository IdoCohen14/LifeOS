import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures, openDashboardTool } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("weekly review reports recorded status changes, missing past data and current task navigation", async ({
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
        data: { title: "Complete review fixture", completed: true },
      })
    ).ok(),
  ).toBe(true);
  const reopened = await (
    await page.request.post("/api/tasks", {
      headers,
      data: { title: "Reopened review fixture", completed: true },
    })
  ).json();
  expect(
    (
      await page.request.put(`/api/tasks/${reopened.id}`, {
        headers,
        data: { title: reopened.title, completed: false },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/");
  await openDashboardTool(page, "איך עבר השבוע");
  const review = page.getByRole("region", {
    name: "סיכום ביצוע שבועי",
    exact: true,
  });
  await review
    .getByRole("button", { name: "הצגת הסיכום", exact: true })
    .click();
  await expect(review.locator(".planning-facts dd")).toHaveText([
    "2",
    "1",
    "1",
    "0",
  ]);
  await expect(review.locator(".review-days li")).toHaveCount(7);
  await expect(review.getByText(/המעקב החל/)).toBeVisible();
  await page.setViewportSize({ width: 320, height: 740 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await review.screenshot({
    path: "../../.runtime/screenshots/weekly-review-he-mobile.png",
  });
  await review
    .getByRole("button", { name: "7 ימים קודמים", exact: true })
    .click();
  await expect(review.locator(".planning-facts dd")).toHaveText([
    "0",
    "0",
    "1",
    "0",
  ]);
  await expect(review.getByText("אין נתוני מעקב", { exact: true })).toHaveCount(
    7,
  );
  await review
    .getByRole("button", { name: "עדכון להיום", exact: true })
    .click();
  await expect(review.locator(".planning-facts dd")).toHaveText([
    "2",
    "1",
    "1",
    "0",
  ]);
  await review
    .locator(".review-recent button")
    .filter({ hasText: reopened.title })
    .click();
  await expect(
    page.getByRole("dialog").getByLabel("כותרת", { exact: true }),
  ).toHaveValue(reopened.title);
  await page.keyboard.press("Escape");
  expect(
    (
      await page.request.put("/api/settings", {
        headers,
        data: { language: "en", theme: "light" },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/");
  await openDashboardTool(page, "Weekly review");
  await page.getByRole("button", { name: "Show review", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Weekly review", exact: true })
      .getByText(/Tracking began/),
  ).toBeVisible();
});
