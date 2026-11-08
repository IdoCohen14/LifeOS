import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures, openDashboardTool } from "./helpers";
import { localInstant, shiftDay } from "../../lib/dates";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("task planning reviews/cancels then explicitly saves once without completing the task", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const headers = { Origin: BASE, "X-CSRF-Token": session.csrf };
  const task = await (
    await page.request.post("/api/tasks", {
      headers,
      data: { title: "Planning browser fixture" },
    })
  ).json();
  await page.goto("/");
  await openDashboardTool(page, "למצוא זמן למשימות");
  await page
    .getByRole("button", { name: "מציאת משבצת זמן", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "תכנון זמן למשימה",
    exact: true,
  });
  const tomorrow = shiftDay(
    await dialog.getByLabel("מתאריך", { exact: true }).inputValue(),
    1,
  );
  await dialog.getByLabel("מתאריך", { exact: true }).fill(tomorrow);
  expect(
    (
      await page.request.post("/api/events", {
        headers,
        data: {
          title: "Busy planning fixture",
          start: localInstant(`${tomorrow}T08:00`, "Asia/Jerusalem"),
          end: localInstant(`${tomorrow}T09:00`, "Asia/Jerusalem"),
        },
      })
    ).ok(),
  ).toBe(true);
  await dialog.getByRole("button", { name: "הצעת זמן", exact: true }).click();
  await expect(dialog.locator(".planner-proposal strong")).toHaveText(
    task.title,
  );
  await expect(dialog.locator(".planner-proposal")).toContainText("09:00");
  expect((await (await page.request.get("/api/events")).json()).length).toBe(1);
  await dialog
    .getByRole("button", { name: "שינוי הבקשה", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "אישור ושמירה ביומן", exact: true }),
  ).toHaveCount(0);
  await dialog.getByLabel("משך בדקות", { exact: true }).fill("45");
  await dialog.getByRole("button", { name: "הצעת זמן", exact: true }).click();
  await page.setViewportSize({ width: 320, height: 740 });
  await dialog
    .locator(".planner-proposal")
    .screenshot({
      path: "../../.runtime/screenshots/task-planning-proposal-mobile.png",
    });
  expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(
    true,
  );
  await dialog
    .getByRole("button", { name: "אישור ושמירה ביומן", exact: true })
    .click();
  await expect(
    dialog.getByText("נשמר ביומן. המשימה נשארת פתוחה.", { exact: true }),
  ).toBeVisible();
  expect((await (await page.request.get("/api/events")).json()).length).toBe(2);
  expect(await (await page.request.get("/api/tasks")).json()).toEqual([task]);
  await dialog
    .getByRole("button", { name: "פתיחה ביומן", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`view=calendar&day=${tomorrow}`));
  await page.goto("/");
  await openDashboardTool(page, "למצוא זמן למשימות");
  await page
    .getByRole("button", { name: "מציאת משבצת זמן", exact: true })
    .click();
  await dialog.getByLabel("מתאריך", { exact: true }).fill(tomorrow);
  await dialog.getByRole("button", { name: "הצעת זמן", exact: true }).click();
  await expect(
    dialog.getByText("כבר מוקצה למשימה זמן עתידי ביומן.", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "אישור ושמירה ביומן", exact: true }),
  ).toHaveCount(0);
});

test("changed task rejects approval and English planning remains available without a model", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  const headers = { Origin: BASE, "X-CSRF-Token": session.csrf };
  const task = await (
    await page.request.post("/api/tasks", {
      headers,
      data: { title: "Changed planner fixture" },
    })
  ).json();
  await page.request.put("/api/settings", {
    headers,
    data: { language: "en", theme: "light" },
  });
  await page.goto("/");
  await openDashboardTool(page, "Make time for tasks");
  await page
    .getByRole("button", { name: "Find a time block", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Plan time for a task",
    exact: true,
  });
  await dialog
    .getByLabel("Starting date", { exact: true })
    .fill(
      shiftDay(
        await dialog.getByLabel("Starting date", { exact: true }).inputValue(),
        1,
      ),
    );
  await dialog
    .getByRole("button", { name: "Suggest a time", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", {
      name: "Confirm and save to calendar",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (
      await page.request.put(`/api/tasks/${task.id}`, {
        headers,
        data: { title: "Changed after proposal" },
      })
    ).ok(),
  ).toBe(true);
  await dialog
    .getByRole("button", { name: "Confirm and save to calendar", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("changed");
  expect(await (await page.request.get("/api/events")).json()).toEqual([]);
});
