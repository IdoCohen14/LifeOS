"use client";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { BROWSER_NOTICE_LOCK, setBrowserNotices } from "@/lib/browser-notifications";
import { BROWSER_CHANNEL_CHANGE, PUSH_DEVICE_KEY, pushKeyBytes, pushRegistration, samePushKey, pushSupport } from "@/lib/web-push";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Config = { configured: boolean; contact: string; public_key: string | null; revision: number };
type Device = { id: string; enabled: boolean; last_error: string | null };
function support() { return pushSupport({secure: window.isSecureContext, notifications: 'Notification' in window,
  push: 'PushManager' in window, serviceWorker: 'serviceWorker' in navigator, locks: 'locks' in navigator,
  standalone: (navigator as Navigator & {standalone?: boolean}).standalone,
  displayStandalone: window.matchMedia?.('(display-mode: standalone)').matches ?? false}); }
export function WebPushSettings({ csrf, settings, t, onUnauthorized }: { csrf: string; settings: Settings; t: Translate; onUnauthorized?: () => void }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [device, setDevice] = useState<Device | null>(null);
  const [devices, setDevices] = useState<(Device & { registered_at: number })[]>([]);
  const [removing, setRemoving] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized?.();
    setError(error instanceof ApiError && error.status === 409 ? "changed" : error instanceof ApiError && error.status === 422 ? "unsupported_provider" : error instanceof ApiError && error.status === 429 ? "limit" : "unavailable");
  }
  function changed() { window.dispatchEvent(new Event(BROWSER_CHANNEL_CHANGE)); }
  async function load() {
    setBusy(true); setError(""); setNotice("");
    try {
      setConfig(await api<Config>('push/config'));
      setDevices(await api<(Device & { registered_at: number })[]>('push/subscriptions'));
      setRemoving(null);
      if (support() === 'ready') {
        await navigator.locks.request(BROWSER_NOTICE_LOCK, async () => {
          const registration = await pushRegistration();
          const subscription = await registration.pushManager.getSubscription();
          const value = subscription ? await api<Device | null>('push/lookup', 'POST', { endpoint: subscription.endpoint }, csrf) : null;
          setDevice(value);
          if (value?.enabled) localStorage.setItem(PUSH_DEVICE_KEY, value.id); else localStorage.removeItem(PUSH_DEVICE_KEY);
          changed();
        });
      }
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function configure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!config) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      setConfig(await api<Config>('push/config', 'PUT', { contact: String(form.get('contact')).trim(), revision: config.revision }, csrf));
      setNotice(t("ההגדרה נשמרה. הפעלת Push בדפדפן דורשת בחירה נפרדת.", "Setup saved. Enabling Push in this browser is a separate choice."));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function enable() {
    if (!config?.public_key || busy) return;
    const available = support();
    if (available !== 'ready') { setError(available === 'home_screen' ? 'home_screen' : 'unavailable'); return; }
    // Permission request occurs immediately within this explicit click.
    setBusy(true); setError(""); setNotice("");
    let created: PushSubscription | null = null;
    let saved: Device | null = null;
    try {
      if (await Notification.requestPermission() !== 'granted') { setError('permission'); return; }
      await navigator.locks.request(BROWSER_NOTICE_LOCK, async () => {
        const registration = await pushRegistration();
        let subscription = await registration.pushManager.getSubscription();
        if (subscription && !samePushKey(subscription.options.applicationServerKey, config.public_key!)) {
          if (device) await api(`push/subscriptions/${device.id}`, 'DELETE', undefined, csrf);
          if (!await subscription.unsubscribe()) throw Error('unsubscribe_failed');
          subscription = null;
        }
        if (!subscription) {
          subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: pushKeyBytes(config.public_key!) });
          created = subscription;
        }
        saved = await api<Device>('push/subscriptions', 'POST', subscription.toJSON(), csrf);
        setBrowserNotices(localStorage, false);
        localStorage.setItem(PUSH_DEVICE_KEY, saved.id);
        setDevice(saved);
        setDevices(previous => [...previous.filter(value => value.id !== saved!.id), { ...saved!, registered_at: Date.now()/1000 }]);
        changed();
      });
      setNotice(t("Push הופעל בדפדפן הזה. הערוץ שפועל רק כשהדף פתוח כובה כדי למנוע שליחה כפולה.", "Push enabled in this browser. The open-page channel was turned off to avoid double delivery."));
    } catch (error) {
      // Registration errors must not leave an unknown active server device behind.
      if (saved) { try { await api(`push/subscriptions/${(saved as Device).id}`, 'DELETE', undefined, csrf); } catch {} }
      if (created) { try { await (created as PushSubscription).unsubscribe(); } catch {} }
      failed(error);
    } finally { setBusy(false); }
  }
  async function disable() {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await navigator.locks.request(BROWSER_NOTICE_LOCK, async () => {
        if (device) await api(`push/subscriptions/${device.id}`, 'DELETE', undefined, csrf);
        localStorage.removeItem(PUSH_DEVICE_KEY); setDevices(previous => previous.filter(value => value.id !== device?.id)); setDevice(null); changed();
        const subscription = await (await pushRegistration()).pushManager.getSubscription();
        if (subscription && !await subscription.unsubscribe()) throw Error('unsubscribe_failed');
      });
      setNotice(t("Push כובה. הודעה שכבר נשלחה עשויה עדיין להגיע. הרשאת הדפדפן עצמה מנוהלת בהגדרות האתר.", "Push turned off. An in-flight notice may still arrive. Manage browser permission itself in site settings."));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function removeOther() {
    if (!removing || busy) return;
    if (removing === device?.id) { await disable(); setRemoving(null); return; }
    setBusy(true); setError(""); setNotice("");
    try { await api(`push/subscriptions/${removing}`, 'DELETE', undefined, csrf); setDevices(previous => previous.filter(value => value.id !== removing)); setRemoving(null); setNotice(t("המנוי הוסר מהשרת. הדפדפן האחר יצטרך להירשם מחדש כדי לקבל Push.", "Server subscription removed. That browser must register again to receive Push.")); }
    catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  return <details className="notification-preferences" onToggle={event => { if (event.currentTarget.open && !config && !busy) void load(); }}>
    <summary>{t("Push כשהטאב סגור", "Push while the tab is closed")}</summary>
    <p className="field-help">{t("כבוי עד הפעלה מפורשת. משתמש בשירות ההתראות של הדפדפן ושולח רק טקסט כללי של LifeOS. המחשב שמארח את האפליקציה חייב לפעול, וגם הדפדפן והמערכת צריכים לתמוך בקבלה ברקע. אין הבטחת מסירה או תזכורת חירום.", "Off until explicitly enabled. Uses your browser's Push service with generic LifeOS text only. The hosting computer must run, and browser/OS background delivery must be supported. Delivery is not guaranteed; this is not an emergency alarm.")}</p>
    <p className="field-help">{t("נתמכים יעדי Chrome/Firefox ו־Apple מאושרים. באייפון נדרשת פתיחה מהאייקון במסך הבית. הרשאת טלפון דורשת גישה מאובטחת לאתר; localhost במחשב אינו כתובת לטלפון. שעות שקטות וקטגוריות ההתראות חלות גם כאן.", "Supports validated Chrome/Firefox and Apple service endpoints. On iPhone, open the app from its Home Screen icon. Phone access needs a secure reachable site; desktop localhost is not a phone address. Quiet hours and notification categories apply.")}</p>
    <details className="field-help"><summary>{t("הפעלת התראות ב־iPhone", "Enable notifications on iPhone")}</summary>
      <ol><li>{t("נדרשת iOS 16.4 ומעלה. פתחו את הכתובת הפרטית של LifeOS ב־Safari כשהחיבור הפרטי פעיל.", "Requires iOS 16.4 or later. Open your private LifeOS address in Safari while the private connection is active.")}</li>
        <li>{t("בתפריט השיתוף בחרו הוספה למסך הבית. לאחר ההוספה, פתחו את LifeOS מהאייקון החדש.", "In the Share menu, choose Add to Home Screen. Then open LifeOS from the new icon.")}</li>
        <li>{t("חזרו לכאן, לחצו על הפעלת Push ואשרו את בקשת ההתראות של iPhone. לא תישלח בקשת הרשאה בלי לחיצה שלכם.", "Return here, tap Enable Push and allow the iPhone notification request. Permission is requested only after your tap.")}</li></ol>
      <p>{t("באייפון כל הודעה שנמסרה חייבת להופיע. שעות שקטות נבדקות במחשב לפני השליחה; השתקה במכשיר עצמו מנוהלת באמצעות מצב ריכוז. הודעה שנמסרה באיחור לא תסונן במכשיר. השליחה מבקשת לא לשמור תור למכשיר שאינו מחובר.", "On iPhone, every delivered push must be displayed. Quiet hours are checked on the PC before sending; use Focus for device-side silencing. A delivered message is not filtered out if it arrives late. Apple is asked not to queue messages for offline devices.")}</p>
    </details>
    {config && <>
      <details><summary>{t("הגדרת שולח במחשב", "Sender setup on this computer")}</summary><form key={config.revision} className="form-stack" onSubmit={configure}>
        <label>{t("דוא״ל קשר למפעיל Push", "Push operator contact email")}<input name="contact" type="email" maxLength={254} required defaultValue={config.contact} disabled={busy} autoComplete="email" /></label>
        <p className="field-help">{t("כתובת קשר לצורך זיהוי השולח (VAPID), ונמסרת לספק ההתראות של הדפדפן. אין חיבור לתיבת דואר ואין שליחת מייל. ההגדרה לבדה אינה רושמת את הדפדפן.", "A sender contact for VAPID, shared with the browser Push provider. No mailbox connection or email is sent. Setup alone does not subscribe this browser.")}</p>
        <Button type="submit" disabled={busy}>{t("שמירת הגדרת שולח Push", "Save Push sender setup")}</Button>
      </form></details>
      <p className="field-help">{device?.enabled ? t("Push פעיל בדפדפן הזה", "Push active in this browser") : t("Push כבוי בדפדפן הזה", "Push off in this browser")}</p>
      {device?.last_error && <p className="field-help" role="status">{t("השליחה האחרונה לא אושרה. רעננו ובדקו הרשאה או הפעילו מחדש. ההתראות בתוך האפליקציה נשארות זמינות.", "The last send was not accepted. Refresh and check permission or re-enable. In-app notifications remain available.")}</p>}
      <div className="google-actions">
        <Button size="small" disabled={busy || !config.configured} onClick={() => void (device?.enabled ? disable() : enable())}>{device?.enabled ? t("כיבוי Push בדפדפן הזה", "Turn off Push in this browser") : t("הפעלת Push בדפדפן הזה", "Enable Push in this browser")}</Button>
        <Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{t("רענון מצב Push", "Refresh Push status")}</Button>
      </div>
    </>}
    {devices.length > 0 && <details><summary>{t("ניהול דפדפנים רשומים", "Manage registered browsers")}</summary><ul className="recovery-list">{devices.map((value, i) => <li key={value.id}><span>{value.id === device?.id ? t("הדפדפן הזה", "This browser") : t("דפדפן נוסף", "Another browser")}<small>{t("נרשם/חודש: ", "Registered/renewed: ")}{new Intl.DateTimeFormat(settings.language, { dateStyle: 'short', timeStyle: 'short', timeZone: settings.timezone }).format(new Date(value.registered_at*1000))}</small></span><Button size="small" variant="ghost" disabled={busy} onClick={() => setRemoving(value.id)}>{t(`הסרת מנוי ${i+1}`, `Remove subscription ${i+1}`)}</Button></li>)}</ul>{removing && <div className="history-clear-confirm"><p>{t("להפסיק לשלוח Push למנוי הזה? ההתראות בתוך האפליקציה לא ישתנו.", "Stop sending Push to this subscription? In-app notifications stay unchanged.")}</p><Button size="small" disabled={busy} onClick={() => void removeOther()}>{t("אישור הסרת מנוי Push", "Confirm Push subscription removal")}</Button><Button size="small" variant="ghost" disabled={busy} onClick={() => setRemoving(null)}>{t("ביטול", "Cancel")}</Button></div>}</details>}
    {!config && <Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{t("טעינת הגדרות Push", "Load Push settings")}</Button>}
    {error && <p role="alert">{error === 'home_screen' ? t('באייפון יש להוסיף את LifeOS למסך הבית ולפתוח מהאייקון לפני הפעלת התראות.', 'On iPhone, add LifeOS to the Home Screen and open its icon before enabling notifications.') : error === 'permission' ? t("הרשאת ההתראות לא ניתנה. אפשר לשנות אותה בהגדרות האתר בדפדפן.", "Notification permission was not granted. Change it in browser site settings.") : error === 'unsupported_provider' ? t("המנוי או ספק ההתראות אינם נתמכים. אפשר להמשיך עם מרכז ההתראות או ערוץ הדף הפתוח.", "This subscription/provider is unsupported. Use the in-app center or open-page channel.") : error === 'changed' ? t("הגדרת השולח השתנתה. רעננו ובדקו אותה לפני שמירה.", "Sender setup changed. Refresh and review before saving.") : error === 'limit' ? t("כבר רשומים חמישה דפדפנים. כבו מנוי ישן לפני הוספת דפדפן נוסף.", "Five browsers are already registered. Turn off an old subscription before adding another.") : t("Push לא זמין כרגע בדפדפן או בחיבור הזה. רעננו או השתמשו במרכז ההתראות; לא נשלחה התראת בדיקה.", "Push is unavailable in this browser or connection. Refresh or use the in-app center; no test notice was sent.")}</p>}
    <p role="status" className="field-help">{busy ? t("טוען…", "Loading…") : notice}</p>
  </details>;
}
