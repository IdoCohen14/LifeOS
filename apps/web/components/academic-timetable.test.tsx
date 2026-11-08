import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AcademicTimetable } from "./academic-timetable";
import type { Course, Slot, Term } from "@/lib/academic";
afterEach(cleanup);
const courses=[{id:"a",name:"Algebra",term_id:"one"},{id:"b",name:"Physics",term_id:"two"}] as Course[];
const terms=[{id:"one",name:"Current term"},{id:"two",name:"Other term"}] as Term[];
const slot=(id:string,weekday:number,start:string,course_id="a"):Slot=>({id,course_id,weekday,start_time:start,end_time:"12:00",location:`Room ${id}`,timezone:"Asia/Jerusalem"});
it("filters by term and groups Sunday first with local-clock order, location and explicit zone",()=>{
 const select=vi.fn();
 render(<AcademicTimetable slots={[slot("later",0,"11:00"),slot("early",0,"09:00"),slot("monday",1,"08:00"),slot("other",0,"07:00","b")]} courses={courses} terms={terms} term="one" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_he,en)=>en} onSelect={select}/>);
 fireEvent.click(screen.getByText("Weekly timetable",{exact:true}));
 const sunday=screen.getByRole("region",{name:"Sunday"});
 expect(within(sunday).getAllByRole("listitem")[0]).toHaveTextContent("09:00");
 expect(within(sunday).getAllByRole("listitem")[1]).toHaveTextContent("11:00");
 expect(screen.queryByText("Room other")).not.toBeInTheDocument();
 expect(within(sunday).getByText("Room early")).toBeVisible();
 expect(within(sunday).getAllByText("Asia/Jerusalem")).toHaveLength(2);
 fireEvent.click(within(sunday).getAllByRole("button",{name:"Open course timetable: Algebra"})[0]);
 expect(select).toHaveBeenCalledWith("a");
 expect(screen.getByRole("region",{name:"Monday"})).toBeVisible();
});
it("shows an honest empty weekly template and ignores orphan sessions",()=>{
 render(<AcademicTimetable slots={[slot("unknown",0,"09:00","missing")]} courses={courses} terms={terms} term="all" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"light"}} t={(_he,en)=>en} onSelect={vi.fn()}/>);
 fireEvent.click(screen.getByText("Weekly timetable",{exact:true}));
 expect(screen.getByText("No weekly sessions in the selected term. Add a session or change the term filter.",{exact:true})).toBeVisible();
 expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
});
