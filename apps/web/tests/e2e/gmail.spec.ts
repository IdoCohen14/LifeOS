import { test, expect } from "@playwright/test";
import { prepareFixtures, BASE } from "./helpers";

test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test("Gmail has one-click read-only consent and safe mobile previews", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("הסיסמה שלך").fill("lifeos automated test password");
  await page.getByRole("button", { name: "כניסה למרחב שלך" }).click();
  await expect(page.getByRole("link", { name: "הגדרות", exact: true })).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  expect(session.test_mode).toBe(true);
  await page.request.post("/api/integrations/google/config", {
    headers: { Origin: BASE, "X-CSRF-Token": session.csrf },
    data: { client_id: "fixture.apps.googleusercontent.com", client_secret: "fixture-secret" },
  });
  await page.getByRole("link", { name: "הגדרות", exact: true }).click();
  await page.locator("summary").getByText("החיבורים שלי",{exact:true}).click();
  await page.locator("summary").getByText("Gmail",{exact:true}).click();
  await expect(page.getByRole("button", { name: "חיבור Gmail", exact: true })).toBeVisible();
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await page.route("https://accounts.google.com/**", route => route.fulfill({ contentType: "text/plain", body: "Mock Google consent: test only" }));
  await page.getByRole("button", { name: "חיבור Gmail", exact: true }).click();
  await page.waitForURL("https://accounts.google.com/**");
  const consent = new URL(page.url());
  expect(consent.searchParams.get("scope")).toBe("https://www.googleapis.com/auth/gmail.readonly");
  expect(consent.searchParams.get("state")).toMatch(/^gmail\./);
  await page.route("**/api/integrations/gmail/status", route => route.fulfill({ json: {
    configured: true, connected: true, state: "connected", error: null,
    syncing: false, stale: false, last_success: 1792920000,
  } }));
  let inbox = [{
    id: "fixture", subject: "הודעת בדיקה בלבד", sender: "fixture@example.test", snippet: '<img src="https://evil.example/pixel" onerror="alert(1)">',
    source_url: "https://mail.google.com/mail/#all/fixture",
  }, { id: "second", subject: "מייל שני", sender: "friend@example.test", snippet: "hello", source_url: "https://mail.google.com/mail/#all/second" }];
  await page.route("**/api/integrations/gmail/queue", route => route.fulfill({ json: inbox }));
  let last: typeof inbox[number] | undefined;
  await page.route("**/api/integrations/gmail/review", route => {
    const body = route.request().postDataJSON();
    if (body.undo && last) inbox = [last, ...inbox];
    else { last = inbox.find(m => m.id === body.id); inbox = body.all ? [] : inbox.filter(m => m.id !== body.id); }
    return route.fulfill({ json: inbox });
  });
  await page.goto("/?view=settings");
  await expect(page.getByText("הודעת בדיקה בלבד", { exact: true })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByText("הודעת בדיקה בלבד", { exact: true })).toBeVisible();
  await expect(page.getByText("מייל שני", { exact: true })).toHaveCount(0);
  await expect(page.locator('.daily-mail img')).toHaveCount(0);
  await expect(page.getByRole("link", { name: "לענות ב־Gmail", exact: true })).toHaveAttribute("rel", "noopener noreferrer");
  await page.screenshot({ path: "../../.runtime/screenshots/gmail-settings.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../../.runtime/screenshots/gmail-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "לא עכשיו — למייל הבא", exact: true }).click();
  await expect(page.getByText("מייל שני", { exact: true })).toBeVisible();
  await page.locator(".daily-mail").screenshot({ path: "../../.runtime/screenshots/mail-undo.png" });
  await page.getByRole("button", { name: "החזר את המייל האחרון", exact: true }).click();
  await expect(page.getByText("הודעת בדיקה בלבד", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "החזר את המייל האחרון", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "לא עכשיו — למייל הבא", exact: true }).click();
  await page.getByRole("button", { name: "סימון הכול כנקרא", exact: true }).click();
  await expect(page.getByText("אין מיילים חדשים", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("אין מיילים חדשים", { exact: true })).toBeVisible();
});
