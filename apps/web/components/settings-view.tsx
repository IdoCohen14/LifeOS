"use client";
import { useState, type FormEvent } from "react";
import { LockKeyhole, Monitor, HardDrive, Unplug } from "lucide-react";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { PlanningPreferenceSettings } from "./planning-preference-settings";
import { SecretarySettings } from "./secretary-settings";
import { RecoverySettings } from "./recovery-settings";
import { MoodleSettings } from "./moodle-settings";
import { BraudeSettings } from "./braude-settings";
import { GmailSettings } from "./gmail-settings";
import { GoogleCalendarSettings } from "./google-calendar-settings";
import { AccountSecurity } from "./account-security";
import { AccountAccessSettings } from "./account-access";
import { AccountDeletionSettings } from "./account-deletion";
import { AccountRecoverySettings } from "./account-recovery-settings";

export function SettingsView({
  settings,
  t,
  onSave,
  csrf,
  onChanged,
  onUnauthorized,
  accountMode = false,
}: {
  settings: Settings;
  t: Translate;
  onSave: (settings: Settings) => Promise<void>;
  csrf: string;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
  accountMode?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      await onSave({
        display_name: String(data.get("display_name")).trim(),
        language: data.get("language") as Settings["language"],
        theme: data.get("theme") as Settings["theme"],
        timezone: String(data.get("timezone")).trim(),
      });
      setMessage(t("ההגדרות נשמרו.", "Settings saved."));
    } catch {
      setMessage(
        t(
          "השמירה נכשלה. יש לבדוק את אזור הזמן ואת החיבור לשרת.",
          "Could not save. Check the timezone and local server.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="settings-layout">
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>{t("המרחב שלך", "Your workspace")}</h2>
            <p className="muted">
              {t("התאימו את LifeOS ליום שלכם.", "Make LifeOS fit your day.")}
            </p>
          </div>
          <Monitor aria-hidden="true" size={21} />
        </div>
        <form className="form-stack settings-form" onSubmit={save}>
          <label>
            {t("איך לקרוא לך?", "Display name")}
            <input
              name="display_name"
              autoComplete="nickname"
              maxLength={80}
              defaultValue={settings.display_name}
            />
          </label>
          <div className="form-grid">
            <label>
              {t("שפה", "Language")}
              <select
                name="language"
                aria-label={t("שפה", "Language")}
                defaultValue={settings.language}
              >
                <option value="he">עברית</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              {t("מראה", "Appearance")}
              <select
                name="theme"
                aria-label={t("מראה", "Appearance")}
                defaultValue={settings.theme}
              >
                <option value="dark">{t("כהה", "Dark")}</option>
                <option value="light">{t("בהיר", "Light")}</option>
                <option value="system">{t("לפי המכשיר", "System")}</option>
              </select>
            </label>
          </div>
          <label>
            {t("אזור זמן", "Timezone")}
            <input
              name="timezone"
              dir="ltr"
              required
              defaultValue={settings.timezone}
              list="timezones"
              autoComplete="off"
            />
            <datalist id="timezones">
              {[
                "Asia/Jerusalem",
                "UTC",
                "Europe/London",
                "America/New_York",
              ].map((z) => (
                <option value={z} key={z} />
              ))}
            </datalist>
          </label>
          <p className="field-help">
            {t(
              "שינוי אזור הזמן משנה את תצוגת השעות, לא את האירועים השמורים.",
              "Changing timezone changes displayed times, not stored events.",
            )}
          </p>
          <Button type="submit" disabled={busy}>
            {busy ? t("שומר…", "Saving…") : t("שמירת הגדרות", "Save settings")}
          </Button>
          <p aria-live="polite" className="status-message">
            {message}
          </p>
        </form>
      </section>
      <details className="section-fold settings-information"><summary>{t("על המידע והאחסון", "About your data and storage")}</summary><div className="settings-aside">
        <section className="panel note-panel">
          <LockKeyhole size={23} aria-hidden="true" />
          <h2>{t("פרטי, כברירת מחדל", "Private by default")}</h2>
          <p>
            {t(
              "המידע נשמר במחשב שלך ב־SQLite. הגישה מוגנת בסיסמה ובחיבור מקומי בלבד.",
              "Your data stays in SQLite on this computer. Access uses a password and a loopback connection.",
            )}
          </p>
          <p>
            {t(
              "קובצי המידע אינם מוצפנים בשלב זה. מומלץ להפעיל הצפנת דיסק ולהגן על חשבון Windows.",
              "Data files are not encrypted in this phase. Use disk encryption and protect your Windows account.",
            )}
          </p>
        </section>
        <section className="panel note-panel">
          <HardDrive size={23} aria-hidden="true" />
          <h2>{t("מקומי וללא מנוי", "Local, without a subscription")}</h2>
          <p>
            {t(
              "המשימות והיומן פועלים בלי שירות ענן. אין פעולות רקע כשהמחשב כבוי.",
              "Tasks and calendar need no cloud service. Background work stops when this computer is off.",
            )}
          </p>
        </section>
      </div>
      </details>
      {accountMode && <details className="section-fold"><summary>{t("העדפות המזכירה והזיכרון", "Secretary and memory preferences")}</summary><SecretarySettings csrf={csrf} t={t} onChanged={onChanged} onUnauthorized={onUnauthorized}/></details>}
      <details className="section-fold"><summary>{t("העדפות תכנון", "Planning preferences")}</summary><PlanningPreferenceSettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} />
      </details>
      <details className="section-fold"><summary>{t("כניסה ואבטחה", "Access and security")}</summary>{accountMode && <AccountSecurity csrf={csrf} t={t} />}
      {accountMode && <AccountAccessSettings csrf={csrf} t={t} onUnauthorized={onUnauthorized} />}
      </details>
      <details className="section-fold"><summary>{t("גיבוי ושחזור", "Backup and restore")}</summary>{accountMode ? <AccountRecoverySettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} /> : <RecoverySettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} />}
      </details>
      {accountMode && <details className="section-fold"><summary>{t("ניהול החשבון", "Account management")}</summary><AccountDeletionSettings csrf={csrf} t={t} /></details>}
      <details className="section-fold"><summary>{t("החיבורים שלי", "My connections")}</summary><section className="panel connections-settings">
        <div className="panel-heading">
          <h2>{t("חיבורים חיצוניים", "External connections")}</h2>
          <Unplug size={20} aria-hidden="true" />
        </div>
<details className="connection-fold"><summary>Google Calendar</summary>        <GoogleCalendarSettings
          csrf={csrf}
          settings={settings}
          t={t}
          onChanged={onChanged}
          onUnauthorized={onUnauthorized}
        /></details>
<details className="connection-fold"><summary>Gmail</summary>        <GmailSettings csrf={csrf} settings={settings} t={t} onUnauthorized={onUnauthorized} /></details>
<details className="connection-fold"><summary>Moodle</summary>        <MoodleSettings csrf={csrf} settings={settings} t={t} onChanged={onChanged} onUnauthorized={onUnauthorized} /></details>
<details className="connection-fold"><summary>{t("תחנת המידע", "Student portal")}</summary>        <BraudeSettings csrf={csrf} settings={settings} t={t} onChanged={onChanged} onUnauthorized={onUnauthorized} /></details>
        <p className="field-help">
          {t(
            "אפשר לנהל מכאן את החיבורים והגיבויים. העדפות ההתראות נמצאות במרכז ההתראות.",
            "Manage connections and backups here. Notification preferences are in the notification center.",
          )}
        </p>
      </section></details>
    </div>
  );
}
