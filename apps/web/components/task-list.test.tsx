import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Task } from "@/lib/types";
import { TaskList } from "./task-list";

afterEach(cleanup);
const task: Task = { id: "fixture", title: "Lab fixture", notes: "", priority: "high",
  due: "2026-11-12T15:00:00Z", completed: false, created_at: "2026-11-01T00:00:00Z",
  academic_id: "item-fixture", academic_course_id: "course-fixture",
  academic_kind: "assignment", academic_course_name: "Operating Systems fixture" };
function show(value: Task, now: string) {
  const toggle = vi.fn();
  render(<TaskList tasks={[value]} settings={{ language: "en", timezone: "Asia/Jerusalem", theme: "dark", display_name: "" }}
    today="2026-11-12" now={new Date(now)} t={(_he, en) => en} busy={false}
    onToggle={toggle} onEdit={vi.fn()} onDelete={vi.fn()} onAdd={vi.fn()} />);
  return toggle;
}
it("shows course, assignment kind and exact Jerusalem deadline with a working checkbox", () => {
  const toggle = show(task, "2026-11-12T14:59:00Z");
  expect(screen.getByText("Operating Systems fixture")).toHaveAttribute("dir", "auto");
  expect(screen.getByText("Assignment")).toBeInTheDocument();
  expect(screen.getByText("17:00")).toBeInTheDocument();
  expect(document.querySelector("time")).toHaveAttribute("dateTime", task.due);
  expect(screen.queryByText(/Overdue/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "Complete: Lab fixture" }));
  expect(toggle).toHaveBeenCalledWith(task);
});
it("marks a timed deadline overdue after its exact time on the same day", () => {
  show(task, "2026-11-12T15:01:00Z");
  expect(screen.getByText(/Overdue/)).toBeInTheDocument();
});
it("keeps date-only deadlines without a fabricated time and labels exams separately", () => {
  show({ ...task, due: "2026-11-12", academic_kind: "exam" }, "2026-11-12T19:00:00Z");
  expect(screen.getByText("Exam")).toBeInTheDocument();
  expect(document.querySelector("time")).not.toHaveTextContent(/\d\d:\d\d/);
  expect(document.querySelector("time")).toHaveAttribute("dateTime", "2026-11-12");
  expect(screen.queryByText(/Overdue/)).not.toBeInTheDocument();
});
