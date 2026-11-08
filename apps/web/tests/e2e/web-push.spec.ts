import { test, expect } from '@playwright/test';
import { prepareFixtures } from './helpers';

function mockPush() {
  let permission: NotificationPermission = 'default';
  const calls = { permission: 0, subscribe: 0, unsubscribe: 0 };
  Object.assign(window, { fixturePushCalls: calls });
  Object.defineProperty(Notification, 'permission', { configurable: true, get: () => permission });
  Notification.requestPermission = async () => { calls.permission++; permission = 'granted'; return permission; };
  function current(): PushSubscription | null {
    const raw = localStorage.getItem('fixture.push.subscription');
    if (!raw) return null;
    const json = JSON.parse(raw);
    const key = Uint8Array.from(atob(json.keys.p256dh.replace(/-/g,'+').replace(/_/g,'/')+'='), value => value.charCodeAt(0)).buffer;
    return { endpoint: json.endpoint, options: { userVisibleOnly: true, applicationServerKey: key }, expirationTime: null,
      toJSON: () => json, getKey: () => null,
      unsubscribe: async () => { calls.unsubscribe++; localStorage.removeItem('fixture.push.subscription'); return true; },
    } as unknown as PushSubscription;
  }
  PushManager.prototype.getSubscription = async () => current();
  PushManager.prototype.subscribe = async options => {
    calls.subscribe++;
    const key = options?.applicationServerKey as ArrayBuffer;
    const encoded = btoa(String.fromCharCode(...new Uint8Array(key))).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');
    localStorage.setItem('fixture.push.subscription',JSON.stringify({ endpoint:'https://fcm.googleapis.com/fcm/send/browser-fixture-token-12345',expirationTime:null,keys:{p256dh:encoded,auth:btoa('0123456789abcdef').replace(/=/g,'')} }));
    return current()!;
  };
}
test.beforeEach(async ({ playwright }) => prepareFixtures(playwright));
test('Push permission is click-only, endpoints stay hidden and off unsubscribes', async ({ page }) => {
  await page.addInitScript(mockPush);
  await page.goto('/');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await page.getByRole('button', { name: /^מרכז התראות/ }).click();
  await page.getByText('Push כשהטאב סגור', { exact: true }).click();
  await page.getByText('הגדרת שולח במחשב', { exact: true }).click();
  await page.getByLabel('דוא״ל קשר למפעיל Push', { exact: true }).fill('operator-fixture@example.test');
  await page.getByRole('button', { name: 'שמירת הגדרת שולח Push', exact: true }).click();
  await expect(page.getByText('ההגדרה נשמרה.', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { fixturePushCalls: { permission: number } }).fixturePushCalls.permission)).toBe(0);
  await page.getByRole('button', { name: 'הפעלת Push בדפדפן הזה', exact: true }).click();
  await expect(page.getByText('Push פעיל בדפדפן הזה', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'הפעלת התראות דפדפן', exact: true })).toBeDisabled();
  const devices = await (await page.request.get('/api/push/subscriptions')).json();
  expect(devices).toHaveLength(1);
  expect(JSON.stringify(devices)).not.toContain('browser-fixture-token');
  await expect(page.getByText('browser-fixture-token', { exact: false })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByText('Push כשהטאב סגור', { exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: '../../.runtime/screenshots/web-push-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'כיבוי Push בדפדפן הזה', exact: true }).click();
  await expect(page.getByText('Push כבוי בדפדפן הזה', { exact: true })).toBeVisible();
  expect(await (await page.request.get('/api/push/subscriptions')).json()).toEqual([]);
  const calls = await page.evaluate(() => (window as unknown as { fixturePushCalls: object }).fixturePushCalls);
  expect(calls).toEqual({ permission: 1, subscribe: 1, unsubscribe: 1 });
});

test('service worker validates generic Push and deduplicates without actual OS display', async ({ page, context }) => {
  await page.goto('/');
  const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
  const value = await worker.evaluate(`(async () => {
    const shown = [];
    self.registration.showNotification = async (title, options) => { shown.push({ title, options }); };
    const payload = { id: 'f'.repeat(64), language: 'en', zone: 'Asia/Jerusalem', quiet_enabled: false, quiet_start: '22:00', quiet_end: '07:00', expires: Math.floor(Date.now()/1000)+300 };
    const first = await handleLifeosPush(payload);
    const again = await handleLifeosPush(payload);
    const invalid = await handleLifeosPush({ ...payload, title: 'Injected private fixture' });
    return { first, again, invalid, shown };
  })()`) as { first: boolean; again: boolean; invalid: boolean; shown: { title: string; options: { body: string } }[] };
  expect(value.first).toBe(true); expect(value.again).toBe(false); expect(value.invalid).toBe(false);
  expect(value.shown).toHaveLength(1);
  expect(value.shown[0].title).toBe('LifeOS');
  expect(value.shown[0].options.body).toBe('There are updates in your notification center.');
});


test('delayed lookup and another tab disabling Push reconcile under the same lock', async ({ page, context }) => {
  await context.addInitScript(mockPush);
  await page.goto('/');
  await page.getByLabel('הסיסמה שלך').fill('lifeos automated test password');
  await page.getByRole('button', { name: 'כניסה למרחב שלך' }).click();
  await page.getByRole('button', { name: /^מרכז התראות/ }).click();
  await page.getByText('Push כשהטאב סגור', { exact: true }).click();
  await page.getByText('הגדרת שולח במחשב', { exact: true }).click();
  await page.getByLabel('דוא״ל קשר למפעיל Push', { exact: true }).fill('operator-fixture@example.test');
  await page.getByRole('button', { name: 'שמירת הגדרת שולח Push', exact: true }).click();
  await expect(page.getByText('ההגדרה נשמרה.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'הפעלת Push בדפדפן הזה', exact: true }).click();
  await expect(page.getByText('Push פעיל בדפדפן הזה', { exact: true })).toBeVisible();
  const other = await context.newPage();
  await other.goto('/');
  await other.getByRole('button', { name: /^מרכז התראות/ }).click();
  let release!: () => void;
  let observed!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const arrived = new Promise<void>(resolve => { observed = resolve; });
  await other.route('**/api/push/lookup', async route => { const response = await route.fetch(); observed(); await held; await route.fulfill({ response }); });
  await other.getByText('Push כשהטאב סגור', { exact: true }).click();
  await arrived;
  try {
    await page.getByRole('button', { name: 'כיבוי Push בדפדפן הזה', exact: true }).click();
    await expect.poll(async () => (await page.evaluate(async () => navigator.locks.query())).pending?.filter(lock => lock.name === 'lifeos-browser-notice-delivery').length).toBe(1);
  } finally { release(); }
  await expect(page.getByText('Push כבוי בדפדפן הזה', { exact: true })).toBeVisible();
  await expect.poll(() => other.evaluate(() => localStorage.getItem('lifeos.push.device.v1'))).toBeNull();
  expect(await (await page.request.get('/api/push/subscriptions')).json()).toEqual([]);
});
