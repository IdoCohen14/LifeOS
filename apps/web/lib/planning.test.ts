import { expect, it } from "vitest";
import { buildPlanning } from "./planning";
import { calendarDayParameter } from "./dates";
import type { CalendarEvent, Task } from "./types";

const now = new Date("2026-10-26T10:00:00Z");
const zone = "Asia/Jerusalem";
const task = (id: string, due: string | null, completed = false): Task => ({
  id,
  due,
  completed,
  title: id,
  notes: "",
  priority: "medium",
  created_at: now.toISOString(),
});
const event = (
  id: string,
  start: string,
  end: string,
  all_day = false,
  source: CalendarEvent["source"] = "personal",
): CalendarEvent => ({
  id,
  start,
  end,
  all_day,
  source,
  title: id,
  notes: "",
  created_at: now.toISOString(),
});

it("separates overdue, remaining deadlines, completed and undated work", () => {
  const result = buildPlanning(
    [
      task("late-date", "2026-10-25"),
      task("late-time", "2026-10-26T09:00:00Z"),
      task("today", "2026-10-26"),
      task("next", "2026-10-27"),
      task("outside", "2026-11-02"),
      task("done", "2026-10-26", true),
      task("undated", null),
    ],
    [],
    now,
    zone,
  );
  expect(result.overdue).toBe(2);
  expect(result.undated).toBe(1);
  expect(result.days.map((d) => d.deadlines.length)).toEqual([
    1, 1, 0, 0, 0, 0, 0,
  ]);
  expect(result.days[0].deadlines[0].id).toBe("today");
});

it("unions booked time, clips midnight, excludes assignment markers and respects exclusive all-day ends", () => {
  const events = [
    event("a", "2026-10-26T07:00:00Z", "2026-10-26T09:00:00Z"),
    event("b", "2026-10-26T08:00:00Z", "2026-10-26T10:00:00Z"),
    event("c", "2026-10-26T10:00:00Z", "2026-10-26T11:00:00Z"),
    event("night", "2026-10-26T21:00:00Z", "2026-10-26T23:00:00Z"),
    event(
      "deadline",
      "2026-10-26T12:00:00Z",
      "2026-10-26T12:01:00Z",
      false,
      "assignment",
    ),
    event("all", "2026-10-26", "2026-10-27", true),
  ];
  const before = JSON.stringify(events);
  const result = buildPlanning([], events, now, zone);
  expect(result.days[0].minutes).toBe(300);
  expect(result.days[1].minutes).toBe(60);
  expect(result.days[0].allDay).toBe(1);
  expect(result.days[1].allDay).toBe(0);
  expect(result.days[0].events).toHaveLength(5);
  expect(JSON.stringify(events)).toBe(before);
});

it("uses elapsed time on a 25-hour Jerusalem DST day and preserves provider identity", () => {
  const full = event("same", "2026-10-24T21:00:00Z", "2026-10-25T22:00:00Z");
  const result = buildPlanning(
    [],
    [full, full, { ...full, source: "google" }],
    new Date("2026-10-24T22:30:00Z"),
    zone,
  );
  expect(result.days[0].day).toBe("2026-10-25");
  expect(result.days[0].minutes).toBe(1500);
  expect(result.days[0].events).toHaveLength(2);
});

it("sorts future deadlines by local date and instant without mutating tasks", () => {
  const tasks = [
    task("date", "2026-10-26"),
    task("later", "2026-10-26T14:00:00Z"),
    task("soon", "2026-10-26T11:00:00Z"),
  ];
  expect(
    buildPlanning(tasks, [], now, zone).days[0].deadlines.map((t) => t.id),
  ).toEqual(["soon", "later", "date"]);
  expect(tasks.map((t) => t.id)).toEqual(["date", "later", "soon"]);
});

it("accepts only valid date-only calendar navigation parameters", () => {
  expect(calendarDayParameter("2026-10-26")).toBe("2026-10-26");
  for (const input of [
    null,
    "2026-02-30",
    "2026-2-03",
    "2026-10-26T00:00Z",
    "<script>",
  ])
    expect(calendarDayParameter(input)).toBeUndefined();
});
