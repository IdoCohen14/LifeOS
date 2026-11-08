"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Download, HardDriveDownload, RefreshCw, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { BackupInspection } from "./backup-inspection";
import { ScheduledBackupSettings } from "./scheduled-backup-settings";
import { Button } from "./ui/button";

type Backup = { id: string; created_at: string; size: number };

export function RecoverySettings({ csrf, settings, t, onUnauthorized }: {
  csrf: string; settings: Settings; t: Translate; onUnauthorized: () => void;
}) {
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(error instanceof ApiError ? error.message : "unavailable");
  }, [onUnauthorized]);
  const load = useCallback(async () => { setBackups(await api<Backup[]>("recovery/backups")); setLoaded(true); }, []);
  useEffect(() => { void (async () => { try { await load(); } catch (error) { failed(error); } })(); }, [load, failed, csrf]);
  async function create(event: FormEvent) {
    event.preventDefault(); setError(""); setNotice("");
    if (password !== repeat) { setError("password_mismatch"); return; }
    setBusy(true);
    try {
      const result = await api<Backup>("recovery/backups", "POST", { password }, csrf);
      setBackups(previous => [result, ...previous.filter(item => item.id !== result.id)].slice(0, 20)); setLoaded(true);
      setPassword(""); setRepeat("");
      setNotice(t("הגיבוי המוצפן נוצר ונשמר במחשב. אפשר להוריד עותק מהרשימה.", "Encrypted backup created and saved on this computer. Download a copy below."));
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  async function download(path: string, filename: string) {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/recovery/${path}`, { cache: "no-store" });
      if (!response.ok) { const error = await response.json().catch(() => ({})); throw new ApiError(response.status, error.detail || "unavailable"); }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }
  return <section className="panel connections-settings recovery-settings" aria-label={t("גיבוי וייצוא", "Backup and export")}>
    <div className="panel-heading"><div className="heading-with-icon"><HardDriveDownload size={22} aria-hidden="true" /><h2>{t("גיבוי וייצוא", "Backup and export")}</h2></div><ShieldCheck size={20} aria-hidden="true" /></div>
    <p>{t("גיבוי מלא מוצפן של הנתונים, כולל קובצי הלימוד והגדרות החיבורים. בחר סיסמת גיבוי נפרדת ושמור אותה במקום בטוח — היא אינה נשמרת באפליקציה.", "Create an encrypted full backup including study files and connection configuration. Choose a separate backup password and keep it safe—it is not stored in the app.")}</p>
    <form className="recovery-form" onSubmit={create}>
      <label>{t("סיסמת גיבוי", "Backup password")}<input type="password" autoComplete="new-password" minLength={8} maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /></label>
      <label>{t("אימות סיסמת גיבוי", "Confirm backup password")}<input type="password" autoComplete="new-password" minLength={8} maxLength={1024} required value={repeat} onChange={event => setRepeat(event.target.value)} disabled={busy} /></label>
      <Button type="submit" disabled={busy}>{busy ? t("מעבד…", "Processing…") : t("יצירת גיבוי מוצפן", "Create encrypted backup")}</Button>
    </form>
    <p className="field-help">{t("לפחות 8 תווים. הגיבוי מוגבל ל־128 MiB של מסד נתונים. שחזור נעשה כשהאפליקציה סגורה, ומשחזר גם את סיסמת הכניסה שהייתה בזמן הגיבוי. חיבורי Google ו־Moodle עשויים לדרוש חיבור מחדש במחשב או בחשבון Windows אחר.", "Minimum 8 characters; up to 128 MiB database. Restore only while the app is closed; it restores the login password from backup time. Google/Moodle connections may need reconnecting on another machine or Windows account.")}</p>
    <details className="field-help"><summary>{t("איך משחזרים גיבוי?", "How do I restore a backup?")}</summary><p>{t("סגרו את LifeOS ואת חלון ההפעלה שלו, ופתחו את Restore-LifeOS.cmd שבתיקיית האפליקציה. אשף השחזור יציג את תיקיית היעד ואת הגיבויים השמורים, יבדוק את הגיבוי עם הסיסמה ויבקש אישור להחלפת הנתונים. הוא ייצור גיבוי בטיחות לפני ההחלפה. השחזור אינו מתבצע מהמסך הזה.", "Close LifeOS and its launcher, then open Restore-LifeOS.cmd in the app folder. The recovery wizard shows the target folder and saved backups, checks the backup password and asks you to approve replacement. It creates a safety backup first. This screen does not perform a restore.")}</p></details>
    {notice && <p role="status" className="status-message">{notice}</p>}
    {error && <p role="alert" className="error-message">{error === "password_mismatch" ? t("סיסמאות הגיבוי אינן תואמות.", "Backup passwords do not match.") : error === "backup_password_minimum_8" ? t("יש לבחור סיסמת גיבוי באורך 8 תווים לפחות.", "Choose a backup password of at least 8 characters.") : error.includes("large") ? t("הקובץ חורג ממגבלת הגודל. הנתונים המקוריים לא השתנו.", "The file exceeds the size limit. Original data is unchanged.") : t("הפעולה לא הושלמה. נסה לרענן את הרשימה ולבדוק את הקובץ שהורד.", "Operation could not complete. Refresh the list and check any downloaded file.")}</p>}
    <div className="panel-heading"><h3>{t("גיבויים מוצפנים במחשב", "Encrypted backups on this computer")}</h3><Button variant="ghost" size="small" disabled={busy} onClick={async () => { setError(""); try { await load(); } catch (error) { failed(error); } }}><RefreshCw size={15} />{t("רענון רשימת גיבויים", "Refresh backup list")}</Button></div>
    {loaded && backups.length === 0 && <p className="muted">{t("עדיין אין גיבויים מוצפנים.", "No encrypted backups yet.")}</p>}
    <ul className="recovery-list">{backups.map(backup => <li key={backup.id}><span><time dateTime={backup.created_at}>{new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(backup.created_at))}</time><small>{(backup.size / 1024 / 1024).toFixed(2)} MiB</small></span><div className="google-actions"><Button variant="ghost" size="small" disabled={busy} onClick={() => setInspecting(backup.id)}>{t("בדיקת תקינות", "Check integrity")}</Button><Button variant="secondary" size="small" disabled={busy} onClick={() => void download(`backups/${backup.id}`, `LifeOS-${backup.id}.lifeosbackup`)}><Download size={15} />{t("הורדת גיבוי", "Download backup")}</Button></div></li>)}</ul>
    <p className="field-help">{t("מוצגים עד 20 הגיבויים האחרונים. גיבויים ידניים אינם נמחקים אוטומטית. תזמון ומדיניות גיבויים אוטומטיים מוגדרים בנפרד; אין שמירה בענן. לשחזור יש לסגור את LifeOS ולהשתמש בכלי השחזור המקומי.", "Shows the latest 20 backups. Manual backups are never automatically deleted. Automatic scheduling and retention are configured separately; no cloud storage. Restore using the local recovery tool while LifeOS is closed.")}</p>
    {inspecting && <BackupInspection id={inspecting} csrf={csrf} settings={settings} t={t} onClose={() => setInspecting(null)} onUnauthorized={onUnauthorized} />}
    <ScheduledBackupSettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} />
    <div className="recovery-export"><h3>{t("ייצוא משימות ויומן אישי", "Export tasks and personal calendar")}</h3><p className="field-help">{t("קובץ JSON לקריאה, שאינו מוצפן. כולל משימות, אירועים אישיים והעדפות בלבד — ללא מפתחות חיבור, מיילים, אירועים מיובאים, ציונים או קובצי לימוד. לגיבוי מלא השתמש בגיבוי המוצפן.", "Readable, unencrypted JSON: tasks, personal events and preferences only. Excludes connection keys, mail, imported calendars, grades and study files. Use the encrypted backup for full recovery.")}</p><Button variant="secondary" disabled={busy} onClick={() => void download("export", "LifeOS-personal-export.json")}><Download size={16} />{t("הורדת ייצוא JSON", "Download JSON export")}</Button></div>
  </section>;
}
