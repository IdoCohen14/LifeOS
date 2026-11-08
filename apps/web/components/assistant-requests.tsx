"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { TrackedRequest } from "@/lib/assistant-requests";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export function AssistantRequests({ csrf, revision, settings, t, onOpen, onChanged, onUnauthorized, hideWhenEmpty = false }: {
  hideWhenEmpty?: boolean;
  csrf: string; revision: number; settings: Settings; t: Translate;
  onOpen: (item: TrackedRequest) => void; onChanged: () => Promise<void>; onUnauthorized: () => void;
}) {
  const [items, setItems] = useState<TrackedRequest[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<TrackedRequest | null>(null);
  const [completed, setCompleted] = useState(false);
  const load = useCallback(async () => {
    try { setItems((await api<{items: TrackedRequest[]}>("assistant/requests")).items); setError(""); }
    catch (error) { if (error instanceof ApiError && error.status === 401) onUnauthorized(); setError(t("הבקשות לא נטענו. נסו לרענן.", "Requests could not load. Try refreshing.")); }
  }, [onUnauthorized, t]);
  useEffect(() => {
    let active = true;
    api<{items: TrackedRequest[]}>("assistant/requests").then(data => {
      if (active) { setItems(data.items); setError(""); }
    }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(t("הבקשות לא נטענו. נסו לרענן.", "Requests could not load. Try refreshing."));
    });
    return () => { active = false; };
  }, [revision, onUnauthorized, t]);
  async function change(item: TrackedRequest, values: object, remove = false) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await api(`assistant/requests/${item.id}`, remove ? "DELETE" : "PATCH", { version: item.version, ...values }, csrf);
      setRemoving(null); await load(); await onChanged();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(t("השינוי לא הושלם או שהבקשה השתנתה. רעננו לפני ניסיון נוסף.", "The change did not complete or the request changed. Refresh before retrying."));
    } finally { setBusy(false); }
  }
  const labels = { waiting_user: t("מחכה לצעד שלך", "Your next step"), waiting_approval: t("הצעה מחכה לאישור בשיחה", "Proposal awaiting confirmation in chat"), waiting_source: t("מחכה לעדכון מהמקור", "Waiting for source information"), done: t("טופלה", "Handled") };
  const active = items.filter(item => item.status !== "done");
  const rows = completed ? items : active;
  const format = (instant: number) => new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(instant * 1000));
  if (hideWhenEmpty && !items.length && !error) return null;
  return <details className="panel tracked-requests"><summary>{t("הבקשות שלי", "My requests")} <span className="subtle-badge">{active.length}</span></summary>
    <p className="field-help">{t("מעקב אחר הצעד הבא. ״טופלה״ מסיים את המעקב בלבד. השיחה נשמרת רק אם הפעלת היסטוריה.", "Track your next step. Handled closes tracking only. Chat text is saved only with history enabled.")}</p>
    <div className="google-actions"><Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{t("רענון", "Refresh")}</Button>
      {!!items.some(item => item.status === "done") && <Button size="small" variant="ghost" onClick={() => setCompleted(!completed)}>{completed ? t("רק פעילות", "Active only") : t("גם בקשות שטופלו", "Include handled requests")}</Button>}</div>
    {!rows.length && <p className="muted">{t("אין בקשות פתוחות. אפשר להתחיל מעדכון בכרטיס שמעל.", "No open requests. Start from an update above.")}</p>}
    {rows.map(item => <article className="tracked-request" key={item.id}>
      <div><h3 dir="auto">{item.title}{item.course_name && ` · ${item.course_name}`}</h3><p className="field-help">{labels[item.status]}{item.followup_at ? ` · ${t("חזרה לבקשה", "Follow up")}: ${format(item.followup_at)}` : ""}</p></div>
      <div className="google-actions">
        {item.status !== "done" && <><Button size="small" disabled={busy} onClick={() => onOpen(item)}>{t("המשך עם העוזר", "Continue with assistant")}</Button>
          <Button size="small" variant="secondary" disabled={busy} onClick={() => void change(item, { followup_minutes: 60 })}>{t("לחזור בעוד שעה", "Follow up in an hour")}</Button>
          <Button size="small" variant="ghost" disabled={busy} onClick={() => void change(item, { followup_minutes: 1440 })}>{t("בעוד 24 שעות", "In 24 hours")}</Button>
          {item.followup_at && <Button size="small" variant="ghost" disabled={busy} onClick={() => void change(item, { followup_minutes: 0 })}>{t("ביטול התזכורת", "Cancel follow-up")}</Button>}
          <Button size="small" variant="ghost" disabled={busy} onClick={() => void change(item, { status: item.status === "waiting_source" ? "waiting_user" : "waiting_source" })}>{item.status === "waiting_source" ? t("המקור זמין", "Source available") : t("ממתין למקור", "Wait for source")}</Button></>}
        <Button size="small" variant="ghost" disabled={busy} onClick={() => void change(item, { status: item.status === "done" ? "waiting_user" : "done" })}>{item.status === "done" ? t("פתיחה מחדש", "Reopen") : t("טופלה", "Handled")}</Button>
        <Button size="small" variant="ghost" disabled={busy} onClick={() => setRemoving(item)}>{t("הסרת המעקב", "Remove tracking")}</Button>
      </div>
    </article>)}
    {error && <p className="error-message" role="alert">{error}</p>}
    {removing && <Modal open onClose={() => { if (!busy) setRemoving(null); }} title={t("להסיר את המעקב?", "Remove tracking?")} description={t("רק רישום הבקשה יוסר. המטלה, האירוע והעדכון המקורי לא ישתנו.", "Only this request record is removed. Its task, event and source update stay unchanged.")} closeLabel={t("סגירה", "Close")}>
      <p dir="auto">{removing.title}</p><Button variant="danger" disabled={busy} onClick={() => void change(removing, {}, true)}>{t("אישור הסרת המעקב", "Confirm removal")}</Button>
    </Modal>}
  </details>;
}
