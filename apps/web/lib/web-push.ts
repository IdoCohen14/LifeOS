export const PUSH_DEVICE_KEY = 'lifeos.push.device.v1';
export const BROWSER_CHANNEL_CHANGE = 'lifeos-browser-notices-change';
export type PushSupport = 'ready' | 'insecure' | 'home_screen' | 'unsupported';
export function pushSupport(value: {secure: boolean; notifications: boolean; push: boolean; serviceWorker: boolean; locks: boolean; standalone?: boolean; displayStandalone: boolean}): PushSupport {
  if (!value.secure) return 'insecure';
  // iOS exposes navigator.standalone; use it for Home Screen guidance, not UA gating.
  if (value.standalone === false && !value.displayStandalone) return 'home_screen';
  return value.notifications && value.push && value.serviceWorker && value.locks ? 'ready' : 'unsupported';
}
export function pushKeyBytes(value: string): ArrayBuffer {
  if (!/^[A-Za-z0-9_-]{87}$/.test(value)) throw Error('push_key_invalid');
  const decoded = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '=');
  if (decoded.length !== 65 || decoded.charCodeAt(0) !== 4) throw Error('push_key_invalid');
  const bytes = new Uint8Array(65);
  for (let i = 0; i < 65; i++) bytes[i] = decoded.charCodeAt(i);
  return bytes.buffer;
}
export function samePushKey(value: ArrayBuffer | null, key: string) {
  if (!value) return false;
  const expected = new Uint8Array(pushKeyBytes(key)), actual = new Uint8Array(value);
  return actual.length === expected.length && actual.every((value, i) => value === expected[i]);
}
export async function pushRegistration() {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([navigator.serviceWorker.ready, new Promise<never>((_, reject) => { timeout = setTimeout(() => reject(Error('worker_unavailable')), 5000); })]);
  } finally { clearTimeout(timeout); }
}
