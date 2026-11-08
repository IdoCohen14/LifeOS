import { test, expect } from "@playwright/test";

test("isolated account signup, academic workspace, private tasks and archives", async ({ browser }) => {
  test.skip(process.env.LIFEOS_ACCOUNT_E2E !== "1", "Requires isolated account test-mode server");
  const base = process.env.LIFEOS_TEST_BASE_URL;
  if (!base || new URL(base).hostname !== "127.0.0.1" || new URL(base).port === "3000")
    throw new Error("Use an explicit isolated test server");
  const left = await browser.newContext({ baseURL: base });
  const right = await browser.newContext({ baseURL: base });
  const errors: string[] = [];
  try {
    const mode = await left.request.get("/api/mode");
    expect(await mode.json()).toMatchObject({ account_mode: true, test_mode: true });
    const a = await left.newPage(); const b = await right.newPage();
    a.on("pageerror", error => errors.push(error.message));
    b.on("pageerror", error => errors.push(error.message));
    const suffix = Date.now();
    for (const [page, login] of [[a, `fixture-a-${suffix}`], [b, `fixture-b-${suffix}`]] as const) {
      await page.goto("/");
      await page.getByLabel("שם משתמש", { exact: true }).fill(login);
      await page.getByLabel("הסיסמה שלך", { exact: true }).fill("fixture account password");
      await page.getByRole("button", { name: "יצירת חשבון חדש", exact: true }).click();
      await page.getByLabel("אימות סיסמה", { exact: true }).fill("fixture account password");
      await page.getByRole("button", { name: "צור חשבון", exact: true }).click();
      await expect(page.locator("#page-title")).toHaveText("הגדרות");
      await page.goto("/?view=dashboard");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("היום שלי");
    }
    await expect(a.locator("html")).toHaveAttribute("dir", "rtl");
    await a.getByRole("button", { name: "משימה חדשה", exact: true }).click();
    await a.getByLabel("כותרת", { exact: true }).fill("משימה פרטית — נתוני דמה");
    await a.getByRole("button", { name: "שמירה", exact: true }).click();
    await expect(a.getByText("משימה פרטית — נתוני דמה", { exact: true })).toBeVisible();
    await b.reload();
    await expect(b.getByText("משימה פרטית — נתוני דמה", { exact: true })).toHaveCount(0);
    const sa = await (await left.request.get("/api/session")).json();
    const sb = await (await right.request.get("/api/session")).json();
    const ha = { Origin: base, "X-CSRF-Token": sa.csrf };
    const hb = { Origin: base, "X-CSRF-Token": sb.csrf };
    const tasks = await (await left.request.get("/api/tasks")).json();
    expect((await right.request.put(`/api/tasks/${tasks[0].id}`, { headers: hb, data: { title: "Foreign" } })).status()).toBe(404);
    const term = await (await left.request.post("/api/academic/terms", { headers: ha,
      data: { name: "תקופת דמה", start_date: "2026-11-01", end_date: "2027-01-31" } })).json();
    expect((await left.request.post("/api/academic/courses", { headers: ha,
      data: { term_id: term.id, name: "קורס דמה פרטי" } })).status()).toBe(201);
    expect(await (await right.request.get("/api/academic/courses")).json()).toEqual([]);
    const saved = await left.request.post("/api/recovery/backups", { headers: ha, data: { password: "fixture backup password" } });
    expect(saved.status()).toBe(201);
    const backup = await saved.json();
    expect(await (await right.request.get("/api/recovery/backups")).json()).toEqual([]);
    expect((await right.request.get(`/api/recovery/backups/${backup.id}`)).status()).toBe(404);
    await a.goto("/?view=settings");
    await a.locator("summary").getByText("גיבוי ושחזור", { exact: true }).click();
    await expect(a.getByRole("heading", { name: "גיבוי החשבון", exact: true })).toBeVisible();
    await a.getByRole("button", { name: "בדיקה ושחזור", exact: true }).first().click();
    const restore = a.getByRole("dialog");
    await restore.getByLabel("סיסמת הגיבוי לשחזור", { exact: true }).fill("fixture backup password");
    await restore.getByRole("button", { name: "בדיקת הגיבוי", exact: true }).click();
    await expect(restore.getByRole("button", { name: "אישור שחזור החשבון", exact: true })).toBeVisible();
    // Reviewing the real fixture archive must leave the account unchanged until confirmation.
    expect((await (await left.request.get("/api/tasks")).json()).map((task: { id: string }) => task.id)).toEqual(tasks.map((task: { id: string }) => task.id));
    await restore.getByRole("button", { name: "ביטול", exact: true }).click();
    await expect(restore).toHaveCount(0);
    const later = await left.request.post("/api/tasks", { headers: ha, data: { title: "אחרי הגיבוי — דמה" } });
    expect(later.status()).toBe(201);
    const other = await right.request.post("/api/tasks", { headers: hb, data: { title: "נשאר בחשבון השני — דמה" } });
    expect(other.status()).toBe(201);
    const otherTask = await other.json();
    await a.getByRole("button", { name: "בדיקה ושחזור", exact: true }).first().click();
    await restore.getByLabel("סיסמת הגיבוי לשחזור", { exact: true }).fill("fixture backup password");
    await restore.getByRole("button", { name: "בדיקת הגיבוי", exact: true }).click();
    const restoredResponse = a.waitForResponse(response => response.url().includes("/api/recovery/restore/") && response.url().endsWith("/confirm") && response.ok());
    await restore.getByRole("button", { name: "אישור שחזור החשבון", exact: true }).click();
    expect((await restoredResponse).status()).toBe(200);
    await expect(a.getByLabel("שם משתמש", { exact: true })).toBeVisible();
    await a.getByLabel("שם משתמש", { exact: true }).fill(`fixture-a-${suffix}`);
    await a.getByLabel("הסיסמה שלך", { exact: true }).fill("fixture account password");
    await a.getByRole("button", { name: "כניסה למרחב שלך", exact: true }).click();
    await expect(a.locator("#page-title")).toHaveText("הגדרות");
    expect((await (await left.request.get("/api/tasks")).json()).map((task: { id: string }) => task.id)).toEqual(tasks.map((task: { id: string }) => task.id));
    expect((await (await right.request.get("/api/tasks")).json()).map((task: { id: string }) => task.id)).toEqual([otherTask.id]);
    expect((await right.request.get("/api/session")).ok()).toBe(true);
    expect((await (await left.request.get("/api/academic/courses")).json())).toHaveLength(1);
    const restoredBackups = await (await left.request.get("/api/recovery/backups")).json();
    expect(restoredBackups.some((record: { id: string }) => record.id !== backup.id)).toBe(true);
    await a.locator("summary").getByText("גיבוי ושחזור", { exact: true }).click();
    await a.screenshot({ path: "../../.runtime/screenshots/accounts-settings.png", fullPage: true });
    expect(errors).toEqual([]);
  } finally { await left.close(); await right.close(); }
});
