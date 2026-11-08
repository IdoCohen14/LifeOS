"use client";
import { useMemo, useState } from "react";
import { ArrowUpLeft, CalendarDays, Clock3 } from "lucide-react";
import { buildPlanning } from "@/lib/planning";
import { dueDay, formatDay, formatTime } from "@/lib/dates";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";

export function PlanningBriefing({
  tasks,
  events,
  now,
  settings,
  stale,
  t,
  onDay,
  onTask,
  onTasks,
  initialWeek = false,
}: {
  tasks: Task[];
  events: CalendarEvent[];
  now: Date;
  settings: Settings;
  stale: boolean;
  t: Translate;
  onDay: (day: string) => void;
  onTask: (task: Task) => void;
  onTasks: () => void;
  initialWeek?: boolean;
}) {
  const [week, setWeek] = useState(initialWeek);
  const plan = useMemo(
    () => buildPlanning(tasks, events, now, settings.timezone),
    [tasks, events, now, settings.timezone],
  );
  const days = week ? plan.days : plan.days.slice(0, 1);
  const peakMinutes = Math.max(1,...days.map(day=>day.minutes));
  const dayDuration=(minutes:number)=>{const total=Math.round(minutes);return `${Math.floor(total/60)}:${String(total%60).padStart(2,"0")}`;};
  const locale = settings.language === "he" ? "he-IL" : "en-GB";
  const unique = [
    ...new Map(
      days
        .flatMap((d) => d.events)
        .map((e) => [JSON.stringify([e.source ?? "personal", e.id]), e]),
    ).values(),
  ];
  const ongoing = unique
    .filter(
      (e) =>
        !e.all_day &&
        Date.parse(e.start) <= now.getTime() &&
        Date.parse(e.end) > now.getTime(),
    )
    .sort((a, b) => Date.parse(a.end) - Date.parse(b.end))[0];
  const allDay = days[0].events.find((e) => e.all_day);
  const upcoming = unique
    .filter((e) =>
      e.all_day ? e.start > days[0].day : Date.parse(e.start) > now.getTime(),
    )
    .sort(
      (a, b) =>
        (a.all_day
          ? a.start
          : dueDay(a.start, settings.timezone)
        ).localeCompare(
          b.all_day ? b.start : dueDay(b.start, settings.timezone),
        ) ||
        (a.all_day
          ? -1
          : b.all_day
            ? 1
            : Date.parse(a.start) - Date.parse(b.start)),
    )[0];
  const focus = ongoing ?? allDay ?? upcoming;
  const nextTask = days.flatMap((d) => d.deadlines)[0];
  const task = nextTask ?? plan.oldestOverdue;
  const minutes = Math.round(days.reduce((sum, d) => sum + d.minutes, 0));
  const duration = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
  const dateLabel = (day: string) =>
    formatDay(day, locale, {
      weekday: "short",
      day: "numeric",
      month: "short",
    });
  return (
    <section
      className="briefing planning-summary"
      aria-labelledby="planning-title"
    >
      <div className="planning-header">
        <div className="heading-with-icon">
          <CalendarDays size={22} aria-hidden="true" />
          <h2 id="planning-title">
            {week
              ? t("השבוע הקרוב שלך", "Your next seven days")
              : t("מבט על היום שלך", "Your day at a glance")}
          </h2>
        </div>
        <div
          className="segmented"
          role="group"
          aria-label={t("טווח הסיכום", "Briefing period")}
        >
          <button aria-pressed={!week} onClick={() => setWeek(false)}>
            {t("היום", "Today")}
          </button>
          <button aria-pressed={week} onClick={() => setWeek(true)}>
            {t("7 ימים", "7 days")}
          </button>
        </div>
      </div>
      <p className="planning-range">
        {dateLabel(days[0].day)}
        {week && ` — ${dateLabel(days[6].day)}`}
      </p>
      <p className="briefing-essential">
        <span>{unique.length} {t("ביומן", "calendar entries")}</span>
        <span>{days.reduce((sum, d) => sum + d.deadlines.length, 0)} {t("מועדים", "deadlines")}</span>
        {plan.overdue > 0 && <button className="briefing-overdue" onClick={onTasks}>{plan.overdue} {t("באיחור", "overdue")}</button>}
      </p>
      <div className="planning-focus">
        <div>
          <span className="planning-label">
            {ongoing
              ? t("מתקיים עכשיו", "Happening now")
              : allDay
                ? t("לאורך היום", "All day today")
                : t("הבא ביומן", "Next on your calendar")}
          </span>
          {focus ? (
            <button
              className="planning-link"
              onClick={() =>
                onDay(
                  ongoing || allDay
                    ? days[0].day
                    : focus.all_day
                      ? focus.start
                      : dueDay(focus.start, settings.timezone),
                )
              }
            >
              <strong dir="auto">{focus.title}</strong>
              <span>
                {dateLabel(
                  focus.all_day
                    ? allDay
                      ? days[0].day
                      : focus.start
                    : dueDay(focus.start, settings.timezone),
                )}{" "}
                ·{" "}
                {focus.all_day
                  ? t("כל היום", "All day")
                  : formatTime(focus.start, locale, settings.timezone)}{" "}
                <ArrowUpLeft size={14} aria-hidden="true" />
              </span>
            </button>
          ) : (
            <p>
              {t(
                "אין אירועים נוספים בטווח הזה",
                "Nothing else on the calendar",
              )}
            </p>
          )}
        </div>
        <div>
          <span className="planning-label">
            {nextTask
              ? t("המועד הקרוב", "Nearest deadline")
              : t("לטיפול באיחור", "Overdue to review")}
          </span>
          {task ? (
            <button className="planning-link" onClick={() => onTask(task)}>
              <strong dir="auto">{task.title}</strong>
              <span>
                {dateLabel(dueDay(task.due!, settings.timezone))}
                {task.due!.length > 10 &&
                  ` · ${formatTime(task.due!, locale, settings.timezone)}`}{" "}
                <ArrowUpLeft size={14} aria-hidden="true" />
              </span>
            </button>
          ) : (
            <p>
              {t(
                "אין מועד שמצריך טיפול כרגע",
                "No deadlines to address right now",
              )}
            </p>
          )}
        </div>
      </div>
      {stale && (
        <p className="planning-warning" role="status">
          {t("חלק מהמידע לא מעודכן. כדאי לבדוק את החיבורים.", "Some data is outdated. Check your connections.")}
        </p>
      )}
      <details className="briefing-details" key={week ? "week" : "day"}>
        <summary>{t("פירוט הסיכום", "Briefing details")}</summary>
        <p className="field-help">{t("זמן מתוזמן ביומן", "Scheduled calendar time")}: <bdi dir="ltr">{duration}</bdi></p>
      {week && (
        <div
          className="planning-days"
          role="group"
          aria-label={t("עומס לפי יום", "Daily workload")}
        >
          {days.map((d) => (
            <button
              key={d.day}
              onClick={() => onDay(d.day)}
              aria-label={`${t("פתיחה ביומן", "Open calendar")}: ${dateLabel(d.day)}`}
            >
              <strong>{dateLabel(d.day)}</strong>
              <span><bdi>{dayDuration(d.minutes)}</bdi> {t("שעות מתוזמנות","scheduled hours")}</span>
              <span className="planning-load-track" aria-hidden="true"><span style={{width:`${100*d.minutes/peakMinutes}%`}}/></span>
              <span>
                {d.events.length} {t("פריטי יומן", "calendar entries")}
              </span>
              <span>
                {d.deadlines.length} {t("מועדים", "deadlines")}
              </span>
            </button>
          ))}
        </div>
      )}
      {week&&<p className="field-help">{t("הפסים משווים זמן מתוזמן בין הימים בטווח הזה בלבד; הם אינם מדד לזמן פנוי או למאמץ למידה.","Bars compare scheduled time across these days only; they do not measure free time or study effort.")}</p>}
      {plan.undated > 0 && (
        <button className="planning-undated" onClick={onTasks}>
          {t(
            `${plan.undated} משימות פתוחות ללא מועד`,
            `${plan.undated} open tasks without a deadline`,
          )}{" "}
          <ArrowUpLeft size={14} aria-hidden="true" />
        </button>
      )}
      <p className="planning-note">
        <Clock3 size={13} aria-hidden="true" />
        {t(
          "חפיפות נספרות פעם אחת בזמן. ימים שלמים ומאמץ למשימות אינם כלולים בשעות; זה אינו חישוב זמן פנוי.",
          "Overlapping time is counted once. Hours exclude all-day items and task effort; this does not measure free time.",
        )}
      </p>
      </details>
    </section>
  );
}
