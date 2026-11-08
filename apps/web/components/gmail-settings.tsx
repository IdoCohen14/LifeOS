"use client";

import { useCallback, useEffect, useState } from "react";
import { Mail, RefreshCw, Unplug } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export type GmailStatus = {
  configured: boolean; connected: boolean; state: string; error: string | null;
  syncing: boolean; stale: boolean; last_success: number | null;
  revision?: number;
  automatic_calendar?: boolean;
};
export function GmailSettings({ csrf, settings, t, onUnauthorized }: {
  csrf: string; settings: Settings; t: Translate; onUnauthorized: () => void;
}) {
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [disconnecting, setDisconnecting] = useState(false);
  const load = useCallback(async () => {
    const state = await api<GmailStatus>("integrations/gmail/status");
    setStatus(state); setError("");
  }, []);
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError ? error.message : "unavailable");
  }, [onUnauthorized]);
  useEffect(() => { void (async () => { try { await load(); } catch (error) { failed(error); } })(); }, [load, failed, csrf]);
  useEffect(() => {
    if (!status?.connected) return;
    const update = () => { void load().catch(failed); };
    const timer = window.setInterval(update, 10000);
    window.addEventListener("focus", update);
    return () => { clearInterval(timer); window.removeEventListener("focus", update); };
  }, [status?.connected, load, failed]);
  async function act(path: string) {
    setBusy(true); setError("");
    try {
      if (path === "authorize") {
        const result = await api<{ authorization_url: string }>("integrations/gmail/authorize", "POST", undefined, csrf);
        window.location.assign(result.authorization_url);
      } else {
        await api(`integrations/gmail/${path}${path === "sync" ? "?background=true" : ""}`, "POST", undefined, csrf);
        setNotice(path === "sync" ? t("בקשת הסנכרון נשלחה. ההודעות יתעדכנו אוטומטית בסיום.", "Sync requested. Messages will refresh automatically when it finishes.") : "");
        await load();
      }
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  return <div className="google-settings gmail-settings">
    <div className="google-heading">
      <Mail size={25} aria-hidden="true" />
      <div><h3 translate="no">Gmail</h3><p>{t("קריאה בלבד · ללא שליחה, מחיקה או שינוי מצב הקריאה", "Read-only · No sending, deleting or marking as read")}</p></div>
      <span className="subtle-badge">{status?.syncing ? t("מסנכרן…", "Syncing…") : status?.state === "expired" ? t("נדרש אישור מחדש", "Reauthorization required") : status?.connected ? t("מחובר", "Connected") : t("לא מחובר", "Disconnected")}</span>
    </div>
    {status && !status.configured && <p>{t("מנהל האתר עדיין לא הגדיר חיבור ל־Google.", "The administrator has not configured Google yet.")}</p>}
    {status?.configured && <div className="google-actions">
      <Button disabled={busy || status.syncing} onClick={() => void act("authorize")}>{status.connected ? t("אישור Gmail מחדש", "Reconnect Gmail") : t("חיבור Gmail", "Connect Gmail")}</Button>
      {(status.connected || status.state === "expired") && <>
        <Button variant="secondary" disabled={busy || status.syncing || !status.connected} onClick={() => void act("sync")}><RefreshCw size={15} />{t("סנכרון Gmail עכשיו", "Sync Gmail now")}</Button>
        <Button variant="ghost" disabled={busy || status.syncing} onClick={() => setDisconnecting(true)}><Unplug size={15} />{t("ניתוק Gmail", "Disconnect Gmail")}</Button>
      </>}
    </div>}
    <p className="field-help">{t("הודעות על לימודים, עבודה ומשרות והתכתבות אישית מתוך 50 ההודעות האחרונות. סינון אוטומטי לפי כללים עשוי לטעות. סנכרון בערך כל 10 דקות כשהמערכת פועלת. פתיחת הודעה מתבצעת ב־Gmail.", "Study, work, jobs and personal correspondence from the latest 50 Inbox messages. Rule-based filtering may make mistakes. Syncs about every 10 minutes while running. Messages open in Gmail.")}</p>
    {notice && <p role="status">{notice}</p>}
    {status?.last_success && <p className="field-help">{t("סנכרון אחרון: ", "Last synced: ")}{new Intl.DateTimeFormat(settings.language === "he" ? "he-IL" : "en-GB", { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(status.last_success * 1000))}</p>}
    {(error || status?.error || status?.stale) && <div role="alert" className="error-message">{status?.state === "expired" ? t("הגישה ל־Gmail פגה או בוטלה. יש לאשר מחדש.", "Gmail access expired or was revoked. Connect again.") : (error || status?.error) === "api_not_enabled" ? t("יש להפעיל את Gmail API בפרויקט Google Cloud.", "Enable Gmail API in the Google Cloud project.") : t("לא ניתן לעדכן כעת. הודעות שמורות עשויות להיות לא מעודכנות.", "Unable to refresh now. Cached messages may be outdated.")}</div>}
    {status?.connected && !status.last_success && <p>{t("החשבון מחובר. לחצו על סנכרון Gmail עכשיו לטעינה ראשונה.", "Account connected. Sync Gmail now to load messages.")}</p>}
    <p className="field-help">{t("המיילים מופיעים אחד־אחד ב'היום שלי'.", "Messages appear one at a time in My Day.")}</p>
    {status?.connected&&<label className="checkbox-row"><input type="checkbox" checked={status.automatic_calendar??false} disabled={busy} onChange={async e=>{const enabled=e.target.checked;setBusy(true);try{setStatus(await api<GmailStatus>("integrations/gmail/calendar","POST",{enabled},csrf));}catch(error){failed(error);}finally{setBusy(false);}}}/>{t("הוספת מועדים מפורשים ממיילים חשובים ליומן באופן אוטומטי","Automatically add explicit dates from important mail to my calendar")}</label>}
    <p className="field-help">{t("זיהוי שמרני של תאריך מפורש: מועד הגשה ביום מסוים או פגישה עם טווח שעות ברור. הודעות עמומות לא יוסיפו אירוע. האירועים נשמרים ב־LifeOS בלבד.","Conservative recognition of an explicit deadline date or meeting time range. Ambiguous messages do not create events. Events are stored only in LifeOS.")}</p>
    <Modal open={disconnecting} onClose={() => setDisconnecting(false)} closeLabel={t("סגירה", "Close")} description={t("ניתוק מקומי בלבד", "Local disconnect only")} title={t("ניתוק Gmail?", "Disconnect Gmail?")}>
      <p>{t("ההודעות השמורות והאישור יוסרו מ־LifeOS בלבד. ההודעות ב־Gmail וחיבור היומן יישארו כפי שהם.", "Removes only the local Gmail cache and credentials. Gmail messages and the Calendar connection remain unchanged.")}</p>
      <Button disabled={busy} onClick={async () => { await act("disconnect"); setDisconnecting(false); }}>{t("ניתוק Gmail", "Disconnect Gmail")}</Button>
    </Modal>
  </div>;
}
