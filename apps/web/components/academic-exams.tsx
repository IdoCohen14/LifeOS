"use client";

import { useId, useState, type ReactNode } from "react";
import { academicDeadlines } from "@/lib/academic-deadlines";
import { dayKey, dueDay, formatDay, formatTime } from "@/lib/dates";
import type { AcademicItem, Course } from "@/lib/academic";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function AcademicExams({ items, courses, term, settings, now, t, onSelect, renderActions }: {
  items: AcademicItem[]; courses: Course[]; term: string; settings: Settings; now: Date; t: Translate;
  onSelect?: (id: string) => void; renderActions?: (item: AcademicItem) => ReactNode;
}) {
  const heading = useId();
  const [limit, setLimit] = useState(5);
  const today = dayKey(now, settings.timezone);
  // A legacy task-completion flag does not cancel or complete an exam date.
  const exams = academicDeadlines(items, courses, term, "all", "exam", settings.timezone, "all", now);
  const upcoming = exams.filter(item => dueDay(item.due, settings.timezone) >= today);
  const past = exams.filter(item => dueDay(item.due, settings.timezone) < today);
  const courseMap = new Map(courses.map(course => [course.id, course]));
  function rows(values: AcademicItem[]) {
    return <ul className="academic-list deadline-list exam-list">{values.map(item => {
      const course = courseMap.get(item.course_id)!;
      return <li key={item.id}><div className="academic-record-content">
        <strong dir="auto">{item.title}</strong>
        <p className="record-meta"><time dateTime={item.due}>{formatDay(dueDay(item.due, settings.timezone), settings.language, {dateStyle:"medium"})}{item.due.length > 10 && ` · ${formatTime(item.due, settings.language, settings.timezone)}`}</time></p>
        {onSelect ? <Button variant="ghost" className="deadline-course" aria-label={`${t("פתיחת קורס", "Open course")}: ${course.name}`} onClick={() => onSelect(course.id)}>{course.name}</Button> : <span className="deadline-course" dir="auto">{course.name}</span>}
        {(item.notes || renderActions) && <details className="item-extra"><summary>{t("פרטי המבחן", "Exam details")}</summary>{item.notes && <p dir="auto">{item.notes}</p>}{renderActions?.(item)}</details>}
      </div></li>;
    })}</ul>;
  }
  return <section className="panel academic-deadlines academic-exams" aria-labelledby={heading}>
    <div className="panel-heading"><h2 id={heading}>{t("מבחנים", "Exams")}</h2><span className="subtle-badge">{upcoming.length}</span></div>
    {upcoming.length ? rows(upcoming.slice(0, limit)) : <p className="deadline-empty">{t("אין מבחנים קרובים ברשימה.", "No upcoming exams in this list.")}</p>}
    {upcoming.length > limit && <div className="panel-footer"><Button variant="ghost" onClick={() => setLimit(value => value + 10)}>{t("מבחנים נוספים", "More exams")}</Button></div>}
    {!!past.length && <details className="past-exams"><summary>{t(`מבחנים שעברו (${past.length})`, `Past exams (${past.length})`)}</summary>{rows(past)}</details>}
  </section>;
}
