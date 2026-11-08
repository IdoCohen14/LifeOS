import { expect, test } from "vitest";
import { calendarIndex } from "./calendar-index";
import { eventConflicts, eventOnDay } from "./dates";

test("a microsecond event after midnight remains visible in grid and daily views", () => {
  const event = { id: "precise", start: "2026-11-04T00:00:00.000001+02:00", end: "2026-11-04T00:00:00.000002+02:00", all_day: false };
  expect(calendarIndex([event], [], ["2026-11-04"], "Asia/Jerusalem").events.get("2026-11-04")).toEqual([event]);
  expect(eventOnDay(event, "2026-11-04", "Asia/Jerusalem")).toBe(true);
});

test("exclusive midnight ends and microsecond crossing are distinguished", () => {
  const crossing = { id: "crossing", start: "2026-11-03T23:59:59.999999+02:00", end: "2026-11-04T00:00:00.000001+02:00", all_day: false };
  const exclusive = { ...crossing, id: "exclusive", end: "2026-11-04T00:00:00+02:00" };
  const result = calendarIndex([crossing, exclusive], [], ["2026-11-03", "2026-11-04"], "Asia/Jerusalem");
  expect(result.events.get("2026-11-03")).toEqual([crossing, exclusive]);
  expect(result.events.get("2026-11-04")).toEqual([crossing]);
  expect(eventOnDay(crossing, "2026-11-04", "Asia/Jerusalem")).toBe(true);
  expect(eventOnDay(exclusive, "2026-11-04", "Asia/Jerusalem")).toBe(false);
});

test("overlap uses complete explicit instants and keeps adjacent ranges separate", () => {
  const event = { id: "a", start: "2026-11-04T00:00:00.000001+02:00", end: "2026-11-04T00:00:00.000003+02:00", all_day: false };
  const overlap = { ...event, id: "b", start: "2026-11-04T00:00:00.000002+02:00" };
  expect(eventConflicts(event, [overlap])).toBe(true);
  expect(eventConflicts(event, [{ ...overlap, start: event.end, end: "2026-11-04T00:00:00.000004+02:00" }])).toBe(false);
});

test("calendar index preserves exclusive ends, DST days and date-only deadlines", () => {
  const events = [
    { id: "dst", start: "2026-10-24T23:30:00+03:00", end: "2026-10-25T01:30:00+02:00", all_day: false },
    { id: "midnight", start: "2026-10-25T23:00:00+02:00", end: "2026-10-26T00:00:00+02:00", all_day: false },
    { id: "all-day", start: "2026-10-24", end: "2026-10-26", all_day: true },
  ];
  const tasks = [
    { due: "2026-10-25", completed: false },
    { due: "2026-10-24T22:30:00Z", completed: false },
    { due: "2026-10-25", completed: true },
    { due: null, completed: false },
  ];
  const result = calendarIndex(events, tasks, ["2026-10-24", "2026-10-25", "2026-10-26"], "Asia/Jerusalem");
  expect(result.events.get("2026-10-24")?.map(e => e.id)).toEqual(["dst", "all-day"]);
  expect(result.events.get("2026-10-25")?.map(e => e.id)).toEqual(["dst", "midnight", "all-day"]);
  expect(result.events.get("2026-10-26")).toEqual([]);
  expect(result.dueCounts.get("2026-10-25")).toBe(2);
  expect(result.dueCounts.get("2026-10-24")).toBe(0);
  expect(events).toHaveLength(3);
});
