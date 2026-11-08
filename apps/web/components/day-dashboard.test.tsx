import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { DayDashboard } from "./day-dashboard";
import type { Task, CalendarEvent } from "@/lib/types";

afterEach(cleanup);

it("uses the Jerusalem day, real task totals and ongoing events, with date-only deadlines unchanged", () => {
  const tasks: Task[] = [
    {id:"a",title:"Assignment",notes:"",priority:"medium",due:"2026-11-03",completed:false,created_at:"2026-11-01T00:00:00Z",academic_kind:"assignment"},
    {id:"b",title:"Done",notes:"",priority:"medium",due:null,completed:true,created_at:"2026-11-01T00:00:00Z"},
    {id:"c",title:"Later",notes:"",priority:"medium",due:"2026-11-04",completed:false,created_at:"2026-11-01T00:00:00Z"},
  ];
  const events: CalendarEvent[] = [{id:"e",title:"Current meeting",notes:"",start:"2026-11-02T22:00:00Z",end:"2026-11-03T00:00:00Z",all_day:false,created_at:"2026-11-01T00:00:00Z"}];
  render(<DayDashboard tasks={tasks} events={events} now={new Date("2026-11-02T22:30:00Z")} settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_,en)=>en}/>);
  expect(screen.getByText("Current meeting").closest("a")).toHaveAttribute("href","/?view=calendar&day=2026-11-03");
  expect(within(screen.getByRole("link",{name:"2 Open tasks"})).getByText("2")).toBeInTheDocument();
  expect(screen.getByRole("link",{name:"1 Due or overdue"})).toBeInTheDocument();
  expect(screen.getByRole("link",{name:"1 Assignments"})).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value","1");
  expect(screen.getByRole("navigation",{name:"Next seven days"}).querySelectorAll("a")).toHaveLength(7);
});

it("shows an honest empty day without invented events or completion", () => {
  render(<DayDashboard tasks={[]} events={[]} now={new Date("2026-11-02T12:00:00Z")} settings={{display_name:"",language:"he",timezone:"Asia/Jerusalem",theme:"dark"}} t={he=>he}/>);
  expect(screen.getByText("אין עוד אירועים מתוזמנים להיום")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("value","0");
});

it("shows the genuine source room for the upcoming class without inventing a location", () => {
  const events: CalendarEvent[] = [{id:"class",title:"Operating systems",notes:"הרצאה\nחדר: L709",source:"braude",start:"2026-11-04T08:30:00Z",end:"2026-11-04T10:20:00Z",all_day:false,created_at:"2026-11-01T00:00:00Z"}];
  render(<DayDashboard tasks={[]} events={events} now={new Date("2026-11-04T08:00:00Z")} settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_,en)=>en}/>);
  expect(screen.getByText("L 709")).toBeInTheDocument();
  expect(screen.getByText("Operating systems").closest("a")).toHaveAttribute("href","/?view=timetable");
});
