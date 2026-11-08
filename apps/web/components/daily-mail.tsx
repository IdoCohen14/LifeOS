"use client";

import { useCallback, useEffect, useState } from "react";
import { Mail, Undo2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Translate } from "@/lib/types";
import type { GmailStatus } from "./gmail-settings";
import { CachedMailSearch } from "./cached-mail-search";
import { Button } from "./ui/button";

type Message = { id: string; subject: string; sender: string; snippet: string; source_url: string; cached_thread_count?: number; connection_revision?: number };

export function DailyMail({ csrf, t, onUnauthorized, onConnect, onCreateTask, onCreateEvent }: {
  csrf: string; t: Translate; onUnauthorized: () => void; onConnect: () => void;
  onCreateTask: (draft:{title:string;notes:string}) => void;
  onCreateEvent?: (draft:{title:string;notes:string}) => void;
}) {
  const [queue, setQueue] = useState<Message[] | null>(null);
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastReviewed, setLastReviewed] = useState<{id: string; revision?: number} | null>(null);
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(true);
  }, [onUnauthorized]);
  const load = useCallback(async () => {
    const [messages, state] = await Promise.all([
      api<Message[]>("integrations/gmail/queue"), api<GmailStatus>("integrations/gmail/status"),
    ]);
    setQueue(messages); setStatus(state); setError(false);
    setLastReviewed(previous => previous?.revision !== undefined && state.revision !== undefined
      && previous.revision !== state.revision ? null : previous);
  }, []);
  useEffect(() => {
    void (async () => { try { await load(); } catch (error) { failed(error); } })();
    const update = () => { void load().catch(failed); };
    const timer = window.setInterval(update, 60000);
    window.addEventListener("focus", update);
    return () => { clearInterval(timer); window.removeEventListener("focus", update); };
  }, [load, failed, csrf]);
  useEffect(() => {
    if(window.location.hash !== "#my-mail") return;
    const frame=requestAnimationFrame(()=>document.getElementById("my-mail")?.scrollIntoView({block:"start"}));
    return ()=>cancelAnimationFrame(frame);
  }, []);
  async function review(all = false) {
    if (busy || !queue?.length) return;
    setBusy(true); setError(false);
    try {
      const revision = queue[0].connection_revision;
      setQueue(await api<Message[]>("integrations/gmail/review", "POST", { ...(all ? { all: true } : { id: queue[0].id }), ...(revision !== undefined ? { revision } : {}) }, csrf));
      setLastReviewed(all ? null : {id: queue[0].id, revision});
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function undo() {
    if (busy || !lastReviewed) return;
    setBusy(true); setError(false);
    try {
      setQueue(await api<Message[]>("integrations/gmail/review", "POST", { id: lastReviewed.id, undo: true, ...(lastReviewed.revision !== undefined ? { revision: lastReviewed.revision } : {}) }, csrf));
      setLastReviewed(null);
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  const message = queue?.[0];
  return <section id="my-mail" tabIndex={-1} className="panel daily-mail" aria-label={t("המיילים שלי", "My mail")}>
    <div className="panel-heading"><div className="heading-with-icon"><Mail size={20} aria-hidden="true" /><h2>{t("המיילים שלי", "My mail")}</h2></div>
      {!!queue?.length && <Button variant="ghost" size="small" disabled={busy} onClick={() => void review(true)}>{t("סימון הכול כנקרא", "Mark all as read")}</Button>}
    </div>
    <details className="calm-mail-help"><summary>{t("על תיבת המיילים", "About this inbox")}</summary><p className="field-help">{t("לימודים, עבודה והתכתבות אישית · סימון כנקרא חל ב־LifeOS בלבד", "Study, work and personal mail · Read status applies only in LifeOS")}</p></details>
    {lastReviewed && <Button className="mail-undo" variant="ghost" size="small" disabled={busy} onClick={() => void undo()}><span className="mail-undo-icon" aria-hidden="true"><Undo2 size={17} strokeWidth={1.8} /></span>{t("החזר את המייל האחרון", "Restore last message")}</Button>}
    {(error || status?.error || status?.stale) && <div role="alert" className="error-message">{t("לא ניתן לעדכן כעת. המידע השמור עשוי להיות לא מעודכן.", "Unable to update. Cached mail may be outdated.")} <Button variant="ghost" size="small" onClick={() => void load().catch(failed)}>{t("ניסיון נוסף", "Retry")}</Button></div>}
    {queue === null && !error && <p role="status">{t("טוען מיילים…", "Loading mail…")}</p>}
    {status && !status.connected ? <Button variant="secondary" onClick={onConnect}>{t("חיבור Gmail בהגדרות", "Connect Gmail in settings")}</Button> : message ? <details className="gmail-message calm-mail-message" aria-live="polite" key={message.id}>
      <summary><span dir="auto">{message.subject || t("ללא נושא", "No subject")}</span><span className="calm-mail-open">{t("פתיחה", "Open")}</span></summary>
      <p className="field-help">{t(`נותרו ${queue?.length} מיילים חדשים`, `${queue?.length} new messages remaining`)}</p>
      <p dir="auto">{message.sender}</p>{(message.cached_thread_count??0)>1&&<p className="field-help">{t(`בשיחה הזו ${message.cached_thread_count} הודעות רלוונטיות בסנכרון הנוכחי, כולל הודעות שכבר נקראו או נבדקו.`,`This conversation has ${message.cached_thread_count} relevant messages in the current snapshot, including read or reviewed messages.`)}</p>}<p dir="auto">{message.snippet}</p>
      <div className="google-actions">
        {onCreateEvent&&<Button variant="ghost" disabled={busy} onClick={()=>onCreateEvent({title:(message.subject||t("אירוע חשוב ממייל","Important email event")).slice(0,240),notes:`${message.sender}\n${message.source_url}`})}>{t("הוספת מועד חשוב ליומן", "Add important date to calendar")}</Button>}
        <Button variant="ghost" disabled={busy} onClick={()=>onCreateTask({title:(message.subject||t("משימה ממייל","Task from email")).slice(0,240),notes:`${message.sender}\n${message.source_url}`})}>{t("יצירת משימה מהמייל", "Create task from email")}</Button>
        <a className="text-button" href={message.source_url} target="_blank" rel="noopener noreferrer" aria-disabled={busy} onClick={event => { if (busy) event.preventDefault(); else void review(); }}>{t("לענות ב־Gmail", "Reply in Gmail")}</a>
        <Button variant="secondary" disabled={busy} onClick={() => void review()}>{t("לא עכשיו — למייל הבא", "Not now — next message")}</Button>
      </div>
    </details> : queue !== null && status?.connected && <p role="status">{!status.last_success ? t("ממתין לסנכרון ראשון. אפשר לסנכרן בהגדרות.", "Waiting for the first sync. Sync from settings.") : t("אין מיילים חדשים", "No new mail")}</p>}
    {status?.connected&&<CachedMailSearch t={t} onUnauthorized={onUnauthorized}/>}
  </section>;
}
