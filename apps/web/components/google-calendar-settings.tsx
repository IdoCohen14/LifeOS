"use client";
import { useCallback, useEffect, useState } from "react";
import {
  CalendarDays,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { GoogleCalendarStatus } from "@/lib/google-calendar";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";

export function GoogleCalendarSettings({
  csrf,
  settings,
  t,
  onChanged,
  onUnauthorized,
}: {
  csrf: string;
  settings: Settings;
  t: Translate;
  onChanged: () => Promise<void>;
  onUnauthorized: () => void;
}) {
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [disconnecting, setDisconnecting] = useState(false);
  const [authUrl, setAuthUrl] = useState("");
  const load = useCallback(async () => {
    setStatus(await api<GoogleCalendarStatus>("integrations/google/status"));
  }, []);
  useEffect(() => {
    void (async () => {
      try {
        await load();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) onUnauthorized();
        setError("load");
      }
    })();
  }, [load, onUnauthorized, csrf]);
  async function action(path: string, method = "POST", body?: unknown) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<GoogleCalendarStatus>(
        `integrations/google/${path}`,
        method,
        body,
        csrf,
      );
      try {
        await load();
        await onChanged();
      } catch {
        setError("saved_refresh");
      }
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onUnauthorized();
      setError(error instanceof ApiError ? error.message : "unavailable");
      throw error;
    } finally {
      setBusy(false);
    }
  }
  function errorText(code: string) {
    if (["calendar_download_limit_exceeded", "calendar_cache_limit_exceeded", "calendar_limit_exceeded"].includes(code)) {
      return t(
        "הסנכרון נעצר בגלל כמות המידע. אפשר לבחור פחות לוחות שנה ולנסות שוב. המידע השמור נשאר ללא שינוי.",
        "Sync stopped because there is too much data. Select fewer calendars and retry. Cached data is unchanged.",
      );
    }
    if (code === "calendar_sync_timeout") {
      return t(
        "הסנכרון ארך זמן רב מדי ונעצר. נסו שוב או בחרו פחות לוחות שנה. המידע השמור נשאר ללא שינוי.",
        "Sync took too long and stopped. Retry or select fewer calendars. Cached data is unchanged.",
      );
    }
    return code === "reauthorization_required"
      ? t(
          "תוקף האישור פג או שהגישה בוטלה. יש לאשר מחדש ב־Google.",
          "Authorization expired or was revoked. Authorize again in Google.",
        )
      : code === "sync_in_progress"
        ? t(
            "סנכרון כבר מתבצע. המתינו ונסו שוב.",
            "A sync is already running. Wait and retry.",
          )
        : code === "credentials_unavailable"
          ? t(
              "לא ניתן לפענח את האישורים בחשבון מערכת ההפעלה הזה. יש להגדיר מחדש.",
              "Credentials cannot be decrypted under this OS account. Configure again.",
            )
          : code === "configuration"
            ? t(
                "יש לבחור קובץ JSON של OAuth מסוג Desktop app ולבדוק את החיבור המקומי.",
                "Choose a Desktop app OAuth JSON file and check the local connection.",
              )
            : t(
                "הפעולה נכשלה. בדקו את החיבור ואת הגדרת Google Calendar API ונסו שוב.",
                "Operation failed. Check the connection and Google Calendar API setup, then retry.",
              );
  }
  return (
    <div className="google-settings">
      <div className="google-heading">
        <CalendarDays size={25} aria-hidden="true" />
        <div>
          <h3 translate="no">Google Calendar</h3>
          <p>
            {t(
              "חיבור לקריאה בלבד · ללא שינוי אירועים ב־Google",
              "Read-only connection · No event changes in Google",
            )}
          </p>
        </div>
        <span
          className={`subtle-badge ${status?.connected ? "google-connected" : ""}`}
        >
          {status?.syncing
            ? t("מסנכרן…", "Syncing…")
            : status?.state === "expired"
              ? t("נדרש אישור מחדש", "Reauthorization required")
              : status?.connected
                ? t("מחובר", "Connected")
                : status?.configured
                  ? t("מוגדר, טרם מחובר", "Configured, not connected")
                  : t("לא מחובר", "Disconnected")}
        </span>
      </div>
      {status && !status.configured && (
        <p className="field-help">{t("החיבור ל־Google עדיין לא הוגדר על ידי מנהל האתר.", "Google connection has not been configured by the site administrator yet.")}</p>
      )}
      {status?.configured && (
        <div className="google-actions">
          <Button
            disabled={busy || status.syncing}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const result = await api<{ authorization_url: string }>(
                  "integrations/google/authorize", "POST", undefined, csrf,
                );
                setAuthUrl(result.authorization_url);
                window.location.assign(result.authorization_url);
              } catch (error) {
                if (error instanceof ApiError && error.status === 401)
                  onUnauthorized();
                setError("authorize");
              } finally {
                setBusy(false);
              }
            }}
          >
            {status.connected
              ? t("אישור גישה מחדש", "Authorize again")
              : t("חיבור Google Calendar", "Connect Google Calendar")}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              try {
                await load();
                await onChanged();
                setMessage(
                  t("מצב החיבור עודכן.", "Connection status refreshed."),
                );
              } catch {
                setError("load");
              }
            }}
          >
            <RefreshCw size={15} aria-hidden="true" />
            {t("רענון מצב", "Refresh status")}
          </Button>
          {(status.connected || status.state === "expired") && (
            <>
              <Button
                variant="secondary"
                disabled={busy || status.syncing || !status.connected}
                onClick={async () => {
                  try {
                    await action("sync");
                    setMessage(
                      t("הסנכרון הושלם.", "Synchronization completed."),
                    );
                  } catch {}
                }}
              >
                {t("סנכרון עכשיו", "Sync now")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy || status.syncing}
                onClick={() => setDisconnecting(true)}
              >
                <Unplug size={15} aria-hidden="true" />
                {t("ניתוק מקומי", "Disconnect locally")}
              </Button>
            </>
          )}
        </div>
      )}
      {authUrl && (
        <Button
          variant="ghost"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(authUrl);
              setMessage(
                t(
                  "הקישור הועתק. פתחו אותו בדפדפן חיצוני.",
                  "Link copied. Open it in your external browser.",
                ),
              );
            } catch {
              setError("clipboard");
            }
          }}
        >
          {t(
            "העתקת קישור האישור לדפדפן חיצוני",
            "Copy consent link for external browser",
          )}
        </Button>
      )}
      {status?.connected && status.calendars.length > 0 && (
        <fieldset
          className="google-calendars"
          disabled={busy || status.syncing}
        >
          <legend>
            {t("יומנים להצגה ולסנכרון", "Calendars to display and sync")}
          </legend>
          {status.calendars.map((calendar) => (
            <label className="checkbox-label" key={calendar.id}>
              <input
                type="checkbox"
                checked={calendar.selected}
                onChange={async (e) => {
                  const ids = status.calendars
                    .filter((c) =>
                      c.id === calendar.id ? e.target.checked : c.selected,
                    )
                    .map((c) => c.id);
                  try {
                    await action("calendars", "PUT", { ids });
                    setMessage(
                      t(
                        "הבחירה נשמרה. לחצו על סנכרון עכשיו לעדכון.",
                        "Selection saved. Sync now to update.",
                      ),
                    );
                  } catch {}
                }}
              />
              <span dir="auto">{calendar.name}</span>
              <small>
                <bdi>{calendar.timezone}</bdi>
              </small>
            </label>
          ))}
        </fieldset>
      )}
      {status?.last_success && (
        <p className="field-help">
          {t("סנכרון מוצלח אחרון:", "Last successful sync:")}{" "}
          {new Intl.DateTimeFormat(settings.language, {
            dateStyle: "short",
            timeStyle: "short",
            timeZone: settings.timezone,
          }).format(new Date(status.last_success * 1000))}
          {status.stale
            ? ` · ${t("המידע עשוי להיות לא מעודכן", "Data may be outdated")}`
            : ""}
        </p>
      )}
      <p className="field-help">
        <ShieldCheck size={14} aria-hidden="true" />
        {t(
          "מוצגים אירועים מ־30 הימים האחרונים ועד שנה קדימה. סנכרון אוטומטי בערך כל 10 דקות כשהמחשב והתוכנה פועלים. אישור במצב Testing עשוי לפוג לאחר 7 ימים.",
          "Events cover the past 30 days through one year ahead. Automatic sync is about every 10 minutes while this computer and app are running. Testing-mode authorization may expire after 7 days.",
        )}
      </p>
      {(error || status?.error) && (
        <p className="error-message" role="alert">
          {errorText(error || status?.error || "")}
        </p>
      )}
      <p className="status-message" aria-live="polite">
        {message}
      </p>
      {disconnecting && (
        <Modal
          open
          onClose={() => {
            if (!busy) setDisconnecting(false);
          }}
          title={t("לנתק את Google Calendar?", "Disconnect Google Calendar?")}
          description={t(
            "יוסרו האסימונים והעותק המקומי של אירועי Google בלבד.",
            "Only the tokens and local Google event cache will be removed.",
          )}
          closeLabel={t("סגירה", "Close")}
        >
          <p className="muted">
            {t(
              "האירועים ב־Google לא יימחקו. לביטול ההרשאה אצל Google השתמשו בהגדרות האבטחה של חשבון Google.",
              "Events in Google stay unchanged. Revoke access through Google Account security settings if needed.",
            )}
          </p>
          <div className="form-actions">
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                try {
                  await action("disconnect");
                  setDisconnecting(false);
                  setAuthUrl("");
                } catch {}
              }}
            >
              {t("ניתוק מקומי", "Disconnect locally")}
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setDisconnecting(false)}
            >
              {t("ביטול", "Cancel")}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
