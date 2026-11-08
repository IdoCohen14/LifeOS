"use client";

import Link from "next/link";
import { ArrowUpLeft, Clock3, GraduationCap, ListTodo, MapPin } from "lucide-react";
import { dayKey, dueDay, eventOnDay, formatDay, formatTime, shiftDay } from "@/lib/dates";
import { classRoom, isClassEvent } from "@/lib/class-schedule";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";
import type { Course } from "@/lib/academic";

export function DayDashboard({ tasks, events, now, settings, t, showUpcoming = true }: {
  showUpcoming?: boolean; tasks: Task[]; events: CalendarEvent[]; now: Date; settings: Settings; t: Translate;
}) {
  const today = dayKey(now, settings.timezone);
  const open = tasks.filter(task => !task.completed);
  const due = open.filter(task => task.due && dueDay(task.due, settings.timezone) <= today);
  const days = Array.from({ length: 7 }, (_, index) => shiftDay(today, index));
  return <section className="day-dashboard" aria-label={t("לוח היום שלי", "My day dashboard")}>
    <div className="day-board">
      <div className="day-board-heading"><div>
        <p>{formatDay(today, settings.language, { month: "long", year: "numeric" })}</p>
        <h2>{formatDay(today, settings.language, { weekday: "long" })}</h2>
      </div><span className="day-stamp" aria-hidden="true">{Number(today.slice(-2))}</span></div>
      <nav className="day-ribbon" aria-label={t("שבעת הימים הקרובים", "Next seven days")}>
        {days.map(day => <Link key={day} href={`/?view=calendar&day=${day}`} className={day === today ? "is-today" : undefined}
          aria-label={formatDay(day, settings.language, { weekday: "long", day: "numeric", month: "long" })}>
          <span>{formatDay(day, settings.language, { weekday: "short" })}</span><strong>{Number(day.slice(-2))}</strong>
          <i className={events.some(event => eventOnDay(event, day, settings.timezone)) ? "has-events" : undefined} aria-hidden="true" />
        </Link>)}
      </nav>
    </div>
    {showUpcoming && <UpcomingEvent tasks={tasks} events={events} now={now} settings={settings} t={t} />}
    <div className="day-metrics">
      <Link href="/?view=tasks" className="day-metric metric-blue"><ListTodo size={20} aria-hidden="true"/><strong>{open.length}</strong><span>{t("משימות פתוחות", "Open tasks")}</span></Link>
      <Link href="/?view=tasks" className="day-metric metric-peach"><Clock3 size={20} aria-hidden="true"/><strong>{due.length}</strong><span>{t("להיום ובאיחור", "Due or overdue")}</span></Link>
      <Link href="/?view=academic" className="day-metric metric-mint"><GraduationCap size={20} aria-hidden="true"/><strong>{open.filter(task => task.academic_kind === "assignment").length}</strong><span>{t("מטלות להגשה", "Assignments")}</span></Link>
    </div>
  </section>;
}


export function UpcomingEvent({ events, now, settings, t, courses = [] }: {
  tasks: Task[]; events: CalendarEvent[]; now: Date; settings: Settings; t: Translate; courses?: Course[];
}) {
  const today = dayKey(now, settings.timezone);
  const schedule = events.filter(event => eventOnDay(event, today, settings.timezone));
  const next = schedule.filter(event => !event.all_day && Date.parse(event.end) > now.getTime())
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start))[0];
  const room = next && isClassEvent(next) ? classRoom(next) : null;
  const isClass = !!next && isClassEvent(next);
  const instructor = courses.find(course => course.id === next?.course_id)?.instructor;
  return (<div className={`day-focus calm-next ${next ? "" : "day-focus-empty"}`}>
      <div className="day-focus-label"><Clock3 size={17} aria-hidden="true"/>{isClass ? t("השיעור הבא", "Next class") : t("הבא ביומן", "Up next")}</div>
      {next ? <Link href={isClassEvent(next) ? "/?view=timetable" : `/?view=calendar&day=${today}`} className="day-focus-event">
        <span className="day-focus-time">
          <time dateTime={next.start}>{formatTime(next.start, settings.language, settings.timezone)}</time><span>–{formatTime(next.end, settings.language, settings.timezone)}</span>
          </span><span className="calm-next-copy"><strong dir="auto">{next.title}</strong>
        {isClass && <span className="day-focus-room"><MapPin size={15} aria-hidden="true"/><bdi>{room ?? t("חדר לא צוין במקור", "Room not provided by source")}</bdi></span>}
        {isClass && <span className="calm-next-instructor" dir="auto">{instructor || t("מרצה לא צוין במידע הזמין", "Lecturer not in available data")}</span>}
        </span><span className="calm-next-open">{isClass ? t("מערכת השעות שלי", "My timetable") : t("פתיחת האירוע", "Open event")}<ArrowUpLeft size={16} aria-hidden="true"/></span>
      </Link> : <div className="day-focus-event"><strong>{t("אין עוד אירועים מתוזמנים להיום", "No more timed events today")}</strong></div>}
    </div>);
}
