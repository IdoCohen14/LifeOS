"use client";

import { useId, useState, type ComponentProps } from "react";
import { GraduationCap } from "lucide-react";
import { dueDay } from "@/lib/dates";
import { TaskList } from "./task-list";
import { Button } from "./ui/button";

export function HomeAssignments({ tasks, stale, ...props }: ComponentProps<typeof TaskList> & { stale: boolean }) {
  const heading = useId();
  const [limit, setLimit] = useState(2);
  const assignments = tasks.filter(task => task.academic_kind === "assignment");
  const open = assignments.filter(task => !task.completed).sort((a, b) => {
    if (!a.due || !b.due) return a.due ? -1 : b.due ? 1 : a.id.localeCompare(b.id);
    const day = dueDay(a.due, props.settings.timezone).localeCompare(dueDay(b.due, props.settings.timezone));
    if (day) return day;
    if (a.due.length === 10 || b.due.length === 10) {
      return Number(a.due.length === 10) - Number(b.due.length === 10) || a.id.localeCompare(b.id);
    }
    return Date.parse(a.due) - Date.parse(b.due) || a.id.localeCompare(b.id);
  });
  if (!assignments.length) return null;
  return <section className="panel" aria-labelledby={heading}>
    <div className="panel-heading">
      <div className="heading-with-icon"><GraduationCap size={20} aria-hidden="true" />
        <h2 id={heading}>{props.t("מטלות להגשה", "Assignments to submit")}</h2>
      </div>
      <span className="count-badge">{open.length}</span>
    </div>
    <p className="field-help">{props.t("לפי מועד ההגשה. סימון בוצע אינו מגיש במכללה.", "Earliest deadline first. Marking complete does not submit to your institution.")}</p>
    {stale && <p className="field-help" role="status">{props.t("חיבור המקור אינו מעודכן כרגע. מוצגים הנתונים האחרונים שנשמרו.", "The source connection is currently outdated. Showing the last saved data.")}</p>}
    {open.length ? <TaskList tasks={open.slice(0, limit)} {...props} />
      : <p role="status">{props.t("כל המטלות שנקלטו סומנו כבוצעו.", "All imported or entered assignments have been marked complete.")}</p>}
    {open.length > limit && <div className="panel-footer"><Button variant="ghost" size="small" onClick={() => setLimit(value => value + 5)}>
      {props.t("הצגת מטלות נוספות", "Show more assignments")}
    </Button></div>}
  </section>;
}
