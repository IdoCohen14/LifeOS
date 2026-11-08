import { expect, type Page, type PlaywrightWorkerArgs } from "@playwright/test";
export const BASE = process.env.LIFEOS_TEST_BASE_URL || "http://127.0.0.1:3000";
export async function prepareFixtures(
  playwright: PlaywrightWorkerArgs["playwright"],
) {
  const api = await playwright.request.newContext({
    baseURL: BASE,
    extraHTTPHeaders: { Origin: BASE },
  });
  expect(
    (
      await api.post("/api/session", {
        data: { password: "lifeos automated test password" },
      })
    ).ok(),
  ).toBe(true);
  const session = await (await api.get("/api/session")).json();
  expect(
    session.test_mode,
    "Refusing to modify data outside the explicitly isolated test server",
  ).toBe(true);
  const headers = { "X-CSRF-Token": session.csrf };
  const pushDevices = await (await api.get("/api/push/subscriptions")).json();
  for (const device of pushDevices) expect((await api.delete(`/api/push/subscriptions/${device.id}`, { headers })).ok()).toBe(true);
  const backupSchedule = await (await api.get("/api/recovery/schedule")).json();
  expect((await api.put("/api/recovery/schedule", { headers, data: { enabled: false, clock: backupSchedule.clock, keep: backupSchedule.keep, revision: backupSchedule.revision, timezone: backupSchedule.timezone, password: null } })).ok()).toBe(true);
  const preferences = await (await api.get("/api/planning/preferences")).json();
  expect((await api.delete("/api/planning/preferences", { headers, data: { revision: preferences.revision } })).ok()).toBe(true);
  expect((await api.put("/api/assistant/history", { headers, data: { enabled: false } })).ok()).toBe(true);
  expect((await api.delete("/api/assistant/history", { headers })).ok()).toBe(true);
  expect((await api.put("/api/briefings/schedule", { headers, data: { daily_enabled: false, weekly_enabled: false } })).ok()).toBe(true);
  for (const kind of [
    "academic/documents",
    "academic/items",
    "academic/timetable",
    "academic/grades",
    "academic/courses",
    "academic/terms",
    "tasks",
    "events",
  ]) {
    const list = await api.get(`/api/${kind}`);
    expect(list.ok()).toBe(true);
    for (const item of await list.json())
      expect(
        (await api.delete(`/api/${kind}/${item.id}`, { headers })).status(),
      ).toBe(204);
  }
  expect(
    (
      await api.put("/api/settings", {
        headers,
        data: {
          display_name: "",
          language: "he",
          theme: "dark",
          timezone: "Asia/Jerusalem",
        },
      })
    ).ok(),
  ).toBe(true);
  expect((await api.put("/api/notifications/preferences", { headers, data: { enabled: true, tasks: true, conflicts: true, briefings: true, quiet_enabled: true, quiet_start: "22:00", quiet_end: "07:00" } })).ok()).toBe(true);
  await api.delete("/api/session", { headers });
  await api.dispose();
}

export async function openDashboardTool(page: Page, name: string) {
  const group = page.locator(".dashboard-more");
  if (!(await group.evaluate(element => (element as HTMLDetailsElement).open)))
    await group.locator(":scope > summary").click();
  const summary = page.locator(".dashboard-tool > summary").filter({ hasText: name });
  if (!(await summary.locator("..").evaluate(element => (element as HTMLDetailsElement).open)))
    await summary.click();
}

export async function openSettingsSection(page: Page, label: string) {
  const summary = page.locator(".settings-layout > .section-fold > summary").filter({ hasText: label });
  if (!(await summary.locator("..").evaluate(element => (element as HTMLDetailsElement).open)))
    await summary.click();
}
export async function openConnection(page: Page, name: string, english = false) {
  await openSettingsSection(page, english ? "My connections" : "החיבורים שלי");
  const summary = page.locator(".connection-fold > summary").filter({ hasText: name });
  if (!(await summary.locator("..").evaluate(element => (element as HTMLDetailsElement).open)))
    await summary.click();
}
