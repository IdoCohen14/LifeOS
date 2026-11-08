import { Check, MoreHorizontal, Pencil, Trash2, ListTodo, Plus } from "lucide-react";
import { dueDay, formatDay, formatTime } from "@/lib/dates";
import type { Settings, Task, Translate } from "@/lib/types";
import { Button } from "./ui/button";

export function TaskList({
  tasks,
  settings,
  today,
  now,
  t,
  onEdit,
  onToggle,
  onDelete,
  onAdd,
  busy,
  compact = false,
}: {
  tasks: Task[];
  settings: Settings;
  today: string;
  now: Date;
  t: Translate;
  onEdit: (task: Task) => void;
  onToggle: (task: Task) => void;
  onDelete: (task: Task) => void;
  onAdd: () => void;
  busy: boolean;
  compact?: boolean;
}) {
  if (!tasks.length)
    return (
      <div className="empty-state">
        <ListTodo size={30} aria-hidden="true" />
        <h3>{t("מקום למשהו חשוב", "Room for what matters")}</h3>
        <p>
          {t(
            "הוסיפו משימה ראשונה והתחילו בקצב שלכם.",
            "Add your first task and take it at your pace.",
          )}
        </p>
        <Button variant="secondary" onClick={onAdd}>
          <Plus size={16} aria-hidden="true" />
          {t("הוספת משימה", "Add task")}
        </Button>
      </div>
    );
  return (
    <ul className={`task-list${compact ? " task-list-compact" : ""}`}>
      {tasks.map((task) => {
        const due = task.due ? dueDay(task.due, settings.timezone) : null;
        const overdue = due && !task.completed && (task.due!.length === 10
          ? due < today : Date.parse(task.due!) < now.getTime());
        return (
          <li
            key={task.id}
            className={`task-row ${task.completed ? "is-complete" : ""}`}
          >
            <button
              className="task-check"
              role="checkbox"
              aria-checked={task.completed}
              aria-label={`${task.completed ? t("פתיחה מחדש", "Reopen") : t("השלמה", "Complete")}: ${task.title}`}
              onClick={() => onToggle(task)}
              disabled={busy}
            >
              {task.completed && <Check size={14} aria-hidden="true" />}
            </button>
            <div className="task-content">
              <button type="button" className="record-title task-title-button" dir="auto" onClick={() => onEdit(task)} disabled={busy}>
                {task.title}
              </button>
              <div className="record-meta">
                {task.academic_id && !compact && (
                  <span className="subtle-badge">
                    {task.academic_kind === "assignment" ? t("מטלה", "Assignment")
                      : task.academic_kind === "exam" ? t("מבחן", "Exam")
                        : t("פריט אקדמי", "Academic item")}
                  </span>
                )}
                {task.academic_course_name && <span dir="auto">{task.academic_course_name}</span>}
                {(!compact || task.priority === "high") && <span className={`priority priority-${task.priority}`}>
                  <span />
                  {task.priority === "high"
                    ? t("עדיפות גבוהה", "High priority")
                    : task.priority === "low"
                      ? t("עדיפות נמוכה", "Low priority")
                      : t("עדיפות רגילה", "Normal priority")}
                </span>}
                {due && (
                  <span className={`task-due${overdue ? " overdue" : ""}`}>
                    {overdue && t("באיחור · ", "Overdue · ")}
                    <time dateTime={task.due!}>{formatDay(due, settings.language, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}{task.due!.length > 10 && <> · <bdi>{formatTime(task.due!, settings.language, settings.timezone)}</bdi></>}</time>
                  </span>
                )}
              </div>
            </div>
            <details className="record-options"><summary aria-label={`${t("אפשרויות", "Options")}: ${task.title}`}><MoreHorizontal size={20} aria-hidden="true"/></summary><div className="row-actions">
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${t("עריכה", "Edit")}: ${task.title}`}
                onClick={() => onEdit(task)}
                disabled={busy}
              >
                <Pencil size={15} aria-hidden="true" />
              </Button>
              {!task.academic_id && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`${t("מחיקה", "Delete")}: ${task.title}`}
                  onClick={() => onDelete(task)}
                  disabled={busy}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </Button>
              )}
            </div></details>
          </li>
        );
      })}
    </ul>
  );
}
