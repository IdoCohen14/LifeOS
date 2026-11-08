"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Settings, Translate } from "@/lib/types";
import { ScheduledBackupSettings } from "./scheduled-backup-settings";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

type Backup = { id: string; created_at: string; size: number };
type Preview = { id: string; counts: Record<string, number> };

export function AccountRecoverySettings({ csrf, settings, t, onUnauthorized, onRestored = () => window.location.reload() }: {
  csrf: string; settings: Settings; t: Translate; onUnauthorized: () => void; onRestored?: () => void;
}) {
  const [backups, setBackups] = useState<Backup[] | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [restorePassword, setRestorePassword] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const load = useCallback(async () => {
    const loaded = await api<Backup[]>("recovery/backups");
    setBackups(loaded);
  }, []);
  const failed = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
    setError(t("הפעולה לא הושלמה. בדקו את הסיסמה והחיבור; אם הנתונים השתנו, בדקו שוב את הגיבוי.", "Could not complete. Check the password and connection; if data changed, review the backup again."));
  }, [t, onUnauthorized]);
  useEffect(() => {
    let active = true;
    void api<Backup[]>("recovery/backups").then(
      loaded => { if (active) setBackups(loaded); },
      error => { if (active) failed(error); },
    );
    return () => { active = false; };
  }, [failed, csrf]);

  function close() {
    if (busy) return;
    setSelected(null); setRestorePassword(""); setPreview(null); setError("");
  }

  async function download(path: string, filename: string) {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/recovery/${path}`, { cache: "no-store" });
      if (!response.ok) throw new ApiError(response.status, "download_failed");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { failed(error); }
    finally { setBusy(false); }
  }

  return <section className="panel connections-settings recovery-settings" aria-label={t("גיבוי החשבון", "Account backup")}>
    <h2>{t("גיבוי החשבון", "Account backup")}</h2>
    <p>{t("גיבוי מוצפן של המשימות, היומן האישי, נתוני הלימודים, הקבצים וההיסטוריה שנשמרה בחשבון הזה. חיבורים חיצוניים ומכשירי התראות דורשים חיבור מחדש לאחר שחזור.", "Encrypted backup of this account's tasks, personal calendar, academic data, files and saved history. External connections and notification devices must be reconnected after restore.")}</p>
    <form className="recovery-form" onSubmit={async event => {
      event.preventDefault(); setError(""); setNotice("");
      if (password !== repeat) { setError(t("סיסמאות הגיבוי אינן תואמות.", "Backup passwords do not match.")); return; }
      setBusy(true);
      try {
        await api("recovery/backups", "POST", { password }, csrf);
        setPassword(""); setRepeat(""); await load();
        setNotice(t("הגיבוי המוצפן נוצר. שמרו את סיסמת הגיבוי במקום בטוח.", "Encrypted backup created. Keep its password somewhere safe."));
      } catch (error) { failed(error); }
      finally { setBusy(false); }
    }}>
      <label>{t("סיסמת גיבוי", "Backup password")}<input type="password" required minLength={8} maxLength={1024} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></label>
      <label>{t("אימות סיסמת גיבוי", "Confirm backup password")}<input type="password" required minLength={8} maxLength={1024} autoComplete="new-password" value={repeat} onChange={e => setRepeat(e.target.value)} disabled={busy} /></label>
      <Button type="submit" disabled={busy}>{t("יצירת גיבוי מוצפן", "Create encrypted backup")}</Button>
    </form>
    <p className="field-help">{t("לפחות 8 תווים. עד 64 MiB לנתוני הגיבוי. שחזור מחליף את נתוני החשבון הזה ושומר גיבוי בטיחות; סיסמת הכניסה אינה משתנה.", "At least 8 characters; up to 64 MiB of backup data. Restore replaces this account's data and saves a safety backup; your login password stays the same.")}</p>
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <div className="panel-heading"><h3>{t("הגיבויים שלך", "Your backups")}</h3><Button variant="ghost" disabled={busy} onClick={() => void load().catch(failed)}>{t("רענון הרשימה", "Refresh list")}</Button></div>
    {backups === null ? <p>{t("טוען…", "Loading…")}</p> : backups.length === 0 ? <p className="muted">{t("עדיין אין גיבויים לחשבון.", "No account backups yet.")}</p> :
      <ul className="recovery-list">{backups.map(backup => <li key={backup.id}>
        <span><time dateTime={backup.created_at}>{new Intl.DateTimeFormat(settings.language, { dateStyle: "short", timeStyle: "short", timeZone: settings.timezone }).format(new Date(backup.created_at))}</time><small>{(backup.size / 1024 / 1024).toFixed(2)} MiB</small></span>
        <div className="google-actions"><Button variant="secondary" disabled={busy} onClick={() => { setSelected(backup.id); setPreview(null); setRestorePassword(""); setError(""); }}>{t("בדיקה ושחזור", "Review and restore")}</Button>
        <Button variant="ghost" disabled={busy} onClick={() => void download(`backups/${backup.id}`, `LifeOS-${backup.id}.lifeosaccountbackup`)}>{t("הורדת גיבוי", "Download backup")}</Button></div>
      </li>)}</ul>}
    <ScheduledBackupSettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} />
    <div className="recovery-export"><h3>{t("ייצוא משימות ויומן אישי", "Export tasks and personal calendar")}</h3><p className="field-help">{t("קובץ JSON שאינו מוצפן, עם משימות, אירועים אישיים והעדפות בלבד. לגיבוי הקבצים ונתוני הלימודים השתמשו בגיבוי המוצפן.", "Unencrypted JSON containing tasks, personal events and preferences only. Use encrypted backup for files and academic data.")}</p><Button variant="secondary" disabled={busy} onClick={() => void download("export", "LifeOS-personal-export.json")}>{t("הורדת ייצוא JSON", "Download JSON export")}</Button></div>
    {selected && <Modal open onClose={close} title={t("שחזור החשבון", "Restore account")} description={t("בדקו את הגיבוי לפני אישור החלפת נתוני החשבון.", "Review the backup before approving replacement of this account's data.")} closeLabel={t("סגירה", "Close")}>
      {!preview ? <form className="form-stack" onSubmit={async event => {
        event.preventDefault(); setBusy(true); setError("");
        try { setPreview(await api<Preview>(`recovery/backups/${selected}/restore-preview`, "POST", { password: restorePassword }, csrf)); }
        catch (error) { failed(error); }
        finally { setBusy(false); }
      }}>
        <label>{t("סיסמת הגיבוי לשחזור", "Backup password for restore")}<input type="password" required minLength={8} maxLength={1024} autoComplete="off" value={restorePassword} onChange={e => setRestorePassword(e.target.value)} disabled={busy} /></label>
        <Button type="submit" disabled={busy}>{t("בדיקת הגיבוי", "Review backup")}</Button>
      </form> : <div className="form-stack">
        <dl><dt>{t("משימות", "Tasks")}</dt><dd>{preview.counts.tasks}</dd><dt>{t("אירועים אישיים", "Personal events")}</dt><dd>{preview.counts.events}</dd><dt>{t("קורסים", "Courses")}</dt><dd>{preview.counts.courses}</dd><dt>{t("קבצים", "Files")}</dt><dd>{preview.counts.documents}</dd></dl>
        <p>{t("אישור יחליף את נתוני החשבון בנתונים האלה. ייווצר גיבוי בטיחות, ותידרש כניסה וחיבור מחדש לשירותים ולמכשירי התראות.", "Confirmation replaces this account's data with this backup. A safety backup will be created; sign in again and reconnect services and notification devices afterwards.")}</p>
        <Button variant="danger" disabled={busy} onClick={async () => {
          setBusy(true); setError("");
          try { await api(`recovery/restore/${preview.id}/confirm`, "POST", { password: restorePassword }, csrf); setRestorePassword(""); onRestored(); }
          catch (error) { setPreview(null); failed(error); }
          finally { setBusy(false); }
        }}>{t("אישור שחזור החשבון", "Confirm account restore")}</Button>
      </div>}
      {error && <p role="alert" className="error-message">{error}</p>}
      <Button variant="ghost" disabled={busy} onClick={close}>{t("ביטול", "Cancel")}</Button>
    </Modal>}
  </section>;
}
