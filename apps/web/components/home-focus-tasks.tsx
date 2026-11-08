"use client";

import { useId, type ComponentProps } from "react";
import { ChevronLeft, ListTodo } from "lucide-react";
import { dueDay } from "@/lib/dates";
import { TaskList } from "./task-list";
import { Button } from "./ui/button";

export function HomeFocusTasks({ tasks, stale, onShowAll, ...props }: ComponentProps<typeof TaskList> & {
  stale: boolean; onShowAll: () => void;
}) {
  const heading = useId();
  const open = tasks.filter(task => !task.completed).sort((a, b) => {
    if (!a.due || !b.due) return a.due ? -1 : b.due ? 1 : a.id.localeCompare(b.id);
    const day = dueDay(a.due, props.settings.timezone).localeCompare(dueDay(b.due, props.settings.timezone));
    if (day) return day;
    if (a.due.length === 10 || b.due.length === 10) {
      return Number(a.due.length === 10) - Number(b.due.length === 10) || a.id.localeCompare(b.id);
    }
    return Date.parse(a.due) - Date.parse(b.due) || a.id.localeCompare(b.id);
  });
  return <section className="panel home-focus-tasks" aria-labelledby={heading}>
    <div className="panel-heading"><div className="heading-with-icon"><ListTodo size={19} aria-hidden="true"/><h2 id={heading}>{props.t("על מה מתקדמים היום", "What to work on today")}</h2></div><Button variant="ghost" size="small" onClick={onShowAll}>{props.t("כל המשימות", "All tasks")}<ChevronLeft className="rtl-chevron" size={15} aria-hidden="true"/></Button></div>
    {stale && <p className="field-help" role="status">{props.t("מוצגים נתוני המקור האחרונים שנשמרו.", "Showing the last saved source data.")}</p>}
    {open.length ? <TaskList {...props} tasks={open.slice(0, 3)} compact/> : <p className="field-help">{props.t("אין משימות פתוחות כרגע.", "No open tasks right now.")}</p>}
    <details className="home-task-details"><summary>{props.t("על הרשימה", "About this list")}</summary><p className="field-help">{props.t(`מוצגות עד שלוש מתוך ${open.length} משימות פתוחות, לפי מועד.`, `Showing up to three of ${open.length} open tasks, ordered by deadline.`)}</p>
      {open.some(task => task.academic_kind === "assignment") && <p className="field-help">{props.t("סימון מטלה כבוצעה אינו מגיש אותה במכללה.", "Marking an assignment complete does not submit it to your institution.")}</p>}
    </details>
  </section>;
}
