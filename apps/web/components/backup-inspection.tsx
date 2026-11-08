"use client";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Inspection = { valid: boolean; created_at: string; schema: string; counts: { tasks: number; events: number } };
export function BackupInspection({ id, csrf, settings, t, onClose, onUnauthorized }: { id: string; csrf: string; settings: Settings; t: Translate; onClose: () => void; onUnauthorized: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Inspection | null>(null);
  const [error, setError] = useState("");
  async function inspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError(""); setResult(null);
    try { setResult(await api<Inspection>(`recovery/backups/${id}/inspect`, "POST", { password }, csrf)); }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(error instanceof ApiError ? error.status === 404 ? "missing" : error.status === 409 ? "busy" : error.status === 413 ? "large" : error.status === 422 ? "invalid" : "unavailable" : "unavailable");
    } finally { setPassword(""); setBusy(false); }
  }
  return <Modal open onClose={() => { if (!busy) onClose(); }} title={t("בדיקת גיבוי מוצפן", "Inspect encrypted backup")} description={t("בדיקת סיסמה ותקינות של קובץ שמור. הבדיקה אינה משחזרת או מחליפה נתונים.", "Check the password and integrity of a saved file. This does not restore or replace any data.")} closeLabel={t("סגירה", "Close")}>
    <form className="form-stack" onSubmit={inspect}>
      <label>{t("סיסמת הגיבוי לבדיקה", "Password for backup inspection")}<input type="password" autoComplete="off" minLength={8} maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /></label>
      <Button type="submit" disabled={busy}>{busy ? t("בודק…", "Checking…") : t("בדיקת הגיבוי ללא שחזור", "Check backup without restoring")}</Button>
    </form>
    {error && <p role="alert">{error === "invalid" ? t("לא ניתן לאמת את הגיבוי. בדקו את הסיסמה; ייתכן שהקובץ פגום או שהפורמט אינו נתמך. הנתונים הנוכחיים לא השתנו.", "Could not validate this backup. Check the password; the file may be corrupt or unsupported. Current data is unchanged.") : error === "missing" ? t("הגיבוי כבר אינו זמין במחשב. סגרו ורעננו את הרשימה.", "This backup is no longer available. Close and refresh the list.") : error === "busy" ? t("פעולת גיבוי אחרת מתבצעת כרגע. נסו שוב אחרי שתסתיים.", "Another backup operation is running. Retry after it finishes.") : error === "large" ? t("הקובץ חורג ממגבלת הבדיקה. השתמשו בכלי השחזור המקומי.", "The file exceeds the inspection size limit. Use the local recovery tool.") : t("לא ניתן להשלים בדיקה כרגע. נסו שוב; לא בוצע שחזור.", "Inspection is unavailable. Retry; no restore was performed.")}</p>}
    {result?.valid && <section className="briefing-snapshot" aria-label={t("תוצאות בדיקת הגיבוי", "Backup inspection results")}>
      <p role="status"><strong>{t("הגיבוי עבר את בדיקות התקינות.", "Backup integrity checks passed.")}</strong></p>
      <p>{t("נוצר: ", "Created: ")}{new Intl.DateTimeFormat(settings.language, { dateStyle: 'medium', timeStyle: 'short', timeZone: settings.timezone }).format(new Date(result.created_at))}</p>
      <dl className="briefing-metrics"><div><dt>{t("משימות בגיבוי", "Tasks in backup")}</dt><dd>{result.counts.tasks}</dd></div><div><dt>{t("אירועים אישיים בגיבוי", "Personal events in backup")}</dt><dd>{result.counts.events}</dd></div></dl>
      <p className="field-help">{t("נבדקו פענוח, תקינות מסד הנתונים ופורמט מוכר. הבדיקה אינה תרגול שחזור ואינה מוודאת שחיבורי ספקים יעבדו במחשב אחר. הנתונים, סיסמת הכניסה והחיבורים הנוכחיים לא שונו.", "Decryption, database integrity and a known format were checked. This is not a restore rehearsal or a guarantee that provider connections will work on another computer. Current data, login password and connections were unchanged.")}</p>
    </section>}
    <p className="field-help">{t("הסיסמה משמשת רק לבדיקה הזאת ומנוקה מהטופס אחרי כל ניסיון. לשחזור בפועל יש לסגור את LifeOS ולהשתמש בכלי השחזור המקומי.", "This password is used only for this check and cleared from the form after each attempt. Actual restore requires closing LifeOS and using the local recovery tool.")}</p>
  </Modal>;
}
