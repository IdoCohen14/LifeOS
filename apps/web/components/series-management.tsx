"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { dayKey, shiftDay } from "@/lib/dates";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Series = { id: string; title: string; timezone: string; count: number };
type Page = { items: Series[]; next_cursor: string | null };
type Preview = { id: string | null; timezone: string; title: string; skipped_modified: number; skipped_all_day?: number; skipped_unchanged?: number; skipped_multiday?: number; events: { id: string; title: string; start: string; end: string; all_day: boolean; modified: boolean; unknown: boolean; new_all_day?: boolean; new_title?: string | null; new_start?: string; new_end?: string }[] };
export function SeriesManagement({ csrf, settings, t, onClose, onChanged, onUnauthorized }: { csrf: string; settings: Settings; t: Translate; onClose: () => void; onChanged: () => Promise<void>; onUnauthorized: () => void }) {
  const [page, setPage] = useState<Page | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [fromDay, setFromDay] = useState("");
  const [includeModified, setIncludeModified] = useState(false);
  const [includeAllDay, setIncludeAllDay] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [deleted, setDeleted] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<"delete" | "reschedule" | "shift" | "rename" | "convert" | "combined">("delete");
  const [clock, setClock] = useState("09:00");
  const [duration, setDuration] = useState(60);
  const [dayShift, setDayShift] = useState(1);
  const [newTitle, setNewTitle] = useState("");
  const renaming = operation === "rename";
  const converting = operation === "convert";
  const combining = operation === "combined";
  const [targetType, setTargetType] = useState<"" | "all_day" | "timed">("");
  const shifting = operation === "shift";
  const rescheduling = operation !== "delete";
  const proposalPath = rescheduling ? "reschedules" : "deletions";
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError ? error.status === 409 ? "changed" : error.status === 404 ? "expired" : error.status === 422 ? "invalid" : error.status === 429 ? "limit" : "unavailable" : "unavailable");
  }, [onUnauthorized]);
  const load = useCallback(async (after: string | null = null) => {
    setBusy(true); setError("");
    try {
      const next = await api<Page>(`recurrence/series${after ? `?cursor=${after}` : ''}`);
      setPage(next); setCursor(after); setSelectedId(next.items[0]?.id ?? ""); setNewTitle("");
      setFromDay(dayKey(new Date(), next.items[0]?.timezone ?? 'UTC'));
      setIncludeModified(false); setIncludeAllDay(false); setTargetType("");
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }, [failed]);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const next = await api<Page>('recurrence/series');
        if (active) { setPage(next); setCursor(null); setSelectedId(next.items[0]?.id ?? ''); setNewTitle(""); setFromDay(dayKey(new Date(), next.items[0]?.timezone ?? 'UTC')); setIncludeModified(false); setIncludeAllDay(false); setTargetType(""); }
      } catch (error) { if (active) failed(error); }
      finally { if (active) setBusy(false); }
    })();
    return () => { active = false; };
  }, [failed, csrf]);
  const selected = page?.items.find(value => value.id === selectedId);
  async function cancel() {
    if (preview?.id && deleted === null) {
      try { await api(`recurrence/${proposalPath}/${preview.id}`, 'DELETE', undefined, csrf); }
      catch (error) { if (error instanceof ApiError && error.status === 401) onUnauthorized(); }
    }
  }
  function close() { if (busy && deleted === null) return; void cancel(); onClose(); }
  async function reset() { setBusy(true); await cancel(); setPreview(null); setDeleted(null); setError(""); setBusy(false); }
  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected || busy) return;
    setBusy(true); setError("");
    try { setPreview(await api<Preview>(`recurrence/series/${selected.id}/${rescheduling ? 'reschedule-preview' : 'deletion-preview'}`, 'POST', { from_day: fromDay, include_modified: includeModified, ...(combining ? {shift_and_time:true,day_shift:dayShift,clock,duration} : converting ? {target_all_day: targetType === "all_day", ...(targetType === "timed" ? {clock,duration} : {})} : renaming ? {new_title: newTitle} : shifting ? {day_shift: dayShift, preserve_time: true, include_all_day: includeAllDay} : rescheduling ? {clock, duration} : {}) }, csrf)); }
    catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!preview?.id || busy || deleted !== null) return;
    setBusy(true); setError("");
    try { const result = await api<{ deleted_count: number; changed_count: number }>(`recurrence/${proposalPath}/confirm`, 'POST', { id: preview.id }, csrf); setDeleted(rescheduling ? result.changed_count : result.deleted_count); try { await onChanged(); } catch { setError('refresh'); } }
    catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  function format(value: string, allDay: boolean) {
    if (allDay) return value.split('-').reverse().join('/');
    return new Intl.DateTimeFormat(settings.language, { timeZone: preview?.timezone ?? selected?.timezone ?? settings.timezone, year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', hourCycle:'h23', timeZoneName:'shortOffset' }).format(new Date(value));
  }
  const destinationAllDay = (value: Preview["events"][number]) => value.new_all_day ?? value.all_day;
  const dayField = <label>{t("מספר ימים להזזה", "Calendar days to shift")}<input type="number" min={-28} max={28} step={1} required value={dayShift} onChange={event => setDayShift(Number(event.target.value))} /></label>;
  const clockFields = <div className="form-grid"><label>{t("שעה חדשה למופעים", "New occurrence time")}<input type="time" value={clock} onChange={event => setClock(event.target.value)} required /></label><label>{t("משך חדש בדקות", "New duration in minutes")}<input type="number" min={5} max={720} step={5} value={duration} onChange={event => setDuration(Number(event.target.value))} required /></label></div>;
  const today = dayKey(new Date(), selected?.timezone ?? settings.timezone);
  return <Modal open onClose={close} title={t("ניהול סדרות שבועיות", "Manage weekly series")} description={t("בחירת מופעים לשינוי כותרות, סוג, מועדים או למחיקה, עם בדיקה ואישור נפרדים. מופעים שנערכו מוגנים כברירת מחדל.", "Review and confirm selected occurrence title/type/date/time changes or deletions. Individually edited occurrences are protected by default.")} closeLabel={t("סגירה", "Close")}>
    {!preview && <>
      {page && page.items.length === 0 && <p role="status">{t("אין סדרות שמורות בעמוד הזה. אירועים ללא מיפוי סדרה נשארים לניהול בנפרד.", "No saved series on this page. Events without a series mapping remain individually managed.")}</p>}
      {!!page?.items.length && <form className="form-stack" onSubmit={propose}><fieldset className="planner-fields" disabled={busy}>
        <label>{t("פעולה בסדרה", "Series action")}<select aria-label={t("פעולה בסדרה", "Series action")} value={operation} onChange={event => { setOperation(event.target.value as "delete" | "reschedule" | "shift" | "rename" | "convert" | "combined"); setIncludeAllDay(false); setTargetType(""); }}><option value="delete">{t("מחיקת מופעים", "Delete occurrences")}</option><option value="reschedule">{t("שינוי שעות", "Change times")}</option><option value="shift">{t("הזזת תאריכים", "Shift dates")}</option><option value="rename">{t("שינוי כותרות", "Change titles")}</option><option value="convert">{t("שינוי סוג אירוע", "Change event type")}</option><option value="combined">{t("תאריך ושעה יחד", "Shift dates and times")}</option></select></label>
        <label>{t("סדרה לניהול", "Series to manage")}<select value={selectedId} onChange={event => { setSelectedId(event.target.value); const value = page.items.find(item => item.id === event.target.value); setNewTitle(""); setFromDay(dayKey(new Date(), value?.timezone ?? settings.timezone)); setIncludeModified(false); setIncludeAllDay(false); setTargetType(""); }}>{page.items.map(value => <option key={value.id} value={value.id}>{value.title} · {value.count} {t("מופעים שמורים", "saved occurrences")}</option>)}</select></label>
        <label>{t("בחירת מופעים החל מתאריך", "Select occurrences from date")}<input type="date" min={today} max={shiftDay(today,400)} value={fromDay} onChange={event => setFromDay(event.target.value)} required /></label>
        <p className="field-help"><bdi>{selected?.timezone}</bdi> · {(renaming || converting) ? t("הבחירה לפי אזור הזמן של הסדרה: מופעים עם שעה שטרם התחילו ואירועי יום שלם החל מהתאריך הנבחר.", "Selection uses the series timezone: future timed occurrences and all-day entries starting on or after the selected date.") : rescheduling ? t("התאריכים והשעות לפי אזור הזמן של הסדרה. מופעים עם שעה נבחרים רק אם טרם התחילו; בהזזת תאריכים אפשר לבחור גם יום שלם במפורש.", "Dates and clocks use the series timezone. Timed occurrences must be future; date shifts can explicitly include all-day occurrences.") : t("התאריכים לפי אזור הזמן של הסדרה. אירוע עם שעה שכבר התחיל לא ייכלל; יום שלם בתאריך שנבחר נכלל.", "Dates use the series timezone. Timed events already started are excluded; all-day events on the selected date are included.")}</p>
        <label className="notification-check"><input type="checkbox" checked={includeModified} onChange={event => setIncludeModified(event.target.checked)} />{t("לכלול גם מופעים שנערכו או שמצב המקור שלהם אינו ידוע", "Include edited occurrences or those with unknown original state")}</label>
        {combining && <>{dayField}{clockFields}<p className="field-help">{t("עד 28 ימים לכל כיוון, ללא אפס, למופעים עתידיים עם שעה בלבד. התאריך המקומי מוזז ואז נקבעות השעה החדשה והמשך בדקות בפועל. שעות חסרות או כפולות ידחו את ההצעה כולה. בדקו את כל המועדים והחפיפות לפני אישור.", "Shift up to28local days in either direction, not zero, for future timed sources only. The local date shifts, then the new clock and elapsed duration apply. Missing/repeated local times reject the whole proposal. Review every range and overlap before approving.")}</p></>}
        {converting && <><label>{t("סוג האירוע החדש", "New occurrence type")}<select aria-label={t("סוג האירוע החדש", "New occurrence type")} required value={targetType} onChange={event=>setTargetType(event.target.value as "" | "all_day" | "timed")}><option value="" disabled>{t("בחירת סוג יעד", "Choose a target type")}</option><option value="all_day">{t("יום שלם", "All day")}</option><option value="timed">{t("עם שעה", "Timed")}</option></select></label>{targetType === "timed" && clockFields}<p className="field-help">{t("אפשר להמיר מופעים קיימים של יום אחד בלבד; מופעים של כמה ימים ידולגו ויוצגו בספירה. יום שלם יחול בתאריך ההתחלה לפי אזור הזמן של הסדרה. לאירוע עם שעה בחרו שעת התחלה עתידית ומשך בדקות בפועל; במעבר שעון שעת הסיום המקומית עשויה להשתנות. בדקו את הסוג והטווח המלא לפני אישור.", "Only single-day sources convert; multi-day occurrences are skipped and counted. All-day uses the start date in the series timezone. For a timed event choose a future start clock and elapsed minutes; DST can change the local end clock. Review the type and full range before confirming.")}</p></>}
        {renaming && <><label>{t("כותרת חדשה למופעים שנבחרו", "New title for selected occurrences")}<input type="text" required maxLength={240} value={newTitle} onChange={event => setNewTitle(event.target.value)} /></label><p className="field-help">{t("הכותרת תחול על המופעים ברשימה שתאשרו. שם הסדרה ברשימת הניהול נשאר לזיהוי הסדרה המקורית.", "The title applies to occurrences in the list you approve. The management list keeps the original series name for identification.")}</p></>}
        {operation === "reschedule" && <>{clockFields}<p className="field-help">{t("התאריכים והפרטים נשמרים. אירועי יום שלם לא ישתנו. ייתכנו חפיפות עם אירועים אחרים ביומן; בדקו את השעות לפני אישור.", "Dates and event details are preserved. All-day events stay unchanged. Events may overlap other calendar entries; review times before confirming.")}</p></>}
        {shifting && <><label className="notification-check"><input type="checkbox" checked={includeAllDay} onChange={event => setIncludeAllDay(event.target.checked)} />{t("לכלול אירועי יום שלם", "Include all-day occurrences")}</label><p className="field-help">{t("אירועי יום שלם ייכללו רק בסימון מפורש. טווח התאריכים ומספר הימים נשמרים, כולל אירועים של היום. יעד לפני היום ידחה את ההזזה כולה.", "All-day occurrences require explicit selection. Their calendar-day length is preserved, including occurrences starting today. A destination before today rejects the entire shift.")}</p>{dayField}<p className="field-help">{t("עד 28 ימים: מספר חיובי לדחייה ושלילי להקדמה, ללא אפס. הבחירה לפי התאריכים הקיימים. שעת ההתחלה המקומית והמשך בפועל נשמרים לכל מופע; במעבר שעון שעת הסיום עשויה להשתנות. אירועי יום שלם ללא סימון נשארים ללא שינוי. יעד שכבר עבר או שעה חסרה/כפולה ידחו את ההזזה כולה. ייתכנו חפיפות ביומן.", "Up to28days: positive to postpone, negative to advance, not zero. Selection uses current dates. Each local start clock and elapsed duration are preserved; DST can change the local end clock. All-day events stay unchanged unless selected. Past or missing/repeated destination times reject the whole shift. Calendar events may overlap.")}</p></>}
        <Button type="submit" disabled={busy || !selected}>{combining ? t("תצוגה מקדימה לתאריך ושעה", "Preview date and time changes") : converting ? t("תצוגה מקדימה להמרת סוג", "Preview type conversion") : renaming ? t("תצוגה מקדימה לשינוי כותרות", "Preview title changes") : shifting ? t("תצוגה מקדימה להזזת תאריכים", "Preview date shift") : rescheduling ? t("תצוגה מקדימה לשינוי שעות", "Preview time changes") : t("תצוגה מקדימה למחיקה", "Preview deletion")}</Button>
      </fieldset></form>}
      <div className="google-actions"><Button variant="ghost" size="small" disabled={busy || history.length === 0} onClick={() => { const previous = history[history.length-1] ?? null; setHistory(values => values.slice(0,-1)); void load(previous); }}>{t("עמוד קודם", "Previous page")}</Button><Button variant="ghost" size="small" disabled={busy || !page?.next_cursor} onClick={() => { setHistory(values => [...values,cursor]); void load(page?.next_cursor ?? null); }}>{t("עוד סדרות", "More series")}</Button><Button variant="ghost" size="small" disabled={busy} onClick={() => { setHistory([]); void load(); }}>{t("רענון סדרות", "Refresh series")}</Button></div>
    </>}
    {preview && <div className="form-stack">
      <p><strong dir="auto">{preview.title}</strong> · <bdi>{preview.timezone}</bdi></p>
      {preview.skipped_modified > 0 && <p className="field-help">{t(`${preview.skipped_modified} מופעים שנערכו או שמצבם אינו ידוע לא נבחרו.`, `${preview.skipped_modified} edited/unknown occurrences were not selected.`)}</p>}
      {!!preview.skipped_all_day && <p className="field-help">{t(`${preview.skipped_all_day} אירועי יום שלם נשארים ללא שינוי.`, `${preview.skipped_all_day} all-day events stay unchanged.`)}</p>}
      {!!preview.skipped_multiday && <p className="field-help">{t(`${preview.skipped_multiday} מופעים של כמה ימים לא הומרו. אפשר לערוך אותם בנפרד ביומן.`, `${preview.skipped_multiday} multi-day occurrences were not converted. Edit them individually in the calendar.`)}</p>}
      {!!preview.skipped_unchanged && <p className="field-help">{converting ? t(`${preview.skipped_unchanged} מופעים כבר בסוג שנבחר.`, `${preview.skipped_unchanged} occurrences already have the selected type.`) : renaming ? t(`${preview.skipped_unchanged} מופעים כבר בכותרת שנבחרה.`, `${preview.skipped_unchanged} occurrences already use the selected title.`) : t(`${preview.skipped_unchanged} מופעים כבר בשעות שנבחרו.`, `${preview.skipped_unchanged} occurrences already use the selected times.`)}</p>}
      {preview.events.length === 0 ? <p role="status">{combining ? t("אין מופעים מתאימים לשינוי המשולב.", "No occurrences match this combined change.") : converting ? t("אין מופעים מתאימים להמרת הסוג לפי הבחירה הזאת.", "No occurrences need a type conversion for this selection.") : renaming ? t("אין מופעים שדורשים שינוי כותרת לפי הבחירה הזאת.", "No occurrences need a title change for this selection.") : shifting ? t("אין מופעים מתאימים להזזת תאריכים לפי הבחירה הזאת.", "No matching occurrences for this date shift.") : rescheduling ? t("אין מופעים שדורשים שינוי שעות לפי הבחירה הזאת.", "No occurrences need a time change for this selection.") : t("לא נמצאו מופעים מתאימים למחיקה לפי הבחירה הזאת.", "No matching occurrences to delete for this selection.")}</p> : <>
        <p className="field-help">{renaming ? t(`${preview.events.length} מופעים נבחרו. בדקו את הכותרות הקיימות והחדשות לפני אישור.`, `${preview.events.length} occurrences selected. Review current and new titles before confirming.`) : rescheduling ? t(`${preview.events.length} מופעים נבחרו. בדקו את התאריכים והשעות הקיימים והחדשים לפני אישור. ייתכנו חפיפות עם אירועים אחרים.`, `${preview.events.length} occurrences selected. Review current and new dates/times before confirming. Other events may overlap.`) : t(`${preview.events.length} מופעים נבחרו. בדקו את הרשימה לפני אישור המחיקה.`, `${preview.events.length} occurrences selected. Review the list before confirming deletion.`)}</p>
        <ol className="recurring-preview-list">{preview.events.map(value => <li key={value.id}>
          <strong dir="auto">{value.title}</strong>
          {renaming && value.new_title && <p>{t("כותרת חדשה: ", "New title: ")}<strong dir="auto">{value.new_title}</strong></p>}
          <p>{rescheduling && !renaming && (value.all_day ? t("תאריכים קיימים: ", "Current dates: ") : t("שעה קיימת: ", "Current time: "))}{format(value.start,value.all_day)}{!value.all_day && <> — {format(value.end,false)}</>}{value.all_day && <>{shiftDay(value.end,-1) !== value.start && <> — {format(shiftDay(value.end,-1),true)} {t("(כולל)", "(inclusive)")}</>} · {t("יום שלם", "All day")}</>}</p>
          {converting && <small>{t("סוג חדש: ", "New type: ")}{destinationAllDay(value) ? t("יום שלם", "All day") : t("עם שעה", "Timed")}</small>}
          {rescheduling && !renaming && value.new_start && value.new_end && <p><strong>{destinationAllDay(value) ? t("תאריכים חדשים: ", "New dates: ") : t("שעה חדשה: ", "New time: ")}</strong>{format(value.new_start,destinationAllDay(value))}{destinationAllDay(value) ? <>{shiftDay(value.new_end,-1) !== value.new_start && <> — {format(shiftDay(value.new_end,-1),true)} {t("(כולל)", "(inclusive)")}</>} · {t("יום שלם", "All day")}</> : <> — {format(value.new_end,false)}</>}</p>}
          {value.modified && <small>{t("נערך בנפרד", "Individually edited")}</small>}{value.unknown && <small>{t("מצב המקור אינו ידוע", "Original state unknown")}</small>}
        </li>)}</ol>
      </>}
      {deleted !== null ? <p role="status"><strong>{combining ? t(`עודכנו התאריכים והשעות של ${deleted} מופעים שנבדקו.`, `Dates and times changed for ${deleted} reviewed occurrences.`) : converting ? t(`הומר הסוג של ${deleted} מופעים שנבדקו.`, `Type converted for ${deleted} reviewed occurrences.`) : renaming ? t(`עודכנו הכותרות של ${deleted} מופעים שנבדקו.`, `Titles updated for ${deleted} reviewed occurrences.`) : shifting ? t(`הוזזו ${deleted} מופעים שנבדקו.`, `${deleted} reviewed occurrences shifted.`) : rescheduling ? t(`עודכנו השעות של ${deleted} מופעים שנבדקו.`, `Times updated for ${deleted} reviewed occurrences.`) : t(`נמחקו ${deleted} מופעים שנבדקו.`, `${deleted} reviewed occurrences deleted.`)}</strong></p> : <div className="google-actions">{preview.id && <Button variant={rescheduling ? 'default' : 'danger'} disabled={busy} onClick={() => void confirm()}>{combining ? t(`אישור תאריך ושעה של ${preview.events.length} מופעים`, `Confirm date and time changes for ${preview.events.length} occurrences`) : converting ? t(`אישור המרת סוג של ${preview.events.length} מופעים`, `Confirm type conversion for ${preview.events.length} occurrences`) : renaming ? t(`אישור שינוי כותרות של ${preview.events.length} מופעים`, `Confirm title changes for ${preview.events.length} occurrences`) : shifting ? t(`אישור הזזת ${preview.events.length} מופעים`, `Confirm shift of ${preview.events.length} occurrences`) : rescheduling ? t(`אישור שינוי שעות של ${preview.events.length} מופעים`, `Confirm time changes for ${preview.events.length} occurrences`) : t(`אישור מחיקת ${preview.events.length} מופעים`, `Confirm deletion of ${preview.events.length} occurrences`)}</Button>}<Button variant="ghost" disabled={busy} onClick={() => void reset()}>{t("שינוי הבחירה", "Change selection")}</Button></div>}
    </div>}
    {busy && <p role="status">{t("מעבד…", "Processing…")}</p>}
    {error && <p role="alert">{error === 'changed' ? t("מופע או הסדרה השתנו. בקשו תצוגה מקדימה חדשה לפני אישור.", "An occurrence or series changed. Request a fresh preview before confirming.") : error === 'expired' ? t("הסדרה או ההצעה אינם זמינים. רעננו או בקשו תצוגה מקדימה חדשה.", "The series or preview is unavailable. Refresh or request a new preview.") : error === 'invalid' ? t("בדקו תאריך מהיום ועד 400 ימים קדימה באזור הזמן של הסדרה וכותרת של 1–240 תווים בשינוי כותרות. לשינוי שעות: משך 5–720 דקות בכפולות 5 ושעה עתידית. שעה חסרה או כפולה במעבר שעון תדחה את השינוי כולו. להזזת תאריכים בחרו עד 28 ימים לכל כיוון, ללא אפס.", "Check a date from today through400days ahead in the series timezone, and a1–240character title for title changes. For time changes use5–720minutes in steps of5 and a future time. A missing or repeated DST time rejects the entire change. Date shifts allow up to28days in either direction, not zero.") : error === 'refresh' ? t("הפעולה בוצעה אך הרענון נכשל. טענו מחדש את היומן.", "The operation succeeded but refresh failed. Reload the calendar.") : error === 'limit' ? t("יש יותר מדי הצעות ממתינות. סגרו הצעה ישנה או נסו מאוחר יותר.", "Too many pending previews. Close an old one or retry later.") : t("הפעולה לא הושלמה. אפשר לנסות שוב את אותו אישור; לא ייבחרו מופעים נוספים.", "The operation did not finish. Retrying the same confirmation will not select additional occurrences.")}</p>}
  </Modal>;
}
