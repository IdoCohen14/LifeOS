"use client";
import { useEffect, useState } from "react";
import { ChartNoAxesColumnIncreasing } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatDay, shiftDay } from "@/lib/dates";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

type Review = {
  range_start: string;
  range_end: string;
  today: string;
  earliest_end: string;
  timezone: string;
  as_of: string;
  tracking_started_at: string;
  available_from: string;
  completed: number;
  reopened: number;
  transition_count: number;
  open_now: number;
  overdue_now: number;
  unknown_completed: number;
  days: {
    day: string;
    available: boolean;
    partial: boolean;
    completed: number;
    reopened: number;
  }[];
  recent: {
    task_id: string;
    title: string;
    completed_at: string;
    currently_completed: boolean;
  }[];
  recent_truncated: boolean;
};
type Result = {
  end?: string;
  zone: string;
  revision: unknown;
  refresh: number;
  data?: Review;
  error?: boolean;
};

export function WeeklyReview({
  settings,
  revision,
  t,
  onTask,
  onUnauthorized,
}: {
  settings: Settings;
  revision: unknown;
  t: Translate;
  onTask: (id: string) => void;
  onUnauthorized: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [end, setEnd] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<Result>();
  useEffect(() => {
    if (!open) return;
    let active = true;
    const key = { end, zone: settings.timezone, revision, refresh };
    void (async () => {
      try {
        const data = await api<Review>(
          `review/weekly${end ? `?end=${end}` : ""}`,
        );
        if (active) setResult({ ...key, data });
      } catch (error) {
        if (active) {
          if (error instanceof ApiError && error.status === 401)
            onUnauthorized();
          setResult({ ...key, error: true });
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [open, end, settings.timezone, revision, refresh, onUnauthorized]);
  const current =
    result?.end === end &&
    result?.zone === settings.timezone &&
    result?.revision === revision &&
    result?.refresh === refresh;
  const data = current ? result?.data : undefined;
  const day = (value: string) =>
    formatDay(value, settings.language, {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
  const stamp = (value: string, zone: string) =>
    new Intl.DateTimeFormat(settings.language, {
      timeZone: zone,
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  return (
    <section
      className="panel review-panel"
      aria-labelledby="weekly-review-title"
    >
      <div className="panel-heading">
        <div className="heading-with-icon">
          <ChartNoAxesColumnIncreasing size={21} aria-hidden="true" />
          <div>
            <h2 id="weekly-review-title">
              {t("סיכום ביצוע שבועי", "Weekly review")}
            </h2>
            <p className="field-help">
              {t(
                "מה סומן כהושלם ומה עדיין פתוח",
                "What was marked complete and what is still open",
              )}
            </p>
          </div>
        </div>
        <Button
          size="small"
          variant="secondary"
          aria-expanded={open}
          aria-controls="weekly-review-content"
          onClick={() => setOpen((value) => !value)}
        >
          {open
            ? t("הסתרת הסיכום", "Hide review")
            : t("הצגת הסיכום", "Show review")}
        </Button>
      </div>
      <div id="weekly-review-content" hidden={!open} className="review-content">
        {open &&
          (current && result?.error ? (
            <div>
              <p role="alert">
                {t(
                  "לא ניתן לטעון את הסיכום כרגע. אין להסיק מכך שאין פעילות.",
                  "The review is unavailable. This does not mean there was no activity.",
                )}
              </p>
              <Button
                size="small"
                variant="secondary"
                onClick={() => setRefresh((value) => value + 1)}
              >
                {t("ניסיון נוסף", "Retry")}
              </Button>
            </div>
          ) : !data ? (
            <p role="status">
              {t("טוען נתוני מעקב…", "Loading recorded activity…")}
            </p>
          ) : (
            <>
              <div className="review-toolbar">
                <strong>
                  {day(data.range_start)} — {day(shiftDay(data.range_end, -1))}
                </strong>
                <div className="google-actions">
                  <Button
                    size="small"
                    variant="ghost"
                    disabled={
                      shiftDay(shiftDay(data.range_end, -1), -7) <
                      data.earliest_end
                    }
                    onClick={() =>
                      setEnd(shiftDay(shiftDay(data.range_end, -1), -7))
                    }
                  >
                    {t("7 ימים קודמים", "Previous 7 days")}
                  </Button>
                  <Button
                    size="small"
                    variant="ghost"
                    disabled={shiftDay(data.range_end, -1) >= data.today}
                    onClick={() => {
                      const next = shiftDay(shiftDay(data.range_end, -1), 7);
                      setEnd(next > data.today ? data.today : next);
                    }}
                  >
                    {t("7 ימים הבאים", "Next 7 days")}
                  </Button>
                  <Button
                    size="small"
                    variant="secondary"
                    onClick={() => {
                      setEnd(undefined);
                      setRefresh((value) => value + 1);
                    }}
                  >
                    {t("עדכון להיום", "Refresh to today")}
                  </Button>
                </div>
              </div>
              <p className="briefing-essential">
                <span>{data.completed} {t("סומנו כהושלמו", "marked complete")}</span>
                <span>{data.open_now} {t("פתוחות כרגע", "open now")}</span>
                {data.overdue_now > 0 && <span>{data.overdue_now} {t("באיחור כרגע", "overdue now")}</span>}
              </p>
              {(data.unknown_completed > 0 || data.days.some(item => !item.available || item.partial)) && <p className="field-help">{t("הסיכום מבוסס על היסטוריית המעקב הזמינה; חלק מהנתונים חסרים.", "This review uses available tracking history; some data is missing.")}</p>}
              <details className="briefing-details" key={data.range_start}>
                <summary>{t("פירוט השבוע והמשימות", "Week and task details")}</summary>
              <dl className="planning-facts">
                <div>
                  <dt>{t("סומנו כהושלמו", "Marked complete")}</dt>
                  <dd>{data.completed}</dd>
                </div>
                <div>
                  <dt>{t("נפתחו מחדש", "Reopened")}</dt>
                  <dd>{data.reopened}</dd>
                </div>
                <div>
                  <dt>{t("פתוחות כרגע", "Open now")}</dt>
                  <dd>{data.open_now}</dd>
                </div>
                <div>
                  <dt>{t("באיחור כרגע", "Overdue now")}</dt>
                  <dd>{data.overdue_now}</dd>
                </div>
              </dl>
              <p className="field-help">
                {t("המעקב החל ב־", "Tracking began ")}
                {stamp(data.tracking_started_at, data.timezone)}.{" "}
                {t(
                  "סימונים ישנים אינם מקבלים תאריך משוער. הסיכום מתייחס לשינויי מצב, לא למדידת שעות עבודה.",
                  "Older markings are not assigned guessed dates. This reports status changes, not hours worked.",
                )}
              </p>
              {data.available_from !== data.tracking_started_at && (
                <p className="field-help">
                  {t("ההיסטוריה הזמינה מתחילה ב־", "Available history starts ")}
                  {stamp(data.available_from, data.timezone)}.{" "}
                  {t(
                    "תחילת היום הראשון בטווח עשויה להיות חלקית.",
                    "The earliest day may be partly retained.",
                  )}
                </p>
              )}
              {data.unknown_completed > 0 && (
                <p className="review-note">
                  {t(
                    `${data.unknown_completed} משימות נמצאות בהושלמו ללא תאריך בהיסטוריה הזמינה; הן לא שויכו לתאריכי הסיכום.`,
                    `${data.unknown_completed} tasks are complete without a timestamp in the available history; they were not assigned to review dates.`,
                  )}
                </p>
              )}
              <ul
                className="review-days"
                aria-label={t("שינויים לפי יום", "Daily status changes")}
              >
                {data.days.map((item) => (
                  <li key={item.day}>
                    <strong>{day(item.day)}</strong>
                    {!item.available ? (
                      <span>{t("אין נתוני מעקב", "No tracking data")}</span>
                    ) : (
                      <>
                        <span>
                          {item.completed}{" "}
                          {t("סומנו כהושלמו", "marked complete")}
                        </span>
                        <span>
                          {item.reopened} {t("נפתחו מחדש", "reopened")}
                        </span>
                        {item.partial && (
                          <small>{t("מעקב חלקי", "Partial tracking")}</small>
                        )}
                      </>
                    )}
                  </li>
                ))}
              </ul>
              <p className="field-help">
                {t(
                  "הסיכום הכולל סופר משימות ייחודיות. משימה שהושלמה בכמה ימים יכולה להופיע בכל אחד מהם. פתוחות ואיחורים משקפים את המצב כרגע.",
                  "Period totals count unique tasks; a task completed on multiple days can appear on each day. Open and overdue totals reflect now.",
                )}
              </p>
              {data.recent.length > 0 ? (
                <ul className="review-recent">
                  {data.recent.map((item) => (
                    <li key={item.task_id}>
                      <button
                        className="planning-link"
                        onClick={() => onTask(item.task_id)}
                      >
                        <strong dir="auto">{item.title}</strong>
                        <span>
                          {stamp(item.completed_at, data.timezone)} ·{" "}
                          {item.currently_completed
                            ? t("הושלמה", "Complete")
                            : t("פתוחה כרגע", "Open now")}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>
                  {t(
                    "לא תועדו סימוני השלמה בטווח הזה.",
                    "No completion markings were recorded in this period.",
                  )}
                </p>
              )}
              {data.recent_truncated && (
                <p className="field-help">
                  {t(
                    "מוצגות עד 10 משימות שהושלמו לאחרונה בטווח.",
                    "Showing up to 10 recently completed tasks in the period.",
                  )}
                </p>
              )}
              <p className="field-help">
                {t("נכון ל־", "As of ")}
                {stamp(data.as_of, data.timezone)} · {data.timezone}
              </p>
              </details>
            </>
          ))}
      </div>
    </section>
  );
}
