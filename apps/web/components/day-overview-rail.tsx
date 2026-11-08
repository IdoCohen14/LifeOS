import Link from "next/link";
import { ArrowUpLeft } from "lucide-react";
import { dayKey, dueDay, eventOnDay, formatDay, formatTime, shiftDay } from "@/lib/dates";
import { classRoom, isClassEvent } from "@/lib/class-schedule";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";

export function DayOverviewRail({ events, tasks, now, settings, t }: {
  events: CalendarEvent[]; tasks: Task[]; now: Date; settings: Settings; t: Translate;
}) {
  const today = dayKey(now, settings.timezone);
  const later = events.filter(event => !event.all_day && eventOnDay(event, today, settings.timezone) && Date.parse(event.end) > now.getTime())
    .sort((a,b) => Date.parse(a.start)-Date.parse(b.start)).slice(1,3);
  const end = shiftDay(today,7);
  const assignments = tasks.filter(task => !task.completed && task.academic_kind === "assignment" && task.due && (task.due.length === 10 || Date.parse(task.due) >= now.getTime()) && dueDay(task.due,settings.timezone) >= today && dueDay(task.due,settings.timezone) < end)
    .sort((a,b) => a.due!.localeCompare(b.due!));
  return <>
    {!!later.length && <section className="calm-later" aria-label={t("בהמשך היום", "Later today")}>
      <div className="calm-rail-heading"><h2>{t("בהמשך היום", "Later today")}</h2><Link href={`/?view=calendar&day=${today}`} aria-label={t("פתיחת היומן", "Open calendar")}><ArrowUpLeft size={16} aria-hidden="true"/></Link></div>
      <ol>{later.map(event=><li key={`${event.source}:${event.id}`}><time dateTime={event.start}>{formatTime(event.start,settings.language,settings.timezone)}</time><div><Link href={isClassEvent(event)?"/?view=timetable":`/?view=calendar&day=${today}`} dir="auto">{event.title}</Link><p>{isClassEvent(event)&&classRoom(event)&&<><bdi>{classRoom(event)}</bdi> · </>}{t("עד", "Until")} <bdi>{formatTime(event.end,settings.language,settings.timezone)}</bdi></p></div></li>)}</ol>
    </section>}
    <section className="calm-week-note" aria-label={t("השבוע בקצרה", "This week, briefly")}>
      <h2>{t("השבוע, בקצרה", "This week, briefly")}</h2>
      <p>{assignments.length?t(`${assignments.length} הגשות בשבעת הימים הקרובים.`,`${assignments.length} assignments due in the next seven days.`):t("אין הגשות בשבעת הימים הקרובים במידע השמור.","No assignments due in the next seven days in saved data.")}</p>
      {assignments[0]&&<p>{t("הקרובה ב־", "Next on ")}{formatDay(dueDay(assignments[0].due!,settings.timezone),settings.language,{weekday:"long",day:"numeric",month:"short"})}.</p>}
      <Link href="/?briefing=week">{t("פתיחת הסיכום", "Open briefing")}<ArrowUpLeft size={14} aria-hidden="true"/></Link>
    </section>
  </>;
}
