import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures, openDashboardTool } from "./helpers";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("daily and seven-day briefing uses records, opens exact dates and task editor", async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date("2026-10-26T10:00:00Z"));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const headers = { Origin: BASE, "X-CSRF-Token": session.csrf };
  for (const data of [
    { title: "Briefing today fixture", due: "2026-10-26" },
    { title: "Briefing future fixture", due: "2026-10-28" },
    { title: "Briefing late fixture", due: "2026-10-25" },
    { title: "Briefing undated fixture" },
  ])
    expect(
      (await page.request.post("/api/tasks", { headers, data })).ok(),
    ).toBe(true);
  for (const data of [
    {
      title: "Ongoing fixture",
      start: "2026-10-26T09:00:00Z",
      end: "2026-10-26T11:00:00Z",
      all_day: false,
    },
    {
      title: "Overlap fixture",
      start: "2026-10-26T10:00:00Z",
      end: "2026-10-26T12:00:00Z",
      all_day: false,
    },
    {
      title: "Tomorrow all-day fixture",
      start: "2026-10-27",
      end: "2026-10-28",
      all_day: true,
    },
  ])
    expect(
      (await page.request.post("/api/events", { headers, data })).ok(),
    ).toBe(true);
  await page.goto("/");
  await openDashboardTool(page, "מבט יומי ושבועי");
  const brief = page.getByRole("region", {
    name: /מבט על היום שלך|השבוע הקרוב שלך/,
  });
  await expect(brief.locator(".planning-facts dd")).toHaveText([
    "2",
    "1",
    "1",
    "3:00",
  ]);
  await expect(brief.getByText("מתקיים עכשיו")).toBeVisible();
  await expect(
    brief.getByRole("button", { name: /Ongoing fixture/ }),
  ).toBeVisible();
  await brief.getByRole("button", { name: /Briefing today fixture/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByLabel("כותרת", { exact: true })).toHaveValue(
    "Briefing today fixture",
  );
  await page.keyboard.press("Escape");
  await brief.getByRole("button", { name: "7 ימים", exact: true }).click();
  await expect(brief.locator(".planning-facts dd")).toHaveText([
    "3",
    "2",
    "1",
    "3:00",
  ]);
  await expect(brief.locator(".planning-days button")).toHaveCount(7);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../../.runtime/screenshots/planning-week-he-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ forcedColors: "active" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const selected = brief.getByRole("button", { name: "7 ימים", exact: true });
  await expect(selected).toHaveAttribute("aria-pressed", "true");
  expect(
    await selected.evaluate((e) =>
      parseFloat(getComputedStyle(e).borderTopWidth),
    ),
  ).toBeGreaterThanOrEqual(2);
  await brief.locator(".planning-days button").nth(2).click();
  await expect(page).toHaveURL(/view=calendar&day=2026-10-28/);
  await expect(page.locator('.day-number[aria-pressed="true"]')).toHaveText(
    "28",
  );
  await expect(page.locator('[aria-current="date"]')).toHaveText("26");
});

test("empty English light briefing warns about stale imported sources without invoking inference", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  expect(
    (
      await page.request.put("/api/settings", {
        headers: { Origin: BASE, "X-CSRF-Token": session.csrf },
        data: { language: "en", theme: "light" },
      })
    ).ok(),
  ).toBe(true);
  await page.route("**/api/integrations/google/status", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: {
        ...(await response.json()),
        connected: false,
        last_success: 1,
        stale: true,
        error: "expired",
      },
    });
  });
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await page.goto("/");
  await openDashboardTool(page, "Day and week overview");
  const brief = page.getByRole("region", {
    name: /Your day at a glance|Your next seven days/,
  });
  await expect(brief.locator(".planning-facts dd")).toHaveText([
    "0",
    "0",
    "0",
    "0:00",
  ]);
  await expect(brief.getByRole("status")).toContainText("cached");
  await brief.getByRole("button", { name: "7 days", exact: true }).click();
  await expect(brief.locator(".planning-days button")).toHaveCount(7);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.screenshot({
    path: "../../.runtime/screenshots/planning-week-en-light.png",
    fullPage: true,
  });
  expect(writes).toEqual([]);
});
