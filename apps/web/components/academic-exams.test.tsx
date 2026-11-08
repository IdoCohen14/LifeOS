import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { AcademicItem, Course } from "@/lib/academic";
import { AcademicExams } from "./academic-exams";

afterEach(cleanup);
const courses=[{id:"systems",name:"Operating systems",term_id:"term"},{id:"other",name:"Other term",term_id:"other"}] as Course[];
const item=(id:string,due:string,kind:"exam"|"assignment"="exam"):AcademicItem=>({id,title:id,course_id:"systems",task_id:id,kind,due,completed:false,notes:"",duration_minutes:120,effort_hours:0});
const settings={display_name:"",language:"en" as const,theme:"dark" as const,timezone:"Asia/Jerusalem"};

it("shows a distant exam as a date, not a completable or plannable task",()=>{
 const onSelect=vi.fn();render(<AcademicExams items={[item("Exam in four months","2027-03-04"),item("Assignment","2026-11-05","assignment")]} courses={courses} term="term" settings={settings} now={new Date("2026-11-04T08:00:00Z")} t={(_,en)=>en} onSelect={onSelect}/>);
 const section=screen.getByRole("region",{name:"Exams"});expect(within(section).getByText("Exam in four months")).toBeVisible();expect(within(section).queryByText("Assignment")).not.toBeInTheDocument();expect(within(section).queryByRole("checkbox")).not.toBeInTheDocument();expect(within(section).queryByText("Plan time")).not.toBeInTheDocument();
 fireEvent.click(within(section).getByRole("button",{name:"Open course: Operating systems"}));expect(onSelect).toHaveBeenCalledWith("systems");
});

it("uses the local exam day, ignores old task completion flags and separates past dates",()=>{
 const future={...item("Legacy marked exam","2027-03-04"),completed:true};
 render(<AcademicExams items={[item("Today locally","2026-11-03T22:30:00Z"),item("Past exam","2026-11-03"),future,{...item("Foreign term","2027-02-01"),course_id:"other"}]} courses={courses} term="term" settings={settings} now={new Date("2026-11-04T08:00:00Z")} t={(_,en)=>en} onSelect={vi.fn()}/>);
 expect(screen.getByText("Today locally")).toBeVisible();expect(screen.getByText(future.title)).toBeVisible();expect(screen.queryByText("Foreign term")).not.toBeInTheDocument();expect(screen.getByText("Past exam")).not.toBeVisible();fireEvent.click(screen.getByText(/Past exams/));expect(screen.getByText("Past exam")).toBeVisible();
});
