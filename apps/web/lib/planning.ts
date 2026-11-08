import { Temporal } from "@js-temporal/polyfill";
import { calendarIndex } from "./calendar-index";
import { dayKey, dueDay, shiftDay } from "./dates";
import type { CalendarEvent, Task } from "./types";

const priorities = { high: 0, medium: 1, low: 2 };

// Counts describe cached records, never availability or estimated task effort.
export function buildPlanning(
  tasks: Task[],
  events: CalendarEvent[],
  now: Date,
  zone: string,
) {
  const today = dayKey(now, zone);
  const dates = Array.from({ length: 7 }, (_, i) => shiftDay(today, i));
  const seen = new Set<string>();
  const unique = events.filter((event) => {
    const key = JSON.stringify([event.source ?? "personal", event.id]);
    if (event.source === "assignment" || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const index = calendarIndex(unique, [], dates, zone);
  let undated = 0;
  const due = tasks
    .flatMap((task) => {
      if (task.completed) return [];
      if (!task.due) {
        undated++;
        return [];
      }
      const day = dueDay(task.due, zone);
      const instant = task.due.length === 10 ? Infinity : Date.parse(task.due);
      return [
        { task, day, instant, late: day < today || instant < now.getTime() },
      ];
    })
    .sort(
      (a, b) =>
        a.day.localeCompare(b.day) ||
        (a.instant === b.instant ? 0 : a.instant < b.instant ? -1 : 1) ||
        priorities[a.task.priority] - priorities[b.task.priority],
    );
  const late = due.filter((row) => row.late);
  const days = dates.map((day) => {
    const start =
      Temporal.PlainDate.from(day).toZonedDateTime(zone).epochMilliseconds;
    const end = Temporal.PlainDate.from(shiftDay(day, 1)).toZonedDateTime(
      zone,
    ).epochMilliseconds;
    const entries = index.events.get(day)!;
    const intervals = entries
      .filter((e) => !e.all_day)
      .map((e) => [
        Math.max(start, Date.parse(e.start)),
        Math.min(end, Date.parse(e.end)),
      ])
      .sort((a, b) => a[0] - b[0]);
    let total = 0,
      until = start;
    for (const [a, b] of intervals) {
      total += Math.max(0, b - Math.max(a, until));
      until = Math.max(until, b);
    }
    return {
      day,
      events: entries,
      allDay: entries.filter((e) => e.all_day).length,
      minutes: total / 60000,
      deadlines: due
        .filter((row) => !row.late && row.day === day)
        .map((row) => row.task),
    };
  });
  return { days, overdue: late.length, oldestOverdue: late[0]?.task, undated };
}
