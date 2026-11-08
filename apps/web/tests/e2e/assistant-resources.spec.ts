import { test, expect } from '@playwright/test';
import { prepareFixtures } from './helpers';

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));
test('assistant source limits preserve unsent draft and retryable proposal', async ({ page }) => {
  await page.route('**/api/assistant/status', route => route.fulfill({ json: { ready: true, local: true, model: 'fixture-only', state: 'ready' } }));
  let limited = true;
  await page.route('**/api/assistant/chat', route => route.fulfill(limited ? { status: 503, json: { detail: 'assistant_resource_limit' } } : { json: { reply: 'Fixture review', proposal: { id: '00000000-0000-0000-0000-000000000001', kind: 'event', payload: { title: 'Resource proposal fixture', start: '2026-10-28T08:00:00Z', end: '2026-10-28T09:00:00Z', all_day: false } } } }));
  await page.route('**/api/assistant/confirm', route => route.fulfill({ status: 503, json: { detail: 'assistant_resource_limit' } }));
  await page.goto('/');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await page.getByRole('button', { name: 'העוזר האישי', exact: true }).click();
  const message = page.getByLabel('הודעה לעוזר', { exact: true });
  await message.fill('מצא 60 דקות פנויות מחר');
  await page.getByRole('button', { name: 'שליחת הודעה', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('בדיקת היומן חרגה ממגבלת המשאבים');
  await expect(message).toHaveValue('מצא 60 דקות פנויות מחר');
  limited = false;
  await page.getByRole('button', { name: 'שליחת הודעה', exact: true }).click();
  const confirm = page.getByRole('button', { name: 'אישור ושמירה', exact: true });
  await expect(confirm).toBeVisible();
  await message.fill('טיוטה נוספת שלא תאבד');
  await confirm.click();
  await expect(page.getByRole('alert')).toContainText('בדיקת היומן חרגה ממגבלת המשאבים');
  await expect(confirm).toBeEnabled();
  await expect(message).toHaveValue('טיוטה נוספת שלא תאבד');
  expect(await (await page.request.get('/api/events')).json()).toEqual([]);
});
