import { test, expect } from "@playwright/test";
import { prepareFixtures, BASE } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test("assistant is honest when unavailable and saves only after explicit confirmation", async ({ page }) => {
  let ready = false;
  await page.route("**/api/assistant/status", route => route.fulfill({ json: { ready, local: true, model: "fixture-only", state: ready ? "ready" : "runtime_unavailable" } }));
  await page.route("**/api/assistant/chat", route => route.fulfill({ json: {
    reply: "בדוק ואשר את הפרטים", proposal: { id: "fixture-proposal", kind: "task", payload: { title: "משימת עוזר לבדיקה", due: "2026-10-28" } },
  } }));
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await page.getByRole("button", { name: "העוזר האישי", exact: true }).click();
  await expect(page.getByText("המודל המקומי אינו זמין כרגע.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "שליחת הודעה", exact: true })).toBeDisabled();
  ready = true;
  await page.getByRole("button", { name: "בדוק שוב", exact: true }).click();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  await page.route("**/api/assistant/confirm", async route => {
    const response = await page.request.post("/api/tasks", {
      headers: { Origin: BASE, "X-CSRF-Token": session.csrf },
      data: { title: "משימת עוזר לבדיקה", due: "2026-10-28" },
    });
    const task = await response.json();
    return route.fulfill({ json: { id: task.id, kind: "task" } });
  });
  await page.getByLabel("הודעה לעוזר", { exact: true }).fill("תוסיף משימה לבדיקה מחר");
  await page.getByRole("button", { name: "שליחת הודעה", exact: true }).click();
  await expect(page.getByRole("button", { name: "אישור ושמירה", exact: true })).toBeVisible();
  expect(await (await page.request.get("/api/tasks")).json()).toEqual([]);
  await page.screenshot({ path: "../../.runtime/screenshots/assistant-proposal.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../.runtime/screenshots/assistant-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "אישור ושמירה", exact: true }).click();
  await expect(page.getByText("נשמר בהצלחה", { exact: true })).toBeVisible();
  const tasks = await (await page.request.get("/api/tasks")).json();
  expect(tasks).toHaveLength(1);
  await page.getByRole("button", { name: "סגירה", exact: true }).click();
});
