"use client";

import { useEffect, useState } from "react";
import { CalendarClock } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Suggestion = { id: string; task_id: string; title: string; course_name: string; due: string; start: string; end: string; duration: number; preferences_used: boolean; reason?: string; replacement?: {id:string;start:string;end:string} | null; snooze_minutes?:60|1440 };
type Feed = { suggestion: Suggestion | null; reason?: string; stale_sources: string[] };
type Proposal = { id: string; record: { title: string; start: string; end: string } };

export function PlanningNudge({ revision, csrf, settings, t, disabled, onChanged, onUnauthorized }: {
  revision: number; csrf: string; settings: Settings; t: Translate; disabled: boolean;
  onChanged: () => Promise<void>; onUnauthorized: () => void;
}) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [reviewed, setReviewed] = useState<Suggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    api<Feed>("planning/suggestions").then(value => { if (active) { setFeed(value); setError(""); } }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(t("הצעת הזמן לא נטענה. אפשר לרענן.", "Time suggestion could not load. Try refreshing."));
    });
    return () => { active = false; };
  }, [revision, reload, onUnauthorized, t]);
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(t("היומן, המקור או ההעדפות השתנו, או שהחיבור אינו זמין. רעננו את ההצעה לפני שמירה.", "The calendar, sources or preferences changed, or the connection is unavailable. Refresh the suggestion before saving."));
  }
  async function review(item: Suggestion) {
    if (busy || disabled) return;
    setBusy(true); setError("");
    try { const value = await api<{proposal: Proposal; request_tracking_warning?: boolean}>("planning/suggestions/propose", "POST", {id:item.id}, csrf); setProposal(value.proposal); setReviewed(item); if (value.request_tracking_warning) setError(t("ההצעה מוכנה, אך מעקב הבקשה לא התעדכן. אפשר לשמור את ההצעה ולרענן את המעקב בנפרד.", "The proposal is ready, but request tracking did not update. You can save it and refresh tracking separately.")); }
    catch (error) { failed(error); } finally { setBusy(false); }
  }
  async function snooze(item: Suggestion) {
    if(busy||disabled)return;setBusy(true);setError("");
    try{await api('planning/suggestions/dismiss','POST',{id:item.id},csrf);setFeed(null);setReload(value=>value+1);}catch(error){failed(error);}finally{setBusy(false);}
  }
  async function save() {
    if (!proposal || busy || disabled) return;
    setBusy(true); setError("");
    try {
      const saved = await api<{request_tracking_warning?: boolean}>("assistant/confirm", "POST", {id:proposal.id}, csrf);
      if (saved.request_tracking_warning) setReceipt(t("זמן העבודה נשמר, אך מעקב הבקשה דורש רענון.", "Work time was saved, but request tracking needs refresh."));
      setProposal(null); setReviewed(null); setFeed(null); setReload(value => value + 1);
      try { await onChanged(); } catch { setReceipt(t("זמן העבודה נשמר. רעננו את האתר כדי לראות אותו.", "Work time was saved. Refresh to see it.")); }
    } catch (error) { failed(error); } finally { setBusy(false); }
  }
  async function cancel() {
    if (!proposal || busy) return;
    setBusy(true);
    try { await api(`planning/proposals/${proposal.id}`, "DELETE", undefined, csrf); }
    catch (error) { failed(error); } finally { setProposal(null); setReviewed(null); setBusy(false); }
  }
  const item = feed?.suggestion;
  const show = item;
  const format = (value: string) => value.length === 10 ? value.split('-').reverse().join('/') : new Intl.DateTimeFormat(settings.language,{dateStyle:"short",timeStyle:"short",timeZone:settings.timezone}).format(new Date(value));
  if (!show && !error && !receipt && feed?.reason !== "stale_sources" && !proposal) return null;
  return <section className="panel planning-nudge" aria-label={t("הצעת זמן", "Time suggestion")}>
    {show && <><div className="heading-with-icon"><CalendarClock size={18} aria-hidden="true"/><h2>{item.replacement ? t("כדאי לעדכן את זמן העבודה", "Consider moving your work time") : t("אפשר לפנות לזה זמן", "Make room for this")}</h2></div>
      <p dir="auto"><strong>{item.title}{item.course_name ? ` · ${item.course_name}` : ""}</strong></p>
      <p>{format(item.start)} · {item.duration} {t("דקות", "minutes")}</p>
      <p className="field-help">{t("לקראת המועד", "Ahead of")}: {format(item.due)} · {item.replacement ? item.reason === "after_deadline" ? t("הזמן השמור מסתיים אחרי המועד הנוכחי. משך העבודה יישמר.", "The saved block ends after the current deadline. Its duration is preserved.") : t("הזמן השמור חופף לפריט ביומן. משך העבודה יישמר.", "The saved block overlaps another calendar entry. Its duration is preserved.") : item.preferences_used ? t("לפי העדפות התכנון שלך", "Using your planning preferences") : t("30 דקות כנקודת התחלה, לא אומדן למטלה", "30 minutes as a starting point, not an effort estimate")}</p>
      <div className="google-actions"><Button size="small" disabled={busy || disabled} onClick={() => void review(item)}>{t("בדיקת ההצעה", "Review suggestion")}</Button><Button size="small" variant="ghost" disabled={busy || disabled} onClick={() => void snooze(item)}>{item.snooze_minutes === 60 ? t("להסתיר לשעה", "Hide for an hour") : t("להסתיר ל־24 שעות", "Hide for 24 hours")}</Button></div></>}
    {feed?.reason === "stale_sources" && <p className="field-help">{t("נחכה למידע מעודכן לפני שנציע זמן ביומן.", "Waiting for current source information before suggesting calendar time.")}</p>}
    {error && <p className="error-message" role="alert">{error}</p>}
    {receipt && <p role="status">{receipt} <Button variant="ghost" size="small" onClick={() => setReceipt("")}>{t("הבנתי", "Got it")}</Button></p>}
    {(error || feed?.reason === "stale_sources") && <Button size="small" variant="ghost" disabled={busy} onClick={() => setReload(value => value + 1)}>{t("רענון ההצעה", "Refresh suggestion")}</Button>}
    {proposal && reviewed && <Modal open onClose={() => { if (!busy) void cancel(); }} title={reviewed.replacement ? t("להזיז את זמן העבודה?", "Move this work block?") : t("לקבוע זמן עבודה?", "Schedule work time?")} description={reviewed.replacement ? t("הזמן המקורי נשאר ביומן עד לאישור. רק משבצת העבודה המקומית תעודכן; המקורות והיומן ייבדקו שוב בשמירה.", "The original remains until confirmation. Only this linked local block changes; sources and calendar are checked again when saving.") : t("תתווסף משבצת עבודה ליומן המקומי רק לאחר אישור. המקורות והיומן ייבדקו שוב בשמירה.", "A local work block is added only after confirmation. Sources and the calendar are checked again when saving.")} closeLabel={t("סגירה", "Close")}>
      {reviewed.replacement && <p>{t("הזמן הקודם", "Previous time")}: <bdi>{format(reviewed.replacement.start)} — {format(reviewed.replacement.end)}</bdi></p>}
      <h3 dir="auto">{reviewed.title}{reviewed.course_name ? ` · ${reviewed.course_name}` : ""}</h3><p><bdi>{format(proposal.record.start)} — {format(proposal.record.end)}</bdi></p>
      <p className="field-help">{reviewed.replacement ? t("אפשר לבטל ולערוך את משבצת העבודה הקיימת בלוח השנה.", "Cancel to edit the existing work block in Calendar.") : t("אפשר לבטל ולבחור זמן אחר בכלי תכנון המשימות הקיים.", "Cancel to choose a different time with the task planner.")}</p>
      {error && <p className="error-message" role="alert">{error}</p>}
      <div className="google-actions"><Button disabled={busy || disabled} onClick={() => void save()}>{t("אישור ושמירה ביומן", "Confirm and save to calendar")}</Button><Button variant="ghost" disabled={busy} onClick={() => void cancel()}>{t("ביטול", "Cancel")}</Button></div>
    </Modal>}
  </section>;
}
