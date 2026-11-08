"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Schedule = {
  daily_enabled: boolean;
  daily_time: string;
  weekly_enabled: boolean;
  weekly_day: number;
  weekly_time: string;
  timezone: string;
  last_run: number | null;
  last_error: string | null;
  last_generated_at: string | null;
};

export function BriefingScheduleSettings({
  csrf,
  t,
  onChanged,
  onUnauthorized,
}: {
  csrf: string;
  t: Translate;
  onChanged: () => Promise<void>;
  onUnauthorized?: () => void;
}) {
  const [data, setData] = useState<Schedule | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    setData(await api<Schedule>("briefings/schedule"));
  }, []);
  const failed = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) onUnauthorized?.();
      setError(
        error instanceof ApiError &&
          error.message === "briefing_schedule_ambiguous"
          ? "time"
          : "unavailable",
      );
    },
    [onUnauthorized],
  );
  useEffect(() => {
    let active = true;
    const update = async () => {
      try {
        const next = await api<Schedule>("briefings/schedule");
        if (active) setData(next);
      } catch (error) {
        if (active) failed(error);
      }
    };
    void update();
    const timer = setInterval(() => {
      void update();
    }, 30000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [failed]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setData(
        await api<Schedule>(
          "briefings/schedule",
          "PUT",
          {
            daily_enabled: form.has("daily_enabled"),
            daily_time: String(form.get("daily_time")),
            weekly_enabled: form.has("weekly_enabled"),
            weekly_day: Number(form.get("weekly_day")),
            weekly_time: String(form.get("weekly_time")),
          },
          csrf,
        ),
      );
      setNotice("saved");
      await onChanged();
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ generated: number; schedule: Schedule }>(
        "briefings/check",
        "POST",
        {},
        csrf,
      );
      setData(result.schedule);
      setNotice(result.generated ? "generated" : "none");
      await onChanged();
    } catch (error) {
      failed(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="notification-preferences">
      <summary>{t("סיכומים מתוזמנים", "Scheduled briefings")}</summary>
      <p className="field-help">
        {t(
          "סיכום יומי ושבעת הימים הקרובים, ללא סיכומי מיילים או עזרה בלימודים. השרת והמחשב צריכים לפעול; ההפקה נבדקת בערך בכל דקה.",
          "Daily and next-seven-day planning, without email summaries or tutoring. The host and server must be running; schedules are checked about every minute.",
        )}
      </p>
      {error && (
        <p role="alert" className="field-help">
          {error === "time"
            ? t(
                "השעה שנבחרה אינה חד־משמעית במעבר שעון. בחרו שעה אחרת, למשל 08:00.",
                "The chosen time is ambiguous or missing during a clock change. Choose another time, such as 08:00.",
              )
            : t(
                "לא ניתן לטעון או לשמור את התזמון. נסו שוב.",
                "Could not load or save the schedule. Please retry.",
              )}
        </p>
      )}
      {!data ? (
        <Button
          size="small"
          variant="secondary"
          onClick={() => void load().catch(failed)}
        >
          {t("טעינת התזמון", "Load schedule")}
        </Button>
      ) : (
        <>
          <p className="field-help">
            {t("אזור זמן", "Timezone")}: {data.timezone}
          </p>
          <form
            className="form-stack"
            onSubmit={save}
            key={JSON.stringify([
              data.daily_enabled,
              data.daily_time,
              data.weekly_enabled,
              data.weekly_day,
              data.weekly_time,
            ])}
          >
            <label className="notification-check">
              <input
                type="checkbox"
                name="daily_enabled"
                defaultChecked={data.daily_enabled}
              />
              {t("סיכום יומי מתוזמן", "Scheduled daily briefing")}
            </label>
            <label>
              {t("שעת הסיכום היומי", "Daily briefing time")}
              <input
                type="time"
                name="daily_time"
                required
                defaultValue={data.daily_time}
              />
            </label>
            <label className="notification-check">
              <input
                type="checkbox"
                name="weekly_enabled"
                defaultChecked={data.weekly_enabled}
              />
              {t("סיכום שבועי מתוזמן", "Scheduled weekly briefing")}
            </label>
            <div className="form-grid">
              <label>
                {t("יום הסיכום השבועי", "Weekly briefing day")}
                <select
                  name="weekly_day"
                  aria-label={t("יום הסיכום השבועי", "Weekly briefing day")}
                  defaultValue={data.weekly_day}
                >
                  {[
                    [6, "ראשון", "Sunday"],
                    [0, "שני", "Monday"],
                    [1, "שלישי", "Tuesday"],
                    [2, "רביעי", "Wednesday"],
                    [3, "חמישי", "Thursday"],
                    [4, "שישי", "Friday"],
                    [5, "שבת", "Saturday"],
                  ].map(([value, he, en]) => (
                    <option key={value} value={value}>
                      {t(String(he), String(en))}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("שעת הסיכום השבועי", "Weekly briefing time")}
                <input
                  type="time"
                  name="weekly_time"
                  required
                  defaultValue={data.weekly_time}
                />
              </label>
            </div>
            <Button type="submit" disabled={busy}>
              {t("שמירת תזמון", "Save schedule")}
            </Button>
          </form>
          <div className="google-actions">
            <Button
              size="small"
              variant="secondary"
              disabled={busy}
              onClick={() => void check()}
            >
              {t("עדכון סיכומים כעת", "Check briefings now")}
            </Button>
          </div>
          <p className="field-help">
            {t(
              "מופקים רק סיכומים שמועדם הגיע, פעם אחת לכל תקופה. אפשר להשלים את היום או השבוע הנוכחיים אחרי הפעלה מחדש; ימים קודמים אינם משוחזרים.",
              "Only due briefings are prepared, once per period. The current day/week can catch up after restart; older periods are not backfilled.",
            )}
          </p>
          {data.last_error && (
            <p role="status" className="field-help">
              {data.last_error === "briefing_resource_limit"
                ? t(
                    "הסיכום האחרון לא הוכן עקב מגבלת עיבוד; הנתונים הקודמים נשמרו.",
                    "The last briefing exceeded its processing budget; previous records were retained.",
                  )
                : data.last_error === "briefing_schedule_ambiguous"
                  ? t(
                      "יש להתאים את השעה לאזור הזמן החדש בהגדרות.",
                      "Adjust the schedule time for your new workspace timezone.",
                    )
                  : t(
                      "הכנת הסיכום האחרונה לא הושלמה.",
                      "The last briefing check did not complete.",
                    )}
            </p>
          )}
          {notice && (
            <p role="status" className="field-help">
              {notice === "saved"
                ? t("התזמון נשמר.", "Schedule saved.")
                : notice === "generated"
                  ? t(
                      "הסיכומים מוכנים במרכז ההתראות.",
                      "Briefings are ready in your notification center.",
                    )
                  : t(
                      "אין כרגע סיכומים נוספים שמועדם הגיע.",
                      "No additional briefings are due now.",
                    )}
            </p>
          )}
        </>
      )}
    </details>
  );
}
