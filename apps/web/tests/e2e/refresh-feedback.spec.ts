import { test, expect } from '@playwright/test';
import { prepareFixtures } from './helpers';

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));
const warning = 'התצוגה אינה מעודכנת. יש לרענן לפני פעולה נוספת.';

test('refresh failure remains visible after acknowledged creation dialog is closed', async ({ page }) => {
  await page.goto('/?view=calendar');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await page.getByRole('button', { name: 'אירוע שבועי חוזר', exact: true }).click();
  await page.getByLabel('כותרת האירוע החוזר').fill('Refresh acknowledgement fixture');
  await page.getByLabel('מספר מופעים שבועיים').fill('2');
  await page.getByRole('button', { name: 'תצוגה מקדימה של המופעים', exact: true }).click();
  await expect(page.locator('.recurring-preview-list li')).toHaveCount(2);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/events', async route => { await gate; await route.fulfill({ status: 503, json: { detail: 'Fixture read failure' } }); });
  let saves = 0;
  page.on('request', request => { if (request.url().endsWith('/api/recurrence/confirm') && request.method() === 'POST') saves += 1; });
  await page.getByRole('button', { name: 'אישור יצירת 2 אירועים', exact: true }).click();
  await expect(page.getByText('האירועים נוצרו ביומן האישי.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'סגירה', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  release();
  await expect(page.getByText(warning, { exact: true })).toBeVisible();
  await page.unrouteAll({ behavior: 'wait' });
  await page.getByRole('button', { name: 'רענון', exact: true }).click();
  await expect(page.getByText(warning, { exact: true })).not.toBeVisible();
  expect(await (await page.request.get('/api/events')).json()).toHaveLength(2);
  expect(saves).toBe(1);
});

test('background refresh warning does not claim that a write occurred', async ({ page }) => {
  await page.goto('/?view=calendar');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await expect(page.getByRole('button', { name: 'אירוע שבועי חוזר', exact: true })).toBeVisible();
  await page.route('**/api/events', route => route.fulfill({ status: 503, json: { detail: 'Fixture background failure' } }));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByText(warning, { exact: true })).toBeVisible();
  await expect(page.getByText('השינוי נשמר, אך התצוגה לא התעדכנה. יש לרענן לפני פעולה נוספת.', { exact: true })).not.toBeVisible();
});
