"use client";
import { useState, type FormEvent } from "react";
import { CalendarClock } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PlanningPreferences } from "@/lib/planning-preferences";
import type { Settings, Translate } from "@/lib/types";
import { WeekdayPicker } from "./weekday-picker";
import { Button } from "./ui/button";

export function PlanningPreferenceSettings({ csrf, settings, t, onUnauthorized }: {
  csrf: string; settings: Settings; t: Translate; onUnauthorized: () => void;
}) {
  const [data, setData] = useState<PlanningPreferences | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [clearing, setClearing] = useState(false);
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError && error.status === 409 ? "conflict" : error instanceof ApiError && error.status === 422 ? "invalid" : "unavailable");
  }
  async function load() {
    setBusy(true); setError(""); setNotice(""); setClearing(false);
    try { setData(await api<PlanningPreferences>("planning/preferences")); }
    catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      setData(await api<PlanningPreferences>("planning/preferences", "PUT", {
        daily_limit_minutes:String(form.get("daily_limit_minutes")??"").trim()?Number(form.get("daily_limit_minutes")):null, weekdays: form.getAll("weekdays").map(Number), revision: data.revision, enabled: form.has("enabled"), assistant_enabled: form.has("assistant_enabled"), duration: Number(form.get("duration")), days: Number(form.get("days")), window_start: String(form.get("window_start")), window_end: String(form.get("window_end")),
      }, csrf));
      setNotice(t("ההעדפות נשמרו. ההפעלה נפרדת לתכנון משימה ולעוזר.", "Preferences saved. Task planning and assistant use have separate switches."));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function clear() {
    if (!data || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      setData(await api<PlanningPreferences>("planning/preferences", "DELETE", { revision: data.revision }, csrf));
      setClearing(false); setNotice(t("ההעדפות אופסו והשימוש בהן כובה.", "Preferences reset and their use turned off."));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <div className="panel-heading"><h2>{t("העדפות תכנון", "Planning preferences")}</h2><CalendarClock aria-hidden="true" size={21} /></div>
    <p className="field-help">{t("בחירות שלך בלבד, בנפרד מהיסטוריית השיחה. ההעדפות ממלאות את טופס התכנון ואפשר לשנות אותן בכל הצעה; הן אינן יוצרות אירועים.", "Your choices, separate from conversation history. Preferences prefill planning and can be changed for each proposal; they create no events.")}</p>
    <details onToggle={event => { if (event.currentTarget.open && !data && !busy) void load(); }}>
      <summary>{t("הצגה ועריכת העדפות", "View and edit preferences")}</summary>
      <p className="field-help">{t("השעות לפי אזור הזמן הנוכחי; שינוי אזור הזמן ישנה את משמעותן.", "Hours use the current workspace timezone; changing timezone changes their meaning.")} <bdi>{settings.timezone}</bdi></p>
      {data && <form key={data.revision} className="form-stack" onSubmit={save}>
        <fieldset className="planner-fields" disabled={busy || error === "conflict"}>
          <label className="notification-check"><input type="checkbox" name="enabled" defaultChecked={data.enabled} />{t("שימוש בהעדפות בתכנון משימה", "Use preferences for task planning")}</label>
          <label className="notification-check"><input type="checkbox" name="assistant_enabled" defaultChecked={data.assistant_enabled ?? false} />{t("שימוש בהעדפות במציאת זמן פנוי בעוזר", "Use preferences for assistant free-slot requests")}</label>
          <p className="field-help">{t("העוזר ישתמש בחלון השעות ובמשך ברירת המחדל אם לא ציינתם משך. משך מפורש בבקשה גובר. מספר ימי החיפוש חל רק על תכנון משימה; העוזר מחפש ביום שביקשתם. פרטי ההעדפות אינם נשלחים למודל.", "The assistant uses the saved time window and defaults the duration only when you omit it. An explicit duration wins. Search days applies only to task planning; the assistant searches your requested date. Preference details are not sent to the model.")}</p>
          <label>{t("תקרת דקות מתוזמנות ביום (ריק = ללא תקרה)","Daily scheduled-minute cap (blank = no cap)")}<input name="daily_limit_minutes" type="number" min={15} max={1440} step={15} defaultValue={data.daily_limit_minutes??""}/></label>
          <p className="field-help">{t("התקרה סופרת איחוד של אירועים עם שעות לאורך כל היום. היא אינה מדד ללמידה בפועל. היא תמולא בתכנון משימה רק אם הפעלתם שימוש בהעדפות, ובעוזר רק עם ההרשאה הנפרדת שלו.","The cap counts the union of timed calendar events across the whole day, not actual study effort. Task planning prefills it only with its preferences switch enabled; assistant reuse requires its separate switch.")}</p>
          <WeekdayPicker defaultValue={data.weekdays} t={t} />
          <p className="field-help">{t("בחרו לפחות יום אחד. ימי השבוע מסננים את טווח החיפוש בתכנון משימה. בעוזר נבדק רק היום שביקשתם, בלי מעבר אוטומטי ליום אחר.", "Choose at least one day. Weekdays filter the task search period. The assistant checks only your requested date, without automatically switching dates.")}</p>
          <div className="form-grid">
            <label>{t("משך מועדף בדקות", "Preferred duration in minutes")}<input name="duration" type="number" min={5} max={240} step={5} required defaultValue={data.duration} /></label>
            <label>{t("מספר ימי חיפוש מועדף", "Preferred search days")}<input name="days" type="number" min={1} max={7} step={1} required defaultValue={data.days} /></label>
          </div>
          <div className="form-grid">
            <label>{t("שעת התחלה מועדפת", "Preferred start time")}<input name="window_start" type="time" required defaultValue={data.window_start} /></label>
            <label>{t("שעת סיום מועדפת", "Preferred end time")}<input name="window_end" type="time" required defaultValue={data.window_end} /></label>
          </div>
          <p className="field-help">{t("המשך חייב להיכנס בחלון השעות. החלון באותו יום; שעון קיץ נבדק בכל הצעת זמן. כיבוי אפשרות שומר את הערכים ומפסיק להשתמש בהם באותו ערוץ.", "Duration must fit the same-day window. DST is checked for each proposal. Turning a switch off keeps values and stops using them in that channel.")}</p>
          <Button type="submit" disabled={busy}>{t("שמירת העדפות", "Save preferences")}</Button>
        </fieldset>
      </form>}
      <div className="google-actions">
        <Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{t("רענון העדפות", "Refresh preferences")}</Button>
        <Button size="small" variant="ghost" disabled={!data || busy || error === "conflict"} onClick={() => setClearing(true)}>{t("איפוס העדפות", "Reset preferences")}</Button>
      </div>
      {clearing && <div className="history-clear-confirm"><p>{t("לאפס את ההעדפות ולכבות את השימוש בהן? משימות, אירועים ושיחות לא ישתנו. גיבויים קודמים עשויים לשמור את הערכים הישנים.", "Reset preferences and turn off their use? Tasks, events and conversations stay unchanged. Earlier backups may retain old values.")}</p><div className="google-actions"><Button size="small" disabled={busy} onClick={() => void clear()}>{t("אישור איפוס ההעדפות", "Confirm preference reset")}</Button><Button size="small" variant="ghost" disabled={busy} onClick={() => setClearing(false)}>{t("ביטול", "Cancel")}</Button></div></div>}
      {error && <p role="alert">{error === "conflict" ? t("ההעדפות השתנו במקום אחר. רעננו ובדקו אותן לפני שמירה נוספת.", "Preferences changed elsewhere. Refresh and review them before saving again.") : error === "invalid" ? t("בדקו את המשך, התקרה היומית, מספר הימים, ימי השבוע וחלון השעות. בחרו לפחות יום אחד.", "Check duration, daily cap, search days, weekdays and time window. Choose at least one weekday.") : t("לא ניתן לטעון או לשמור העדפות כרגע. נסו רענון.", "Preferences are unavailable. Try refreshing.")}</p>}
      <p role="status" className="field-help">{busy ? t("טוען…", "Loading…") : notice}</p>
    </details>
  </section>;
}
