"use client";

import { useState } from "react";
import { CalendarClock, CheckCheck, Clock3, TriangleAlert } from "lucide-react";
import { ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

export type Recommendation = { id: string; kind: "overdue" | "due_soon" | "conflict"; title: string; other_title?: string; due?: string; start?: string; end?: string; target: "tasks" | "calendar" };
export type RecommendationFeed = { items: Recommendation[]; truncated: boolean; stale_sources: string[] };

export function RecommendationsPanel({ data, settings, t, onDismiss, onNavigate, onRefresh, onUnauthorized }: {
  data: RecommendationFeed | null; settings: Settings; t: Translate;
  onDismiss: (id: string) => Promise<void>; onNavigate: (view: "tasks" | "calendar") => void;
  onRefresh: () => Promise<void>; onUnauthorized: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  function format(value: string) {
    return value.length === 10 ? value.split("-").reverse().join("/") : new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(value));
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(false);
    try { await action(); }
    catch (error) { if (error instanceof ApiError && error.status === 401) onUnauthorized(); setError(true); }
    finally { setBusy(false); }
  }
  return <section className="panel recommendations-panel" aria-label={t("לתשומת לבך", "Worth your attention")}>
    <div className="panel-heading"><div className="heading-with-icon"><CalendarClock size={20} aria-hidden="true" /><h2>{t("לתשומת לבך", "Worth your attention")}</h2></div><span className="subtle-badge">{t("לפי היומן והמשימות", "From your calendar and tasks")}</span></div>
    {!data || error ? <div className="notice" role="alert"><span>{t("לא ניתן לעדכן את ההמלצות כעת.", "Unable to update recommendations now.")}</span><Button variant="ghost" size="small" disabled={busy} onClick={() => void perform(onRefresh)}>{t("רענון המלצות", "Refresh recommendations")}</Button></div> : <>
      {data.stale_sources.length > 0 && <p className="field-help" role="status">{t("חלק מהיומנים המחוברים אינם מעודכנים. ההמלצות מבוססות על המידע השמור.", "Some connected calendars are outdated. Recommendations use cached information.")}</p>}
      {data.items.length === 0 && <p className="recommendation-clear" role="status"><CheckCheck size={18} aria-hidden="true" />{t("אין המלצות דחופות כרגע", "No urgent recommendations right now")}</p>}
      <div className="recommendation-list">{data.items.map(item => <article className={`recommendation-item recommendation-${item.kind}`} key={item.id}>
        <span className="recommendation-icon" aria-hidden="true">{item.kind === "conflict" ? <TriangleAlert size={18} /> : <Clock3 size={18} />}</span>
        <div className="recommendation-copy"><small>{item.kind === "conflict" ? t("חפיפה ביומן", "Calendar conflict") : item.kind === "overdue" ? t("מועד המשימה עבר", "Task is overdue") : t("מועד שמתקרב", "Upcoming deadline")}</small><h3 dir="auto">{item.title}{item.other_title && <> · {item.other_title}</>}</h3><p>{item.due && format(item.due)}{item.start && format(item.start)}{item.end && <> — {format(item.end)}</>}</p>
          <div className="google-actions"><Button variant="secondary" size="small" onClick={() => onNavigate(item.target)}>{item.target === "calendar" ? t("פתיחת היומן", "Open calendar") : t("פתיחת המשימות", "Open tasks")}</Button><Button variant="ghost" size="small" disabled={busy} onClick={() => void perform(() => onDismiss(item.id))} aria-label={`${t("הסתר ל־24 שעות", "Hide for 24 hours")}: ${item.title}`}>{t("הסתר ל־24 שעות", "Hide for 24 hours")}</Button></div>
        </div>
      </article>)}</div>
      {data.truncated && <p className="field-help">{t("מוצגות עד 5 המלצות; בדקו ביומן ובמשימות גם פריטים נוספים.", "Showing up to 5 recommendations; check calendar/tasks for additional items.")}</p>}
    </>}
    <p className="field-help">{t("לא משתנה דבר בלי פעולה שלך. ההסתרה מקומית; שינוי בפרטי המשימה או האירוע עשוי להציג המלצה חדשה.", "Nothing changes without your action. Hiding is local; changed task/event details can create a new recommendation.")}</p>
  </section>;
}
