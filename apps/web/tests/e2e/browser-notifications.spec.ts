import { test, expect } from "@playwright/test";
import { BASE, prepareFixtures } from "./helpers";

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));

test("browser notices request consent only on click and show only a generic mocked test", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const state = {
      permission: "default" as NotificationPermission,
      requests: 0,
      hidden: false,
      shown: [] as { title: string; options?: NotificationOptions }[],
    };
    Object.assign(window, { __noticeFixture: state });
    Object.defineProperty(document, "hidden", { get: () => state.hidden });
    Object.defineProperty(Notification, "permission", {
      get: () => state.permission,
    });
    Notification.requestPermission = async () => {
      state.requests++;
      state.permission = "granted";
      return "granted";
    };
    ServiceWorkerRegistration.prototype.showNotification = async (
      title,
      options,
    ) => {
      state.shown.push({ title, options });
    };
  });
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
        data: { title: "Private browser fixture", due: "2020-01-01" },
      })
    ).ok(),
  ).toBe(true);
  expect(
    (
      await page.request.put("/api/notifications/preferences", {
        headers,
        data: { quiet_enabled: false },
      })
    ).ok(),
  ).toBe(true);
  await page.goto("/?notifications=open");
  const dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await expect(dialog).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { __noticeFixture: { requests: number } })
          .__noticeFixture.requests,
    ),
  ).toBe(0);
  await dialog
    .getByRole("button", { name: "הפעלת התראות דפדפן", exact: true })
    .click();
  await expect(
    dialog.getByText("פעיל בדפדפן הזה", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { __noticeFixture: { requests: number } })
          .__noticeFixture.requests,
    ),
  ).toBe(1);
  await page.evaluate(() => {
    (
      window as unknown as { __noticeFixture: { hidden: boolean } }
    ).__noticeFixture.hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { __noticeFixture: { shown: unknown[] } })
            .__noticeFixture.shown.length,
      ),
    )
    .toBe(1);
  await page.evaluate(() => {
    (
      window as unknown as { __noticeFixture: { hidden: boolean } }
    ).__noticeFixture.hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await dialog
    .getByRole("button", { name: "שליחת התראת ניסיון", exact: true })
    .click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { __noticeFixture: { shown: unknown[] } })
            .__noticeFixture.shown.length,
      ),
    )
    .toBe(2);
  const notices = await page.evaluate(
    () =>
      (window as unknown as { __noticeFixture: { shown: unknown[] } })
        .__noticeFixture.shown,
  );
  expect(JSON.stringify(notices)).toContain(
    "יש עדכונים חדשים במרכז ההתראות שלך",
  );
  expect(JSON.stringify(notices)).not.toContain("source_ids");
  expect(JSON.stringify(notices)).not.toContain("Private browser fixture");
  await page.setViewportSize({ width: 390, height: 844 });
  await dialog.getByRole("region", { name: "התראות דפדפן", exact: true }).screenshot({ path: "../../.runtime/screenshots/browser-notifications-controls.png" });
  await dialog
    .getByRole("button", { name: "כיבוי התראות דפדפן", exact: true })
    .click();
  await expect(
    dialog.getByText("כבוי בדפדפן הזה", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.evaluate(() =>
    navigator.serviceWorker.dispatchEvent(
      new MessageEvent("message", {
        data: { type: "lifeos:open-notifications" },
      }),
    ),
  );
  await expect(dialog).toBeVisible();
});

test("blocked browser permission leaves the in-app center usable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(Notification, "permission", { get: () => "denied" });
  });
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.locator("#page-title")).toBeVisible();
  await page.goto("/?notifications=open");
  const dialog = page.getByRole("dialog", { name: "מרכז התראות", exact: true });
  await expect(dialog.getByText(/ההרשאה חסומה/)).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "הפעלת התראות דפדפן", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "רענון", exact: true }),
  ).toBeEnabled();
});
