import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it, vi } from 'vitest';
it('recognizes a dated lesson using the existing backward-compatible copy fields', () => {
  const context = vm.createContext({ self: { addEventListener: vi.fn() }, Date, Intl, URL });
  vm.runInContext(readFileSync('public/sw.js', 'utf8'), context);
  const policy = vm.runInContext('pushNotice', context) as (v: unknown, now: number) => { options: { data: { url?: string } } } | null;
  const now = Date.parse('2026-11-04T12:00:00Z');
  const value = { id:'c'.repeat(64),language:'he',zone:'Asia/Jerusalem',quiet_enabled:false,quiet_start:'22:00',quiet_end:'07:00',expires:now/1000+300,notice_title:'שיעור הבא — קורס הדגמה',notice_body:'2026-11-04 14:10 · L 709' };
  expect(policy(value, now)?.options.data.url).toBe('/?view=timetable&day=2026-11-04');
  expect(policy({...value,notice_url:'https://outside.test'},now)).toBeNull();
  expect(policy({...value,notice_body:'2026-02-31 14:10 · L 709'},now)?.options.data.url).toBeUndefined();
  expect(policy({...value,notice_title:'אירוע מתקרב'},now)?.options.data.url).toBeUndefined();
  expect(policy({...value,visible_required:true,expires:1},now)?.options.data.url).toBeUndefined();
});
it('Push receive policy allows only generic fresh notices outside workspace quiet time', () => {
  const context = vm.createContext({ self: { addEventListener: vi.fn() }, Date, Intl, URL });
  vm.runInContext(readFileSync('public/sw.js', 'utf8'), context);
  const policy = vm.runInContext('pushNotice', context) as (value: unknown, now: number) => { title: string; options: { body: string } } | null;
  const now = Date.parse('2026-10-27T19:59:59Z');
  const value = { id: 'a'.repeat(64), language: 'en', zone: 'Asia/Jerusalem', quiet_enabled: true, quiet_start: '22:00', quiet_end: '07:00', expires: Math.floor(now / 1000) + 300 };
  expect(policy(value, now)?.title).toBe('LifeOS');
  expect(policy(value, now + 1000)).toBeNull();
  expect(policy({ ...value, title: 'Injected private title' }, now)).toBeNull();
  expect(policy({ ...value, expires: Math.floor(now / 1000) - 1 }, now)).toBeNull();
  expect(policy({ ...value, zone: 'not/a-zone' }, now)).toBeNull();
});
it('Apple deliveries are visibly replaced even if late or repeated; server enforces quiet hours before sending', async () => {
  const display = vi.fn().mockResolvedValue(undefined);
  const context = vm.createContext({ self: { addEventListener: vi.fn(), registration: { showNotification: display } }, Date, Intl, URL });
  vm.runInContext(readFileSync('public/sw.js', 'utf8'), context);
  const handle = vm.runInContext('handleLifeosPush', context) as (value: unknown) => Promise<boolean>;
  const value = { id: 'b'.repeat(64), language: 'en', zone: 'Asia/Jerusalem', quiet_enabled: true,
    quiet_start: '00:00', quiet_end: '00:00', expires: 1, visible_required: true };
  expect(await handle(value)).toBe(true);
  expect(await handle(value)).toBe(true);
  expect(display).toHaveBeenCalledTimes(2);
  expect(display.mock.calls[0][1]).toMatchObject({body:'Open LifeOS to view your notification center.',tag:'lifeos-attention',renotify:false});
  expect(display.mock.calls[1][1]).toEqual(display.mock.calls[0][1]);
});

it('displays bounded descriptive copy but never stale Apple details', () => {
  const context = vm.createContext({ self: { addEventListener: vi.fn() }, Date, Intl, URL });
  vm.runInContext(readFileSync('public/sw.js', 'utf8'), context);
  const policy = vm.runInContext('pushNotice', context) as (value: unknown, now: number) => { title: string; options: { body: string } } | null;
  const now = Date.parse('2026-11-03T08:00:00Z');
  const value = { id: 'c'.repeat(64), language: 'he', zone: 'Asia/Jerusalem', quiet_enabled: false, quiet_start: '22:00', quiet_end: '07:00', expires: now / 1000 + 300, notice_title: 'נוספה מטלה', notice_body: 'תרגיל 2' };
  expect(policy(value, now)?.title).toBe('נוספה מטלה');
  expect(policy(value, now)?.options.body).toBe('תרגיל 2');
  expect(policy({ ...value, notice_body: undefined }, now)).toBeNull();
  expect(policy({ ...value, notice_title: 'x'.repeat(101) }, now)).toBeNull();
  expect(policy({ ...value, notice_body: '\u202eunsafe' }, now)).toBeNull();
  expect(policy({ ...value, visible_required: true, expires: 1 }, now)?.title).toBe('LifeOS');
});
