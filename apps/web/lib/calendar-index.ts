import { Temporal } from "@js-temporal/polyfill";
import { dueDay } from "./dates";

type Span = { start: string; end: string; all_day: boolean };

export function calendarIndex<T extends Span>(
  events: T[],
  tasks: { due: string | null; completed: boolean }[],
  days: string[],
  zone: string,
) {
  const indexed = new Map<string, T[]>();
  const dueCounts = new Map<string, number>();
  const spans = events.map(event => ({ event,
    start: event.all_day ? null : Temporal.Instant.from(event.start).epochNanoseconds,
    end: event.all_day ? null : Temporal.Instant.from(event.end).epochNanoseconds,
  }));
  for (const day of new Set(days)) {
    const date = Temporal.PlainDate.from(day);
    const start = date.toZonedDateTime(zone).toInstant().epochNanoseconds;
    const end = date.add({ days: 1 }).toZonedDateTime(zone).toInstant().epochNanoseconds;
    indexed.set(day, spans.filter(span => span.event.all_day
      ? span.event.start <= day && span.event.end > day
      : span.start !== null && span.end !== null && span.start < end && span.end > start).map(span => span.event));
    dueCounts.set(day, 0);
  }
  for (const task of tasks) {
    if (task.completed || !task.due) continue;
    const day = dueDay(task.due, zone);
    if (dueCounts.has(day)) dueCounts.set(day, dueCounts.get(day)! + 1);
  }
  return { events: indexed, dueCounts };
}
