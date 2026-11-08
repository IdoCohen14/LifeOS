import { Temporal } from "@js-temporal/polyfill";

type Span = { start: string; end: string; all_day: boolean };
export function calendarDayParameter(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  try {
    return Temporal.PlainDate.from(value).toString() === value ? value : undefined;
  } catch {
    return undefined;
  }
}
export function dayKey(date: Date, zone: string) {
  return Temporal.Instant.from(date.toISOString())
    .toZonedDateTimeISO(zone)
    .toPlainDate()
    .toString();
}
export function localInstant(local: string, zone: string, original?: string | null) {
  // Keep an unchanged explicit instant, including its offset and sub-minute precision.
  if (original && original.length > 10 && localInput(original, zone) === local) return original;
  return Temporal.PlainDateTime.from(local)
    .toZonedDateTime(zone, { disambiguation: "reject" })
    .toInstant()
    .toString();
}
export function localInput(instant: string, zone: string) {
  return Temporal.Instant.from(instant)
    .toZonedDateTimeISO(zone)
    .toPlainDateTime()
    .toString()
    .slice(0, 16);
}
export function shiftDay(day: string, amount: number) {
  return Temporal.PlainDate.from(day).add({ days: amount }).toString();
}
export function eventOnDay(event: Span, day: string, zone: string) {
  if (event.all_day) return event.start <= day && event.end > day;
  const start = Temporal.PlainDate.from(day)
    .toZonedDateTime(zone)
    .toInstant().epochNanoseconds;
  const end = Temporal.PlainDate.from(shiftDay(day, 1))
    .toZonedDateTime(zone)
    .toInstant().epochNanoseconds;
  return Temporal.Instant.from(event.start).epochNanoseconds < end && Temporal.Instant.from(event.end).epochNanoseconds > start;
}
export function eventConflicts(
  event: Span & { id: string },
  events: (Span & { id: string })[],
) {
  if (event.all_day) return false;
  const start = Temporal.Instant.from(event.start).epochNanoseconds;
  const end = Temporal.Instant.from(event.end).epochNanoseconds;
  return events.some(
    (other) =>
      other.id !== event.id &&
      !other.all_day &&
      start < Temporal.Instant.from(other.end).epochNanoseconds &&
      end > Temporal.Instant.from(other.start).epochNanoseconds,
  );
}
export function formatDay(
  day: string,
  locale: string,
  options: Intl.DateTimeFormatOptions = {},
) {
  return new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    ...options,
  }).format(new Date(`${day}T12:00:00Z`));
}
export function formatTime(instant: string, locale: string, zone: string) {
  return new Intl.DateTimeFormat(locale, {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(instant));
}
export function dueDay(due: string, zone: string) {
  return due.length === 10 ? due : dayKey(new Date(due), zone);
}
export function monthDays(day: string) {
  const first = Temporal.PlainDate.from(day).with({ day: 1 });
  const start = first.subtract({ days: first.dayOfWeek % 7 });
  return Array.from({ length: 42 }, (_, i) =>
    start.add({ days: i }).toString(),
  );
}
export function weekDays(day: string) {
  const date = Temporal.PlainDate.from(day);
  const start = date.subtract({ days: date.dayOfWeek % 7 });
  return Array.from({ length: 7 }, (_, i) => start.add({ days: i }).toString());
}
export function shiftMonth(day: string, amount: number) {
  return Temporal.PlainDate.from(day).add({ months: amount }).toString();
}
