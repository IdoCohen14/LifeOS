"use client";
import { useRef, useState, type FormEvent } from "react";
import { Repeat2, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { shiftDay } from "@/lib/dates";
import type { Settings, Translate } from "@/lib/types";
import { SeriesManagement } from "./series-management";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Preview = { id: string; timezone: string; events: { title: string; start: string; end: string; all_day: boolean }[] };
export function RecurringEvents({ csrf, settings, today, t, onChanged, onUnauthorized }: {
  csrf: string; settings: Settings; today: string; t: Translate; onChanged: () => Promise<void>; onUnauthorized: () => void;
}) {
  const [managing, setManaging] = useState(false);
  const [open, setOpen] = useState(false);
  const [allDay, setAllDay] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError && error.status === 422 ? "invalid" : error instanceof ApiError && error.status === 409 ? "changed" : error instanceof ApiError && error.status === 404 ? "expired" : error instanceof ApiError && error.status === 429 ? "limit" : "unavailable");
  }
  async function cancel() {
    if (preview && !saved) {
      try { await api(`recurrence/proposals/${preview.id}`, "DELETE", undefined, csrf); }
      catch (error) { if (error instanceof ApiError && error.status === 401) onUnauthorized(); }
    }
  }
  function close() { if (busy && !saved) return; void cancel(); generation.current += 1; setBusy(false); setOpen(false); setPreview(null); setSaved(false); setError(""); }
  async function reset() { setBusy(true); await cancel(); setPreview(null); setError(""); setSaved(false); setBusy(false); }
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      setPreview(await api<Preview>("recurrence/preview", "POST", { title: String(form.get("title")).trim(), notes: String(form.get("notes") || ""), day: String(form.get("day")), count: Number(form.get("count")), all_day: allDay, clock: allDay ? "09:00" : String(form.get("clock")), duration: allDay ? 60 : Number(form.get("duration")), timezone: settings.timezone }, csrf));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!preview || saved || busy) return;
    const started = generation.current;
    setBusy(true); setError("");
    try {
      await api("recurrence/confirm", "POST", { id: preview.id }, csrf);
      setSaved(true);
      try { await onChanged(); } catch { if (started === generation.current) setError("refresh"); }
    } catch (error) { failed(error); }
    finally { if (started === generation.current) setBusy(false); }
  }
  function format(value: string, dateOnly: boolean) {
    if (dateOnly) return value.split("-").reverse().join("/");
    return new Intl.DateTimeFormat(settings.language, { timeZone: preview?.timezone ?? settings.timezone, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "shortOffset" }).format(new Date(value));
  }
  return <>
    <div className="calendar-recurring-entry"><Button variant="secondary" onClick={() => { setAllDay(false); setOpen(true); }}><Repeat2 size={17} aria-hidden="true" />{t("אירוע שבועי חוזר", "Weekly recurring event")}</Button><Button variant="ghost" onClick={() => setManaging(true)}>{t("ניהול סדרות שבועיות", "Manage weekly series")}</Button></div>
    {managing && <SeriesManagement csrf={csrf} settings={settings} t={t} onClose={() => setManaging(false)} onChanged={onChanged} onUnauthorized={onUnauthorized} />}
    {open && <Modal open onClose={close} title={t("יצירת אירועים שבועיים", "Create weekly events")} description={t("סדרה מוגבלת של אירועים מקומיים. קודם בודקים את כל התאריכים, ואז מאשרים שמירה.", "A finite set of local events. Review every date before confirming creation.")} closeLabel={t("סגירה", "Close")}>
      <p className="field-help">{t("כל מופע יישמר כאירוע אישי שניתן לערוך בנפרד. דרך ״ניהול סדרות שבועיות״ אפשר לבחור כמה מופעים למחיקה. אין חזרה אינסופית או שינוי שעות לכל הסדרה. ייתכנו התנגשויות עם היומן הקיים.", "Each occurrence is a personal event editable separately. Manage weekly series lets you review multiple occurrences for deletion. No endless recurrence or group time changes. Events may overlap your calendar.")}</p>
      {!preview && <form className="form-stack" onSubmit={propose}><fieldset className="planner-fields" disabled={busy}>
        <label>{t("כותרת האירוע החוזר", "Recurring event title")}<input name="title" maxLength={240} required /></label>
        <div className="form-grid"><label>{t("תאריך ראשון", "First date")}<input type="date" name="day" defaultValue={shiftDay(today, 1)} min={today} max={shiftDay(today, 30)} required /></label><label>{t("מספר מופעים שבועיים", "Number of weekly occurrences")}<input type="number" name="count" min={2} max={52} step={1} defaultValue={4} required /></label></div>
        <label className="notification-check"><input type="checkbox" checked={allDay} onChange={event => setAllDay(event.target.checked)} />{t("יום שלם בכל שבוע", "All day each week")}</label>
        {!allDay && <div className="form-grid"><label>{t("שעת התחלה בכל שבוע", "Weekly start time")}<input type="time" name="clock" defaultValue="09:00" required /></label><label>{t("משך לפי השעון המקומי בדקות", "Local clock duration in minutes")}<input type="number" name="duration" defaultValue={60} min={5} max={720} step={5} required /></label></div>}
        <label>{t("הערות לכל מופע", "Notes for each occurrence")}<textarea name="notes" maxLength={10000} rows={2} /></label>
        <p className="field-help"><bdi>{settings.timezone}</bdi> · {t("אותה שעה מקומית בכל שבוע. מעבר שעון עשוי לשנות את המשך בפועל; שעות חסרות או כפולות יידחו.", "Same local clock each week. DST can change elapsed duration; missing or repeated times are rejected.")}</p>
        <Button type="submit" disabled={busy}>{t("תצוגה מקדימה של המופעים", "Preview occurrences")}</Button>
      </fieldset></form>}
      {preview && <div className="form-stack">
        <p><strong dir="auto">{preview.events[0]?.title}</strong> · {preview.events.length} {t("מופעים", "occurrences")} · <bdi>{preview.timezone}</bdi></p>
        <ol className="recurring-preview-list">{preview.events.map((event, i) => <li key={i}><span>{format(event.start, event.all_day)}</span>{!event.all_day && <> — <span>{format(event.end, false)}</span></>}{event.all_day && <small> · {t("יום שלם", "All day")}</small>}</li>)}</ol>
        {saved ? <p role="status"><Check size={18} aria-hidden="true" />{t("האירועים נוצרו ביומן האישי.", "Events created in your personal calendar.")}</p> : <div className="google-actions"><Button disabled={busy} onClick={() => void confirm()}>{t(`אישור יצירת ${preview.events.length} אירועים`, `Confirm creation of ${preview.events.length} events`)}</Button><Button variant="ghost" disabled={busy} onClick={() => void reset()}>{t("שינוי הפרטים", "Change details")}</Button></div>}
      </div>}
      {error && <p role="alert">{error === "invalid" ? t("בדקו תאריך עתידי, מספר מופעים ומשך. שעה חסרה או כפולה במעבר שעון באחד המופעים תדחה את כל הסדרה.", "Check future date, count and duration. Any missing/repeated DST time rejects the entire set.") : error === "changed" ? t("אזור הזמן השתנה. יש לבדוק תצוגה מקדימה חדשה.", "Timezone changed. Review a fresh preview.") : error === "expired" ? t("פג תוקף ההצעה. שנו פרטים ובקשו תצוגה מקדימה חדשה.", "Preview expired. Change details and request a new preview.") : error === "limit" ? t("יש יותר מדי הצעות ממתינות. סגרו הצעות ישנות או נסו מאוחר יותר.", "Too many pending previews. Close old previews or retry later.") : error === "refresh" ? t("האירועים נשמרו אך הרענון נכשל. טענו מחדש את היומן.", "Events were saved but refresh failed. Reload the calendar.") : t("הפעולה לא הושלמה. אפשר לנסות שוב; אישור חוזר של אותה הצעה לא ייצור כפילויות.", "The operation did not finish. Retrying the same confirmation will not duplicate events.")}</p>}
    </Modal>}
  </>;
}
