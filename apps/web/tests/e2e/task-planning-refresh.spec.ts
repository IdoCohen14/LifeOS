import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures, openDashboardTool } from "./helpers";
import { shiftDay } from "../../lib/dates";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("acknowledged task planning closes during refresh and protects a reopened draft", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  expect((await page.request.post("/api/tasks", { headers: { Origin: BASE, "X-CSRF-Token": session.csrf }, data: { title: "Refresh planner fixture" } })).ok()).toBe(true);
  await page.reload();
  await openDashboardTool(page, "למצוא זמן למשימות");
  await page.getByRole("button", { name: "מציאת משבצת זמן", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "תכנון זמן למשימה" });
  await dialog.getByLabel("מתאריך", { exact: true }).fill(shiftDay(await dialog.getByLabel("מתאריך", { exact: true }).inputValue(), 1));
  await dialog.getByRole("button", { name: "הצעת זמן", exact: true }).click();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/events", async route => { await gate; await route.fulfill({ status: 503, json: { detail: "Fixture refresh failure" } }); });
  let saves = 0;
  page.on("request", request => { if (request.url().endsWith("/api/assistant/confirm") && request.method() === "POST") saves++; });
  await dialog.getByRole("button", { name: "אישור ושמירה ביומן", exact: true }).click();
  await expect(dialog.getByText("נשמר ביומן. המשימה נשארת פתוחה.", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "סגירה", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "מציאת משבצת זמן", exact: true }).click();
  await dialog.getByLabel("משך בדקות", { exact: true }).fill("45");
  release();
  await expect(page.getByText("התצוגה אינה מעודכנת. יש לרענן לפני פעולה נוספת.", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("משך בדקות", { exact: true })).toHaveValue("45");
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  expect(await (await page.request.get("/api/events")).json()).toHaveLength(1);
  expect(saves).toBe(1);
});
