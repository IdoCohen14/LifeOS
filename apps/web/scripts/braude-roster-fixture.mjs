/** Fixture-only export collector. No real portal origins, credentials or persistent profile. */
import { chromium } from '@playwright/test';
import { mkdir, mkdtemp, realpath, rm } from 'node:fs/promises';
import { isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const MAX_BYTES = 4 * 1024 * 1024;
const runtimeRoot = resolve(fileURLToPath(new URL('../../../.runtime/', import.meta.url)));
const inside = (root, path) => {
  const value = relative(root, path);
  return value !== '' && value !== '..' && !value.startsWith('..\\') && !value.startsWith('../') && !isAbsolute(value);
};
function fail(reason) { const error = new Error(reason); error.fixtureReason = reason; throw error; }
function errorReason(error) {
  return error.fixtureReason ?? (['TimeoutError', 'AbortError'].includes(error.name) ? 'source_timeout' : 'collection_failed');
}
function allowed(url, origin) {
  return url.origin === origin && !url.username && !url.password && !url.hash
    && ['/report', '/roster.xlsx'].includes(url.pathname);
}
function sourceMetadata(raw, accountId) {
  if (!raw || raw.length > 4096) fail('invalid_source');
  let value;
  try { value = JSON.parse(raw); } catch { fail('invalid_source'); }
  if (!value || value.account_id !== accountId) fail('account_mismatch');
  const keys = ['account_id','observed_at','year','semester','start_date','end_date','complete'];
  if (Object.keys(value).some(key => !keys.includes(key))
    || typeof value.observed_at !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value.observed_at)
    || !Number.isFinite(Date.parse(value.observed_at))
    || !Number.isInteger(value.year) || value.year < 2000 || value.year > 2100
    || !Number.isInteger(value.semester) || typeof value.complete !== 'boolean'
    || ['start_date','end_date'].some(key => value[key] !== null && (typeof value[key] !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value[key])))) fail('invalid_source');
  if (!value.complete) fail('incomplete_source');
  return value;
}

async function boundedGet(target) {
  const response = await fetch(target, {redirect:'manual', signal:AbortSignal.timeout(5000)});
  if (response.status >= 300 && response.status < 400) fail('redirect_rejected');
  if (!response.ok) fail(target.pathname === '/roster.xlsx' ? 'download_failed' : 'report_failed');
  if (response.headers.has('content-encoding') && response.headers.get('content-encoding') !== 'identity') fail('unsupported_encoding');
  if (Number(response.headers.get('content-length')) > MAX_BYTES) { await response.body?.cancel(); fail('response_too_large'); }
  const chunks = [];
  let size = 0;
  for await (const chunk of response.body) {
    size += chunk.length;
    if (size > MAX_BYTES) fail('response_too_large');
    chunks.push(chunk);
  }
  return {status:response.status, headers:response.headers, body:Buffer.concat(chunks)};
}

export async function collectFixture({url, accountId, runtimeDir}) {
  const unavailable = reason => ({fixture:true, status:reason === 'login_required' ? 'login_required' : 'needs_review', reason});
  let initial;
  try { initial = new URL(url); } catch { return unavailable('fixture_origin_required'); }
  if (initial.protocol !== 'http:' || initial.hostname !== '127.0.0.1' || !initial.port
    || initial.pathname !== '/report' || !allowed(initial, initial.origin)) return unavailable('fixture_origin_required');
  if (typeof accountId !== 'string' || !accountId || accountId.length > 128) return unavailable('account_mismatch');
  if (typeof runtimeDir !== 'string' || !inside(runtimeRoot, resolve(runtimeDir))) return unavailable('runtime_directory_required');
  let browser;
  let work;
  let verifiedRoot;
  let failure;
  try {
    verifiedRoot = await realpath(runtimeRoot);
    await mkdir(runtimeDir, {recursive:true});
    const directory = await realpath(runtimeDir);
    if (!inside(verifiedRoot, directory)) fail('runtime_directory_required');
    work = await mkdtemp(join(directory, 'capture-'));
    await mkdir(join(work, 'temp'));
    browser = await chromium.launch({channel:'msedge', headless:true, downloadsPath:work,
      env:{...process.env, TEMP:join(work, 'temp'), TMP:join(work, 'temp')}});
    const context = await browser.newContext({acceptDownloads:false, serviceWorkers:'block'});
    let requests = 0;
    await context.route('**/*', async route => {
      try {
        const request = route.request();
        const target = new URL(request.url());
        if (target.origin === initial.origin && target.pathname === '/favicon.ico' && request.method() === 'GET') {
          await route.fulfill({status:204}); return;
        }
        if (request.method() !== 'GET' || !allowed(target, initial.origin) || ++requests > 6) fail('unsafe_navigation');
        const response = await boundedGet(target);
        const headers = Object.fromEntries(['content-type','content-disposition'].flatMap(key => response.headers.has(key) ? [[key,response.headers.get(key)]] : []));
        await route.fulfill({status:response.status, headers, body:response.body});
      } catch (error) {
        failure ??= errorReason(error);
        await route.abort().catch(() => {});
      }
    });
    const page = await context.newPage();
    await page.goto(initial.href, {waitUntil:'domcontentloaded', timeout:10000});
    if (failure) fail(failure);
    if (await page.locator('[data-lifeos-login-required]').count()) fail('login_required');
    const sourceElement = page.locator('[data-lifeos-roster-source]');
    if (await sourceElement.count() !== 1 || await sourceElement.getAttribute('data-lifeos-fixture') !== 'true') fail('invalid_source');
    const source = sourceMetadata(await sourceElement.getAttribute('data-lifeos-roster-source'), accountId);
    const link = page.getByTestId('roster-export');
    if (await link.count() !== 1) fail('export_unavailable');
    const href = await link.getAttribute('href');
    const target = new URL(href || '', initial);
    if (!href || !allowed(target, initial.origin) || target.pathname !== '/roster.xlsx') fail('unsafe_export');
    // A native browser download can bypass page routing. Suppress that action;
    // read the observed allowlisted href with a redirect-free bounded stream.
    await link.evaluate(element => element.addEventListener('click', event => event.preventDefault(), {capture:true}));
    await link.click({timeout:3000});
    if (failure) fail(failure);
    const {body:bytes} = await boundedGet(target);
    if (failure) fail(failure);
    if (!bytes.length || bytes.length > MAX_BYTES) fail('response_too_large');
    return {fixture:true, status:'ready', reason:null, source, export_base64:bytes.toString('base64')};
  } catch (error) {
    return unavailable(failure || errorReason(error));
  } finally {
    await browser?.close();
    if (work) {
      // Verify the final absolute target before recursive fixture cleanup on Windows.
      const actual = await realpath(work);
      if (!verifiedRoot || !inside(verifiedRoot, actual)) throw new Error('Fixture cleanup boundary changed');
      await rm(actual, {recursive:true});
    }
  }
}
