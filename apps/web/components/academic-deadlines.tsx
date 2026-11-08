"use client";
import { useId, useMemo, useState, type ReactNode } from "react";
import { CalendarDays, Check } from "lucide-react";
import { academicDeadlines, academicOverdue, type DeadlineStatus, type DeadlinePeriod } from "@/lib/academic-deadlines";
import { dueDay, formatDay, formatTime } from "@/lib/dates";
import type { AcademicItem, Course } from "@/lib/academic";
import type { Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function AcademicDeadlines({ items, courses, term, settings, today, now, busy, t, onSelect, onToggle, renderPlan }: {
  items: AcademicItem[]; courses: Course[]; term: string; settings: Settings; today: string; busy: boolean; t: Translate;
  onSelect: (id: string) => void; onToggle: (item: AcademicItem) => void;
  renderPlan?: (item: AcademicItem) => ReactNode;
  now: Date;
}) {
  const heading = useId();
  const [status, setStatus] = useState<DeadlineStatus>("open");
  const [period,setPeriod]=useState<DeadlinePeriod>("all");
  const [limit, setLimit] = useState(5);
  const list = useMemo(() => academicDeadlines(items,courses,term,status,"assignment",settings.timezone,period,now),[items,courses,term,status,settings.timezone,period,now]);
  const courseMap = useMemo(() => new Map(courses.map(course=>[course.id,course])),[courses]);
  return <section className="panel academic-deadlines" aria-labelledby={heading}>
    <div className="panel-heading">
      <div className="heading-with-icon"><CalendarDays size={22} aria-hidden="true"/><div>
        <h2 id={heading}>{t("מטלות להגשה", "Assignments to submit")}</h2>
        <p className="field-help">{t("מה צריך להגיש, ומתי.", "What’s due, and when.")}</p>
      </div></div>
      <span className="subtle-badge" role="status">{status === "open" ? t(`${list.length} פריטים פתוחים`,`${list.length} open items`) : t(`${list.length} פריטים`,`${list.length} items`)}</span>
    </div>
    <details className="simple-filters"><summary>{t("סינון", "Filter")}<span>{t(status === "open" ? "פתוחים" : status === "completed" ? "הושלמו" : "הכול", status === "open" ? "Open" : status === "completed" ? "Completed" : "All")}{period !== "all" ? t(" · טווח נבחר", " · Selected period") : ""}</span></summary><div className="deadline-filters">
      <label>{t("מצב הפריטים","Item status")}<select value={status} onChange={e=>{setStatus(e.target.value as DeadlineStatus);setLimit(5);}}>
        <option value="open">{t("פתוחים","Open")}</option><option value="completed">{t("הושלמו","Completed")}</option><option value="all">{t("הכול","All")}</option>
      </select></label>
      <label>{t("טווח המועדים","Deadline period")}<select value={period} onChange={e=>{setPeriod(e.target.value as DeadlinePeriod);setLimit(5);}}>
        <option value="all">{t("כל המועדים","All deadlines")}</option><option value="overdue">{t("באיחור","Overdue")}</option><option value="today">{t("היום","Today")}</option><option value="week">{t("7 ימים מהיום","7 days from today")}</option>
      </select></label>
    </div>
    <p className="field-help deadline-zone"><bdi>{settings.timezone}</bdi> · {t("7 ימים כוללים את היום וששת הימים שאחריו.","Seven days includes today and the following six dates.")}</p>
    </details>
    {list.length ? <ul className="academic-list deadline-list">{list.slice(0,limit).map(item=>{
      const day = dueDay(item.due,settings.timezone), course = courseMap.get(item.course_id)!;
      const overdue = academicOverdue(item,now,settings.timezone,today);
      return <li key={item.id}>
        <button className="task-check" role="checkbox" aria-checked={item.completed} aria-label={`${item.completed?t("פתיחה מחדש","Reopen"):t("השלמה","Complete")}: ${item.title}`} disabled={busy} onClick={()=>onToggle(item)}>{item.completed&&<Check size={14} aria-hidden="true"/>}</button>
        <div className="academic-record-content">
          <strong dir="auto">{item.title}</strong>
          <p className={`record-meta${overdue?" overdue":""}`}>
            {item.kind==="exam"?t("מבחן","Exam"):t("מטלה","Assignment")} · {overdue?t("באיחור · ","Overdue · "):day===today&&!item.completed?t("היום · ","Today · "):""}
            <time dateTime={item.due}>{formatDay(day,settings.language,{dateStyle:"medium"})}{item.due.length>10&&` · ${formatTime(item.due,settings.language,settings.timezone)}`}</time>
          </p>
          <Button variant="ghost" className="deadline-course" aria-label={`${t("פתיחת קורס","Open course")}: ${course.name}`} onClick={()=>onSelect(course.id)}><span dir="auto">{course.name}</span></Button>
          {renderPlan && <details className="item-extra"><summary>{t("תכנון זמן", "Plan time")}</summary>{renderPlan(item)}</details>}
        </div>
      </li>;
    })}</ul>:<p className="deadline-empty" role="status">{t("אין פריטים שמתאימים לסינון. אפשר לשנות את הסינון או להוסיף מטלה מתוך קורס.","No items match these filters. Change the filters or add an assignment from a course.")}</p>}
    {list.length>limit&&<div className="deadline-more"><Button variant="secondary" onClick={()=>setLimit(value=>value+10)}>{t("הצגת נוספים","Show more")}</Button><span className="field-help">{t(`מוצגים ${Math.min(limit,list.length)} מתוך ${list.length}`,`Showing ${Math.min(limit,list.length)} of ${list.length}`)}</span></div>}
  </section>;
}
