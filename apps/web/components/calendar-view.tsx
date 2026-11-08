"use client";
import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import {
  formatDay,
  formatTime,
  monthDays,
  shiftDay,
  shiftMonth,
  weekDays,
} from "@/lib/dates";
import type { CalendarEvent, Settings, Task, Translate } from "@/lib/types";
import { calendarIndex } from "@/lib/calendar-index";
import { Agenda } from "./agenda";
import { Button } from "./ui/button";

export function CalendarView({
  events,
  tasks,
  settings,
  today,
  initialDay,
  t,
  onEdit,
  onDelete,
  onAdd,
  busy,
}: {
  events: CalendarEvent[];
  tasks: Task[];
  settings: Settings;
  today: string;
  initialDay?: string;
  t: Translate;
  onEdit: (e: CalendarEvent) => void;
  onDelete: (e: CalendarEvent) => void;
  onAdd: (day: string) => void;
  busy: boolean;
}) {
  const [mode, setMode] = useState<"day" | "week" | "month">("month");
  const [day, setDay] = useState(initialDay ?? today);
  const [selected, setSelected] = useState(initialDay ?? today);
  const days = useMemo(() => mode === "month" ? monthDays(day) : weekDays(day), [mode, day]);
  const index = useMemo(
    () => calendarIndex(events, tasks, [...days, day, selected], settings.timezone),
    [events, tasks, days, day, selected, settings.timezone],
  );
  function move(amount: number) {
    const next =
      mode === "month"
        ? shiftMonth(day, amount)
        : shiftDay(day, amount * (mode === "week" ? 7 : 1));
    setDay(next);
    setSelected(next);
  }
  return (
    <>
      <div className="calendar-toolbar">
        <div className="toolbar-group">
          <Button
            variant="secondary"
            onClick={() => {
              setDay(today);
              setSelected(today);
            }}
          >
            {t("היום", "Today")}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => move(-1)}
            aria-label={t("הקודם", "Previous")}
          >
            <ChevronRight
              className="rtl-chevron"
              size={18}
              aria-hidden="true"
            />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => move(1)}
            aria-label={t("הבא", "Next")}
          >
            <ChevronLeft className="rtl-chevron" size={18} aria-hidden="true" />
          </Button>
          <h2>
            {formatDay(day, settings.language, {
              month: "long",
              year: "numeric",
              ...(mode === "day" ? { day: "numeric" } : {}),
            })}
          </h2>
        </div>
        <div
          className="segmented"
          aria-label={t("תצוגת יומן", "Calendar view")}
        >
          {(["day", "week", "month"] as const).map((m) => (
            <button
              key={m}
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
            >
              {m === "day"
                ? t("יום", "Day")
                : m === "week"
                  ? t("שבוע", "Week")
                  : t("חודש", "Month")}
            </button>
          ))}
        </div>
      </div>
      <section className="panel calendar-panel">
        {mode === "day" ? (
          <Agenda
            events={index.events.get(day) || []}
            allEvents={events}
            settings={settings}
            t={t}
            onEdit={onEdit}
            onDelete={onDelete}
            onAdd={() => onAdd(day)}
            busy={busy}
          />
        ) : (
          <div
            className="calendar-scroll"
            tabIndex={0}
            role="region"
            aria-label={t(
              "יומן — ניתן לגלול לרוחב",
              "Calendar — scroll horizontally",
            )}
          >
            <div
              className={`calendar-grid ${mode === "week" ? "week-grid" : ""}`}
            >
              <div className="calendar-weekdays">
                {weekDays(day).map((d) => (
                  <span key={d}>
                    {formatDay(d, settings.language, { weekday: "short" })}
                  </span>
                ))}
              </div>
              <div className="calendar-cells">
                {days.map((d) => {
                  const list = index.events.get(d) || [];
                  const due = index.dueCounts.get(d) || 0;
                  return (
                    <div
                      key={d}
                      className={`calendar-cell ${d.slice(0, 7) !== day.slice(0, 7) && mode === "month" ? "outside" : ""} ${d === selected ? "selected" : ""}`}
                    >
                      <button
                        className={`day-number ${d === today ? "today-number" : ""}`}
                        onClick={() => setSelected(d)}
                        aria-label={formatDay(d, settings.language, {
                          dateStyle: "full",
                        })}
                        aria-pressed={d === selected}
                        aria-current={d === today ? "date" : undefined}
                      >
                        {Number(d.slice(8))}
                      </button>
                      {list.slice(0, mode === "week" ? 12 : 2).map((e) => (
                        <button
                          key={e.id}
                          className="calendar-chip"
                          onClick={() => onEdit(e)}
                        >
                          <span dir="auto">{e.title}</span>
                          {!e.all_day && (
                            <small>
                              {formatTime(
                                e.start,
                                settings.language,
                                settings.timezone,
                              )}
                            </small>
                          )}
                        </button>
                      ))}
                      {due > 0 && (
                        <span className="calendar-due">
                          {due} {t("משימות ליום זה", "tasks due")}
                        </span>
                      )}
                      {list.length > (mode === "week" ? 12 : 2) && (
                        <button
                          className="text-button"
                          onClick={() => setSelected(d)}
                        >
                          +{list.length - (mode === "week" ? 12 : 2)}{" "}
                          {t("נוספים", "more")}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </section>
      {mode !== "day" && (
        <section className="panel selected-agenda">
          <div className="panel-heading">
            <h2>
              {formatDay(selected, settings.language, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}
            </h2>
            <Button variant="ghost" onClick={() => onAdd(selected)}>
              <Plus size={16} aria-hidden="true" />
              {t("אירוע חדש", "New event")}
            </Button>
          </div>
          <Agenda
            events={index.events.get(selected) || []}
            allEvents={events}
            settings={settings}
            t={t}
            onEdit={onEdit}
            onDelete={onDelete}
            onAdd={() => onAdd(selected)}
            busy={busy}
          />
        </section>
      )}
    </>
  );
}
