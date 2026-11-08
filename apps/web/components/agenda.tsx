import {
  CalendarDays,
  Pencil,
  Trash2,
  Plus,
  TriangleAlert,
} from "lucide-react";
import { eventConflicts, formatTime } from "@/lib/dates";
import type { CalendarEvent, Settings, Translate } from "@/lib/types";
import { Button } from "./ui/button";
export function Agenda({
  events,
  allEvents,
  settings,
  t,
  onEdit,
  onDelete,
  onAdd,
  busy,
}: {
  events: CalendarEvent[];
  allEvents: CalendarEvent[];
  settings: Settings;
  t: Translate;
  onEdit: (event: CalendarEvent) => void;
  onDelete: (event: CalendarEvent) => void;
  onAdd: () => void;
  busy: boolean;
}) {
  if (!events.length)
    return (
      <div className="empty-state agenda-empty">
        <CalendarDays size={30} aria-hidden="true" />
        <h3>{t("היום פתוח לאפשרויות", "A little breathing room")}</h3>
        <p>
          {t(
            "אין אירועים מתוכננים. אפשר להקדיש זמן למה שחשוב.",
            "No events planned. Make time for what matters.",
          )}
        </p>
        <Button variant="secondary" onClick={onAdd}>
          <Plus size={16} aria-hidden="true" />
          {t("הוספת אירוע", "Add event")}
        </Button>
      </div>
    );
  return (
    <ul className="agenda">
      {events.map((event) => (
        <li className="agenda-row" key={event.id}>
          <div className="agenda-time" dir="auto">
            {event.all_day ? (
              t("כל היום", "All day")
            ) : (
              <>
                <strong>
                  {formatTime(
                    event.start,
                    settings.language,
                    settings.timezone,
                  )}
                </strong>
                {event.source !== "assignment" && (
                  <span>
                    {formatTime(
                      event.end,
                      settings.language,
                      settings.timezone,
                    )}
                  </span>
                )}
              </>
            )}
          </div>
          <div className="agenda-track">
            <span />
          </div>
          <div className="agenda-content">
            <span className="record-title" dir="auto">
              {event.title}
            </span>
            {event.notes && (
              <p className="record-notes" dir="auto">
                {event.notes}
              </p>
            )}
            <span className="source-label">
              {event.source === "exam"
                ? t("מבחן", "Exam")
                : event.source === "assignment"
                  ? t("מועד הגשה", "Assignment deadline")
                  : (event.source === "google" || event.source === "moodle" || event.source === "braude")
                    ? (event.source === "braude" ? t("תחנת המידע", "Student portal") : event.source === "moodle" ? "Moodle" : "Google Calendar")
                    : event.source === "timetable"
                      ? t("מערכת שעות", "Timetable")
                      : t("יומן אישי", "Personal calendar")}
            </span>
            {event.source !== "assignment" &&
              eventConflicts(
                event,
                allEvents.filter((other) => other.source !== "assignment"),
              ) && (
                <span className="overdue conflict">
                  <TriangleAlert size={14} aria-hidden="true" />
                  {t("חפיפה עם אירוע אחר", "Overlaps another event")}
                </span>
              )}
          </div>
          <div className="row-actions">
            {event.source !== "google" && event.source !== "moodle" && (
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${t("עריכה", "Edit")}: ${event.title}`}
                onClick={() => onEdit(event)}
                disabled={busy}
              >
                <Pencil size={15} aria-hidden="true" />
              </Button>
            )}
            {(event.source === "google" || event.source === "moodle" || event.source === "braude") && event.source_url && (
              <a
                className="button button-ghost button-small"
                href={event.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("מקור", "Source")}
              </a>
            )}
            {!event.course_id && event.source !== "google" && event.source !== "moodle" && (
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${t("מחיקה", "Delete")}: ${event.title}`}
                onClick={() => onDelete(event)}
                disabled={busy}
              >
                <Trash2 size={15} aria-hidden="true" />
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
