import { test, expect } from '@playwright/test';
import { prepareFixtures } from './helpers';
test.beforeAll(async ({ playwright }) => prepareFixtures(playwright));
test('history requires consent, reloads text only and clears explicitly', async ({ page }) => {
  await page.route('**/api/assistant/status', route => route.fulfill({ json: { ready: true, local: true, model: 'fixture-only', state: 'ready' } }));
  await page.goto('/');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  const open = async () => {
    await page.getByRole('button', { name: 'העוזר האישי', exact: true }).click();
    await page.getByText(/^היסטוריית שיחה מקומית/).click();
  };
  await open();
  await page.getByRole('button', { name: 'הפעלת שמירת שיחה', exact: true }).click();
  await page.getByLabel('הודעה לעוזר', { exact: true }).fill('solve my homework fixture');
  await page.getByRole('button', { name: 'שליחת הודעה', exact: true }).click();
  await expect.poll(async () => (await (await page.request.get('/api/assistant/history')).json()).stored_count).toBe(1);
  await page.reload(); await open();
  await expect(page.getByText('טקסט משיחה שמורה', { exact: false })).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'אישור ושמירה', exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../../.runtime/screenshots/conversation-history-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'מחיקת ההיסטוריה', exact: true }).click();
  await page.getByRole('button', { name: 'אישור מחיקת ההיסטוריה', exact: true }).click();
  await expect.poll(async () => (await (await page.request.get('/api/assistant/history')).json()).stored_count).toBe(0);
  await page.getByRole('button', { name: 'כיבוי שמירת שיחה', exact: true }).click();
});
test('context reset preserves the current answer but excludes it from the next request', async ({ page }) => {
  await page.route('**/api/assistant/status', route => route.fulfill({ json: { ready: true, local: true, state: 'ready', model: 'fixture' } }));
  let requests = 0;
  await page.route('**/api/assistant/chat', async route => {
    const body = route.request().postDataJSON();
    if (requests++) expect(body.history).toEqual([]);
    await route.fulfill({ json: { reply: 'Current fixture answer', proposal: null, history_discarded: true, history_state: { enabled: false, generation: body.history_generation }, history_saved: false } });
  });
  await page.goto('/');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await page.getByRole('button', { name: 'העוזר האישי', exact: true }).click();
  for (let i = 0; i < 2; i++) {
    await page.getByLabel('הודעה לעוזר', { exact: true }).fill(`Fixture ${i}`);
    await page.getByRole('button', { name: 'שליחת הודעה', exact: true }).click();
    await expect(page.getByText('Current fixture answer', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'שליחת הודעה', exact: true })).toBeDisabled();
  }
  expect(requests).toBe(2);
});
