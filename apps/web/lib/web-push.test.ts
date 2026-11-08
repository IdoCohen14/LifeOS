import { expect, it } from 'vitest';
import { pushKeyBytes, samePushKey, pushSupport } from './web-push';
it('decodes only the configured P-256 public key and compares subscription options', () => {
  const raw = new Uint8Array(65); raw[0] = 4;
  const key = btoa(String.fromCharCode(...raw)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const buffer = pushKeyBytes(key);
  expect(new Uint8Array(buffer)).toEqual(raw);
  expect(samePushKey(buffer, key)).toBe(true);
  raw[1] = 9;
  expect(samePushKey(raw.buffer, key)).toBe(false);
  expect(() => pushKeyBytes('invalid')).toThrow();
});
it('guides iPhone Safari tabs to Home Screen without requesting permission', () => {
  const ready = {secure:true,notifications:true,push:true,serviceWorker:true,locks:true,displayStandalone:false};
  expect(pushSupport({...ready,standalone:false})).toBe('home_screen');
  expect(pushSupport({...ready,standalone:true})).toBe('ready');
  expect(pushSupport({...ready,standalone:false,displayStandalone:true})).toBe('ready');
  expect(pushSupport(ready)).toBe('ready');
  expect(pushSupport({...ready,secure:false})).toBe('insecure');
  expect(pushSupport({...ready,push:false})).toBe('unsupported');
});
