import { describe, expect, it } from "vitest";
import {
  dayKey,
  localInstant,
  shiftDay,
  eventOnDay,
  eventConflicts,
} from "./dates";

describe("calendar semantics", () => {
  it("uses Jerusalem across midnight and DST boundaries", () => {
    expect(dayKey(new Date("2026-10-24T22:30:00Z"), "Asia/Jerusalem")).toBe(
      "2026-10-25",
    );
    expect(localInstant("2026-10-25T10:00", "Asia/Jerusalem")).toBe(
      "2026-10-25T08:00:00Z",
    );
  });
  it("rejects missing and ambiguous local times", () => {
    expect(() => localInstant("2026-03-27T02:30", "Asia/Jerusalem")).toThrow();
    expect(() => localInstant("2026-10-25T01:30", "Asia/Jerusalem")).toThrow();
  });
  it("keeps date-only entries and exclusive ends", () => {
    const e = { start: "2026-10-25", end: "2026-10-27", all_day: true };
    expect(eventOnDay(e, "2026-10-25", "Asia/Jerusalem")).toBe(true);
    expect(eventOnDay(e, "2026-10-26", "Asia/Jerusalem")).toBe(true);
    expect(eventOnDay(e, "2026-10-27", "Asia/Jerusalem")).toBe(false);
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("detects overlap but allows adjacent events", () => {
    const a = {
      id: "a",
      start: "2026-10-25T08:00:00Z",
      end: "2026-10-25T09:00:00Z",
      all_day: false,
    };
    const b = {
      id: "b",
      start: "2026-10-25T09:00:00Z",
      end: "2026-10-25T10:00:00Z",
      all_day: false,
    };
    expect(eventConflicts(a, [a, b])).toBe(false);
    expect(
      eventConflicts(a, [a, { ...b, start: "2026-10-25T08:59:00Z" }]),
    ).toBe(true);
  });
});
