import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Task } from "@/lib/types";
import { HomeFocusTasks } from "./home-focus-tasks";

afterEach(cleanup);
const task = (id: string, due: string | null, completed = false): Task => ({id,title:id,due,completed,priority:"medium",notes:"",created_at:"2026-11-01T00:00:00Z"});
const props = {settings:{display_name:"",language:"en" as const,timezone:"Asia/Jerusalem",theme:"dark" as const},today:"2026-11-04",now:new Date("2026-11-04T08:00:00Z"),t:(_he:string,en:string)=>en,onEdit:vi.fn(),onToggle:vi.fn(),onDelete:vi.fn(),onAdd:vi.fn(),onShowAll:vi.fn(),busy:false,stale:false};

it("shows three real open priorities across academic and personal tasks, ordered by deadline", () => {
  const assignment={...task("Academic", "2026-11-05"),academic_kind:"assignment" as const,course_name:"Systems"};
  render(<HomeFocusTasks {...props} tasks={[task("No date",null),task("Done","2026-11-01",true),task("Later","2026-11-10"),assignment,task("Today","2026-11-04")]}/>);
  const panel=screen.getByRole("region",{name:"Your priorities"});
  const titles=within(panel).getAllByRole("checkbox").map(el=>el.getAttribute("aria-label"));
  expect(titles).toEqual(["Complete: Today","Complete: Academic","Complete: Later"]);
  expect(screen.queryByText("No date")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"All tasks"})).toBeInTheDocument();
});

it("keeps source staleness and the institution submission distinction visible", () => {
  render(<HomeFocusTasks {...props} tasks={[{...task("Academic","2026-11-05"),academic_kind:"assignment"}]} stale/>);
  expect(screen.getByRole("status")).toHaveTextContent("Showing the last saved source data.");
  expect(screen.getByText("Marking an assignment complete does not submit it to your institution.")).toBeVisible();
});
