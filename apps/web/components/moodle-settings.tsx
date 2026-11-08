"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { GraduationCap, RefreshCw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export type MoodleStatus = { configured: boolean; connected: boolean; state: string; error: string | null; syncing: boolean; stale: boolean; last_success: number | null; event_count: number };

export function MoodleSettings({ csrf, settings, t, onChanged, onUnauthorized }: {
  csrf: string; settings: Settings; t: Translate; onChanged: () => Promise<void>; onUnauthorized: () => void;
}) {
  const [status, setStatus] = useState<MoodleStatus | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disconnecting, setDisconnecting] = useState(false);
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError ? error.message : "unavailable");
  }, [onUnauthorized]);
  const load = useCallback(async () => { setStatus(await api<MoodleStatus>("integrations/moodle/status")); }, []);
  useEffect(() => {
    void (async () => { try { await load(); } catch (error) { failed(error); } })();
  }, [load, failed, csrf]);
  useEffect(() => {
    if (!status?.configured) return;
    const timer = setInterval(() => { void load().catch(failed); }, 10000);
    return () => clearInterval(timer);
  }, [status?.configured, load, failed]);
  async function act(path: string, body?: unknown) {
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`integrations/moodle/${path}`, "POST", body, csrf);
      if (path === "config") setUrl("");
      if (path.startsWith("sync")) setNotice(t("בקשת הסנכרון נשלחה. היומן יתעדכן אוטומטית.", "Sync requested. Your calendar will refresh automatically."));
      await load(); await onChanged();
      return true;
    } catch (error) { failed(error); return false; }
    finally { setBusy(false); }
  }
  return <div className="google-settings gmail-settings">
    <div className="google-heading"><GraduationCap size={25} aria-hidden="true" /><div><h3>Moodle · {t("בראודה", "Braude")}</h3><p>{t("יומן לקריאה בלבד · ללא שינוי מטלות באתר המכללה", "Read-only calendar · No changes to college assignments")}</p></div><span className="subtle-badge">{status?.syncing ? t("מסנכרן…", "Syncing…") : status?.connected ? t("מחובר", "Connected") : t("לא מחובר", "Disconnected")}</span></div>
    {status && !status.configured && <form className="google-config-form" onSubmit={async (event: FormEvent) => { event.preventDefault(); if (await act("config", { url })) await act("sync?background=true"); }}>
      <label>{t("קישור מנוי ליומן Moodle", "Moodle calendar subscription URL")}<input type="password" dir="ltr" value={url} onChange={event => setUrl(event.target.value)} autoComplete="off" spellCheck={false} maxLength={8192} required /></label>
      <Button type="submit" disabled={busy}>{t("חיבור Moodle", "Connect Moodle")}</Button>
    </form>}
    <p className="field-help">{t("הקישור האישי נשמר מוצפן ולא מוצג שוב. מיובאים רק האירועים בטווח הייצוא של Moodle, כולל מועדי מטלות שמופיעים ביומן. קבצים, ציונים ומצב הגשה אינם מיובאים.", "Your private link is encrypted and never displayed again. Imports only events within Moodle’s export range, including deadlines published in its calendar. Files, grades and submission status are not imported.")}</p>
    <p className="field-help">{t("סנכרון אוטומטי בערך כל 10 דקות כשהמערכת פועלת. שינוי או מחיקת אירוע ב־Moodle יתעדכנו אחרי סנכרון מוצלח.", "Syncs about every 10 minutes while running. Moodle event changes/deletions appear after a successful sync.")}</p>
    {status?.configured && <div className="google-actions"><Button variant="secondary" disabled={busy || status.syncing} onClick={() => void act("sync?background=true")}><RefreshCw size={15} />{t("סנכרון Moodle עכשיו", "Sync Moodle now")}</Button><Button variant="ghost" disabled={busy || status.syncing} onClick={() => setDisconnecting(true)}>{t("ניתוק Moodle", "Disconnect Moodle")}</Button></div>}
    {status?.last_success && <p className="field-help">{t("סנכרון אחרון: ", "Last synced: ")}{new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(status.last_success * 1000))}</p>}
    {status?.connected && status.event_count === 0 && !status.error && <p role="status">{t("החיבור תקין. כרגע אין אירועים ביומן Moodle בטווח שנבחר.", "Connected successfully. Moodle currently exports no events in the selected range.")}</p>}
    {status?.configured && !status.last_success && !status.error && <p role="status">{t("הקישור הוגדר. ממתין לסנכרון ראשון מוצלח.", "Subscription configured. Waiting for the first successful sync.")}</p>}
    {(error || status?.error || status?.stale) && <p role="alert" className="error-message">{error === "invalid_moodle_url" ? t("יש להזין קישור ייצוא תקין מיומן Moodle של בראודה.", "Enter a valid Braude Moodle calendar export link.") : t("לא ניתן לעדכן את היומן. בדקו שהקישור עדיין פעיל. האירועים השמורים עשויים להיות לא מעודכנים.", "Unable to update. Check that the subscription is still valid. Cached events may be outdated.")}</p>}
    {notice && <p role="status">{notice}</p>}
    <Modal open={disconnecting} onClose={() => setDisconnecting(false)} title={t("ניתוק Moodle?", "Disconnect Moodle?")} description={t("הסרה מקומית בלבד", "Local removal only")} closeLabel={t("סגירה", "Close")}><p>{t("הקישור והאירועים המיובאים יוסרו מ־LifeOS. המידע ב־Moodle ואירועים אישיים לא ישתנו.", "Removes the subscription and imported events from LifeOS. Moodle and personal events remain unchanged.")}</p><Button disabled={busy} onClick={async () => { if (await act("disconnect")) setDisconnecting(false); }}>{t("ניתוק Moodle", "Disconnect Moodle")}</Button></Modal>
  </div>;
}
