import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AcademicDeadlines } from "./academic-deadlines";
import type { AcademicItem, Course } from "@/lib/academic";
afterEach(cleanup);
const course = {id:"a",term_id:"one",name:"Algebra fixture"} as Course;
const items: AcademicItem[] = Array.from({length:12},(_,i)=>({id:`item-${i}`,task_id:`task-${i}`,course_id:"a",title:`Assignment ${i}`,due:`2026-11-${String(i+1).padStart(2,"0")}`,notes:"",kind:"assignment",completed:false,effort_hours:1,duration_minutes:60}));
function mount(extra: AcademicItem[] = [], busy=false) {
 const onSelect=vi.fn(),onToggle=vi.fn();
 render(<AcademicDeadlines items={[...items,...extra]} courses={[course]} term="all" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} today="2026-11-02" now={new Date("2026-11-02T10:00:00Z")} busy={busy} t={(_he,en)=>en} onSelect={onSelect} onToggle={onToggle}/>);
 return {onSelect,onToggle};
}
it("shows bounded open deadlines, accurate total and explicit completion/navigation",()=>{
 const {onSelect,onToggle}=mount();
 const region=screen.getByRole("region",{name:"Assignments to submit"});
 expect(within(region).getByText("12 open items")).toBeVisible();
 expect(within(region).getAllByRole("listitem")).toHaveLength(5);
 expect(within(region).getByText(/Overdue ·/)).toBeVisible();
 fireEvent.click(within(region).getAllByRole("button",{name:"Open course: Algebra fixture"})[0]);
 expect(onSelect).toHaveBeenCalledWith("a");
 fireEvent.click(within(region).getByRole("checkbox",{name:"Complete: Assignment 0"}));
 expect(onToggle).toHaveBeenCalledWith(items[0]);
 fireEvent.click(within(region).getByRole("button",{name:"Show more"}));
 expect(within(region).getAllByRole("listitem")).toHaveLength(12);
});
it("filters actionable periods with precise same-day overdue labels and visible timezone",()=>{
 const timed={...items[0],id:"timed",title:"Timed past",due:"2026-11-02T09:00:00Z"};
 mount([timed]);
 fireEvent.click(document.querySelector(".simple-filters > summary")!);
 fireEvent.click(screen.getByRole("button",{name:"Show more"}));
 fireEvent.change(screen.getByLabelText("Deadline period"),{target:{value:"overdue"}});
 expect(screen.getAllByRole("listitem")).toHaveLength(2);
 expect(screen.getByText("Timed past")).toBeVisible();
 expect(screen.getAllByText(/Overdue ·/)).toHaveLength(2);
 expect(screen.getByText("Asia/Jerusalem",{exact:true})).toBeVisible();
 fireEvent.change(screen.getByLabelText("Deadline period"),{target:{value:"today"}});
 expect(screen.getAllByRole("listitem")).toHaveLength(2);
 fireEvent.change(screen.getByLabelText("Deadline period"),{target:{value:"all"}});
 expect(screen.getAllByRole("listitem")).toHaveLength(5);
});
it("filters completed assignments while exams stay outside this section",()=>{
 const done={...items[0],id:"done",title:"Completed assignment",completed:true};
 const exam={...items[0],id:"exam",title:"Future exam",due:"2027-03-04",kind:"exam" as const};
 mount([done,exam],true);
 fireEvent.click(document.querySelector(".simple-filters > summary")!);
 expect(screen.queryByText(done.title)).not.toBeInTheDocument();
 expect(screen.getByRole("checkbox",{name:"Complete: Assignment 0"})).toBeDisabled();
 fireEvent.change(screen.getByLabelText("Item status"),{target:{value:"completed"}});
 expect(screen.getByText(done.title)).toBeVisible();
 expect(screen.getByRole("checkbox",{name:"Reopen: Completed assignment"})).toHaveAttribute("aria-checked","true");
 expect(screen.queryByText(exam.title)).not.toBeInTheDocument();
 expect(screen.getAllByRole("listitem")).toHaveLength(1);
});
