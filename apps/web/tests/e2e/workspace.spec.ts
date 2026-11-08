import { test, expect } from "@playwright/test";
import { prepareFixtures } from "./helpers";
const BASE = process.env.LIFEOS_TEST_BASE_URL || "http://127.0.0.1:3000";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));

test("Hebrew RTL, task/calendar CRUD, settings and mobile layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "היום שלי",
  );
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-empty-dark.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "משימה חדשה", exact: true }).click();
  await page
    .getByLabel("כותרת", { exact: true })
    .fill("בדיקת משימה — מידע ניסיוני בלבד");
  await page.getByRole("dialog").locator(".form-extra > summary").filter({hasText:"עדיפות ושעה מדויקת"}).click();
  await page.getByLabel("עדיפות", { exact: true }).selectOption("high");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(
    page.getByText("בדיקת משימה — מידע ניסיוני בלבד", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("בדיקת משימה — מידע ניסיוני בלבד", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("checkbox", { name: "השלמה: בדיקת משימה — מידע ניסיוני בלבד" })
    .click();
  await expect(
    page.getByText("אין משימות נוספות פתוחות כרגע.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "המשימות שלי" }).click();
  await page.getByRole("button", { name: "הושלמו", exact: true }).click();
  await page.getByLabel("אפשרויות: בדיקת משימה — מידע ניסיוני בלבד", {exact:true}).click();
  await page
    .getByRole("button", { name: "עריכה: בדיקת משימה — מידע ניסיוני בלבד" })
    .click();
  await page.getByLabel("כותרת", { exact: true }).fill("משימה ערוכה");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByText("משימה ערוכה", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "פתיחה מחדש: משימה ערוכה" }).click();
  await page.getByRole("link", { name: "היומן שלי", exact: true }).click();
  await page
    .getByRole("button", { name: "אירוע חדש", exact: true })
    .first()
    .click();
  await page.getByLabel("כותרת", { exact: true }).fill("מפגש בדיקה");
  await page.getByLabel("כל היום", { exact: true }).check();
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "יום", exact: true }).click();
  await expect(page.getByText("מפגש בדיקה", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "עריכה: מפגש בדיקה" }).click();
  await page.getByLabel("כותרת", { exact: true }).fill("מפגש בדיקה ערוך");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(
    page.getByText("מפגש בדיקה ערוך", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "שבוע", exact: true }).click();
  await expect(page.locator(".week-grid")).toBeVisible();
  await page.getByRole("button", { name: "חודש", exact: true }).click();
  await expect(page.locator(".calendar-cell")).toHaveCount(42);
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await page.getByLabel("איך לקרוא לך?").fill("חשבון בדיקה");
  await page.getByLabel("מראה", { exact: true }).selectOption("light");
  await page.getByRole("button", { name: "שמירת הגדרות" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("link", { name: "היום שלי", exact: true }).click();
  await expect(page.getByText("משימה ערוכה", { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-light.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-mobile-light.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "יומן", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/calendar-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await page.getByLabel("מראה", { exact: true }).selectOption("dark");
  await page.getByRole("button", { name: "שמירת הגדרות" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "היום", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-mobile-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-dark.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await page.getByLabel("שפה", { exact: true }).selectOption("en");
  await page.getByRole("button", { name: "שמירת הגדרות" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.getByRole("link", { name: "My day", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "My day",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../.runtime/screenshots/dashboard-english.png",
    fullPage: true,
  });
  await page.getByLabel("Options: משימה ערוכה", {exact:true}).click();
  await page.getByRole("button", { name: "Delete: משימה ערוכה" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByText("משימה ערוכה", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "My calendar", exact: true }).click();
  await page.getByRole("button", { name: "Day", exact: true }).click();
  await page.getByRole("button", { name: "Delete: מפגש בדיקה ערוך" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByText("מפגש בדיקה ערוך", { exact: true })).toHaveCount(
    0,
  );
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Language", { exact: true }).selectOption("he");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  expect(errors).toEqual([]);
});

test("rejects cross-origin login and private unauthenticated reads", async ({
  request,
}) => {
  const read = await request.get("/api/tasks");
  expect(read.status()).toBe(401);
  const login = await request.post("/api/session", {
    headers: { Origin: "https://evil.example" },
    data: { password: "lifeos automated test password" },
  });
  expect(login.status()).toBe(403);
  const huge = await request.post("/api/session", {
    headers: { Origin: BASE },
    data: { password: "a".repeat(70000) },
  });
  expect(huge.status()).toBe(413);
});

test("retains a form draft through session reauthentication", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await page.getByRole("button", { name: "משימה חדשה", exact: true }).click();
  await page.getByLabel("כותרת", { exact: true }).fill("טיוטה שלא תאבד");
  await page.route("**/api/tasks", async (route) => {
    if (route.request().method() === "POST")
      await route.fulfill({ status: 401, json: { detail: "Expired" } });
    else await route.continue();
  });
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה ושמירת הטיוטה" }).click();
  await expect(page.getByLabel("כותרת", { exact: true })).toHaveValue(
    "טיוטה שלא תאבד",
  );
  await page.unroute("**/api/tasks");
  await page.getByRole("button", { name: "שמירה", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("טיוטה שלא תאבד", { exact: true })).toBeVisible();
});

test("PWA caches only public assets and shows an offline fallback", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await expect
    .poll(() =>
      page.evaluate(() => Boolean(navigator.serviceWorker.controller)),
    )
    .toBe(true);
  const urls = await page.evaluate(async () => {
    const active = (await caches.keys()).filter(name => name.startsWith("lifeos-static-"));
    if (active.length !== 1) throw Error("Expected one active public cache");
    const cache = await caches.open(active[0]);
    return (await cache.keys()).map((request) => new URL(request.url).pathname);
  });
  expect(urls).toContain("/offline.html");
  expect(urls.some((url) => url.startsWith("/api/") || url === "/")).toBe(
    false,
  );
  await context.setOffline(true);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "המרחב שלך מחכה לך." }),
  ).toBeVisible();
  await context.setOffline(false);
});
