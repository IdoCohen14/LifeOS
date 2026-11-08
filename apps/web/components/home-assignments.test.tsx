import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Task } from "@/lib/types";
import { HomeAssignments } from "./home-assignments";

afterEach(cleanup);
const base: Task = { id: "fixture", title: "Fixture", notes: "", priority: "medium", due: "2026-11-12",
  completed: false, created_at: "2026-11-01T00:00:00Z", academic_id: "item",
  academic_kind: "assignment", academic_course_name: "Course fixture" };
function show(tasks: Task[], stale = false) {
  const toggle = vi.fn();
  const rendered = render(<HomeAssignments tasks={tasks} stale={stale} settings={{ language: "en", timezone: "Asia/Jerusalem", theme: "dark", display_name: "" }}
    today="2026-11-02" now={new Date("2026-11-02T10:00:00Z")} t={(_he, en) => en}
    busy={false} onToggle={toggle} onEdit={vi.fn()} onDelete={vi.fn()} onAdd={vi.fn()} />);
  return { toggle, ...rendered };
}
it("keeps assignments visible independently of exam priorities, ordered by deadline with expansion", () => {
  const tasks = Array.from({ length: 6 }, (_, i): Task => ({ ...base, id: String(i), title: `Assignment ${i}`, due: `2026-11-${10 + i}`, priority: i === 5 ? "high" : "medium" }));
  const { toggle } = show([...tasks.reverse(), { ...base, id: "exam", title: "Exam fixture", academic_kind: "exam" }, { ...base, id: "done", title: "Done fixture", completed: true }]);
  expect(screen.getByRole("heading", { name: "Assignments to submit" })).toBeInTheDocument();
  expect(screen.getAllByRole("checkbox").map(el => el.getAttribute("aria-label"))).toEqual(Array.from({ length: 2 }, (_, i) => `Complete: Assignment ${i}`));
  expect(screen.queryByText("Exam fixture")).not.toBeInTheDocument();
  expect(screen.queryByText("Done fixture")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show more assignments" }));
  expect(screen.getAllByRole("checkbox")).toHaveLength(6);
  fireEvent.click(screen.getByRole("checkbox", { name: "Complete: Assignment 0" }));
  expect(toggle.mock.calls[0][0].id).toBe("0");
});
it("orders by local day and instant, keeping date-only at the end of its day", () => {
  show([{ ...base, id: "date", title: "Date only", due: "2026-11-12" },
    { ...base, id: "early", title: "Early", due: "2026-11-11T23:30:00Z" },
    { ...base, id: "late", title: "Late", due: "2026-11-12T15:00:00Z" }], true);
  fireEvent.click(screen.getByRole("button", { name: "Show more assignments" }));
  expect(screen.getAllByRole("checkbox").map(el => el.getAttribute("aria-label"))).toEqual(["Complete: Early", "Complete: Late", "Complete: Date only"]);
  expect(screen.getByRole("status")).toHaveTextContent("last saved data");
});
it("does not invent assignments when none exist and acknowledges completed known assignments", () => {
  const { unmount, container } = show([]);
  expect(container).toBeEmptyDOMElement(); unmount();
  show([{ ...base, completed: true }]);
  expect(screen.getByRole("status")).toHaveTextContent("marked complete");
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});
