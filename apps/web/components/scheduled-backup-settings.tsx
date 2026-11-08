"use client";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Schedule = { enabled: boolean; configured: boolean; clock: string; keep: number; revision: number; timezone: string; last_attempt: number | null; last_success: number | null; last_error: string | null };
export function ScheduledBackupSettings({ csrf, settings, t, onUnauthorized }: { csrf: string; settings: Settings; t: Translate; onUnauthorized: () => void }) {
  const [data, setData] = useState<Schedule | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function failed(error: unknown) {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError && error.status === 409 ? "changed" : error instanceof ApiError ? error.message : "unavailable");
  }
  async function load() {
    setBusy(true); setError(""); setNotice("");
    try { setData(await api<Schedule>("recovery/schedule")); }
    catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!data || busy) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    const password = String(values.get("password") || "");
    const repeat = String(values.get("repeat") || "");
    if (password !== repeat) { setError("password_mismatch"); return; }
    const enabled = values.has("enabled");
    if (enabled && !data.configured && !password) { setError("backup_password_required"); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      setData(await api<Schedule>("recovery/schedule", "PUT", { enabled, clock: String(values.get("clock")), keep: Number(values.get("keep")), password: password || null, revision: data.revision, timezone: data.timezone }, csrf));
      setNotice(t("תזמון הגיבוי נשמר. המחשב והאפליקציה צריכים לפעול; הבדיקה הבאה בתוך כדקה.", "Backup schedule saved. Keep the host and app running; next check in about a minute."));
    } catch (error) { failed(error); }
    finally {
      for (const name of ["password", "repeat"]) { const input = form.elements.namedItem(name); if (input instanceof HTMLInputElement) input.value = ""; }
      setBusy(false);
    }
  }
  function timestamp(value: number | null) { return value === null ? t("עדיין לא נרשם", "Not recorded yet") : new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(value * 1000)); }
  return <details className="notification-preferences" onToggle={event => { if (event.currentTarget.open && !data && !busy) void load(); }}>
    <summary>{t("גיבוי מוצפן יומי אוטומטי", "Automatic daily encrypted backup")}</summary>
    <p className="field-help">{t("כבוי כברירת מחדל. בהפעלה, סיסמת הגיבוי נשמרת מוצפנת עבור חשבון המחשב כדי שהגיבוי יפעל בלי הקלדה. שמרו את הסיסמה גם במקום בטוח מחוץ לאפליקציה; אובדנה עלול למנוע שחזור.", "Off by default. Enabling stores the backup password encrypted for this computer account so backups can run unattended. Keep the password safely outside LifeOS too; losing it can prevent recovery.")}</p>
    <p className="field-help">{t("נשמרים רק הגיבויים האוטומטיים האחרונים לפי הכמות שתבחרו, לאחר גיבוי חדש שהצליח. גיבויים ידניים וקבצים שהורדתם אינם נמחקים. אין שמירה בענן או גיבוי כשהמחשב כבוי.", "Only older automatic backups are deleted after a new successful backup, keeping your chosen count. Manual backups and downloaded files are never pruned. No cloud copy or backups while the host is off.")}</p>
    {data && <>
      <p className="field-help">{data.enabled ? t("התזמון פעיל", "Schedule on") : t("התזמון כבוי", "Schedule off")} · <bdi>{data.timezone}</bdi></p>
      <p className="field-help">{t("גיבוי מתוזמן אחרון שהצליח: ", "Last successful scheduled backup: ")}{timestamp(data.last_success)}</p>
      {data.last_error && <p role="status" className="field-help">{data.last_error === "backup_retention_pending" ? t("הגיבוי הצליח אך חלק מהגיבויים האוטומטיים הישנים לא נמחקו. הניקוי ינסה שוב אחרי גיבוי מוצלח נוסף.", "Backup succeeded, but some older automatic files could not be removed. Cleanup retries after another successful backup.") : t("בדיקת הגיבוי האחרונה נכשלה. בדקו מקום פנוי ושעה תקינה. ניסיון נוסף ייעשה אחרי 15 דקות לכל המוקדם; אם החלפתם חשבון מחשב, הגדירו סיסמה מחדש.", "Last backup check failed. Check disk space and time. Retry is throttled to at least 15 minutes; after changing computer account, configure the password again.")}</p>}
      <form key={data.revision} className="form-stack" onSubmit={save}>
        <fieldset className="planner-fields" disabled={busy || error === "changed"}>
          <label className="notification-check"><input name="enabled" type="checkbox" defaultChecked={data.enabled} />{t("הפעלת גיבוי יומי מתוזמן", "Enable scheduled daily backup")}</label>
          <div className="form-grid"><label>{t("שעת הגיבוי היומי", "Daily backup time")}<input name="clock" type="time" defaultValue={data.clock} required /></label><label>{t("כמות גיבויים אוטומטיים לשמירה", "Automatic backups to keep")}<input name="keep" type="number" min={1} max={30} step={1} defaultValue={data.keep} required /></label></div>
          <label>{t("סיסמה לגיבוי מתוזמן", "Scheduled backup password")}<input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={1024} /></label>
          <label>{t("אימות הסיסמה לגיבוי מתוזמן", "Confirm scheduled backup password")}<input name="repeat" type="password" autoComplete="new-password" minLength={8} maxLength={1024} /></label>
          <p className="field-help">{t("לפחות 8 תווים. בהפעלה ראשונה נדרשת סיסמה; כשקיימת סיסמה שמורה אפשר להשאיר ריק. כיבוי מסיר אותה. גיבוי שכבר התחיל עשוי להסתיים גם אחרי כיבוי. בשחזור התזמון יישאר כבוי ותידרש הגדרה מחדש.", "Minimum 8 characters. A password is required on first enable; leave blank to keep an existing one. Turning off removes it. A running backup may finish after turning off. Restore keeps this schedule off and requires setup again.")}</p>
          <label className="notification-check"><input type="checkbox" name="consent" required />{t("בדקתי את מדיניות השמירה ואת השימוש בסיסמה המוצפנת.", "I reviewed retention and the use of the encrypted password.")}</label>
          <Button type="submit" disabled={busy}>{t("שמירת תזמון גיבוי", "Save backup schedule")}</Button>
        </fieldset>
      </form>
    </>}
    <Button size="small" variant="ghost" disabled={busy} onClick={() => void load()}>{t("רענון תזמון הגיבוי", "Refresh backup schedule")}</Button>
    {error && <p role="alert">{error === "password_mismatch" ? t("סיסמאות הגיבוי אינן תואמות.", "Backup passwords do not match.") : error === "backup_password_required" || error === "backup_password_minimum_8" ? t("נדרשת סיסמת גיבוי באורך 8 תווים לפחות.", "A backup password of at least 8 characters is required.") : error === "backup_schedule_ambiguous" ? t("השעה חסרה או חוזרת באחד ממעברי השעון הקרובים. בחרו שעה אחרת, למשל בבוקר.", "This time is missing or repeated during a coming clock change. Choose another time, such as a morning hour.") : error === "changed" ? t("התזמון או אזור הזמן השתנו. רעננו ובדקו לפני שמירה מחדש.", "Schedule or timezone changed. Refresh and review before saving again.") : t("לא ניתן לשמור או לטעון תזמון כרגע. נסו רענון.", "Schedule is unavailable. Try refreshing.")}</p>}
    <p role="status" className="field-help">{busy ? t("טוען…", "Loading…") : notice}</p>
  </details>;
}
