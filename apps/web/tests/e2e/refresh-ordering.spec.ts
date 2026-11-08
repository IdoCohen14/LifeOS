import { test, expect } from '@playwright/test';
import { BASE, prepareFixtures } from './helpers';

test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));
const warning = 'התצוגה אינה מעודכנת. יש לרענן לפני פעולה נוספת.';
for (const outcomes of ['success-success', 'failure-success', 'success-failure']) {
  test(`latest requested snapshot controls data and status: ${outcomes}`, async ({ page }) => {
    await page.goto('/?view=tasks');
    await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
    await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
    await expect(page.getByRole('button', { name: 'משימה חדשה', exact: true })).toBeVisible();
    const session = await (await page.request.get('/api/session')).json();
    expect(session.test_mode).toBe(true);
    let release!: () => void, captured!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const firstCaptured = new Promise<void>(resolve => { captured = resolve; });
    let reads = 0;
    await page.route('**/api/tasks', async route => {
      reads += 1;
      const first = reads === 1;
      const source = await route.fetch();
      const body = await source.json();
      if (first) { captured(); await gate; }
      const failed = first ? outcomes.startsWith('failure') : outcomes.endsWith('failure');
      await route.fulfill({ status: failed ? 503 : 200, json: failed ? { detail: 'Fixture ordering failure' } : body, headers: { 'X-Fixture-Generation': first ? 'old' : 'new' } });
    });
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await firstCaptured;
    expect((await page.request.post('/api/tasks', { headers: { Origin: BASE, 'X-CSRF-Token': session.csrf }, data: { title: 'Latest snapshot fixture' } })).ok()).toBe(true);
    const newer = page.waitForResponse(response => response.url().endsWith('/api/tasks') && response.headers()['x-fixture-generation'] === 'new');
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await (await newer).finished();
    const newerFailed = outcomes.endsWith('failure');
    if (newerFailed) await expect(page.getByText(warning, { exact: true })).toBeVisible();
    else await expect(page.getByText('Latest snapshot fixture', { exact: true })).toBeVisible();
    release();
    await page.unrouteAll({ behavior: 'wait' });
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    if (newerFailed) await expect(page.getByText(warning, { exact: true })).toBeVisible();
    else {
      await expect(page.getByText('Latest snapshot fixture', { exact: true })).toBeVisible();
      await expect(page.getByText(warning, { exact: true })).not.toBeVisible();
    }
    expect(reads).toBe(2);
  });
}

test('an authenticated snapshot cannot overwrite signed-out settings', async ({ page }) => {
  await page.goto('/?view=tasks');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await expect(page.getByRole('button', { name: 'משימה חדשה', exact: true })).toBeVisible();
  const session = await (await page.request.get('/api/session')).json();
  expect(session.test_mode).toBe(true);
  expect((await page.request.put('/api/settings', { headers: { Origin: BASE, 'X-CSRF-Token': session.csrf }, data: { language: 'en', theme: 'light', timezone: 'Asia/Jerusalem' } })).ok()).toBe(true);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/tasks', async route => { const response = await route.fetch(); const body = await response.json(); await gate; await route.fulfill({ status: 200, json: body }); });
  const otherReads = ['events', 'settings', 'academic/calendar', 'integrations/google/events', 'integrations/google/status', 'integrations/gmail/status', 'integrations/moodle/events', 'integrations/moodle/status', 'recommendations', 'notifications'].map(path => page.waitForResponse(response => response.url().endsWith(`/api/${path}`)).then(response => response.finished()));
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await Promise.all(otherReads);
  await page.getByRole('button', { name: /יציאה/ }).click();
  await expect(page.getByLabel('הסיסמה שלך')).toBeVisible();
  release();
  await page.unrouteAll({ behavior: 'wait' });
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByLabel('הסיסמה שלך')).toBeVisible();
  expect(await page.locator('html').getAttribute('lang')).toBe('he');
});
