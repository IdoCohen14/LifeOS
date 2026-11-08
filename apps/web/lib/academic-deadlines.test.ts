import { beforeEach, expect, it, vi } from "vitest";
import { dueDay } from "./dates";
import { academicDeadlines, academicOverdue } from "./academic-deadlines";
import type { AcademicItem, Course } from "./academic";
vi.mock("./dates",async original=>{const actual=await original<typeof import("./dates")>();return {...actual,dueDay:vi.fn(actual.dueDay)};});
beforeEach(()=>{vi.mocked(dueDay).mockClear();});

const courses = [{ id: "a", term_id: "one" }, { id: "b", term_id: "two" }] as Course[];
const item = (id: string, due: string, changes: Partial<AcademicItem> = {}): AcademicItem => ({ id, due, course_id: "a", task_id: id, title: id, notes: "", kind: "assignment", completed: false, effort_hours: 1, duration_minutes: 60, ...changes });
it("orders by local deadline day, actual timed instant, then date-only without changing input", () => {
  const source = [item("day", "2026-10-28"), item("later", "2026-10-28T10:00:00+02:00"), item("early", "2026-10-28T09:30:00+03:00"), item("previous", "2026-10-27T21:30:00Z"), item("next", "2026-10-28T23:30:00Z")];
  const before = JSON.stringify(source);
  expect(academicDeadlines(source, courses, "all", "open", "all", "Asia/Jerusalem").map(x=>x.id)).toEqual(["previous", "early", "later", "day", "next"]);
  expect(JSON.stringify(source)).toBe(before);
});
it("prepares local dates at most once per eligible record rather than per sort comparison",()=>{
 const source=Array.from({length:100},(_,i)=>item(String(i),`2026-10-${String(i*17%28+1).padStart(2,"0")}T09:00:00+02:00`));
 const before=JSON.stringify(source);
 const result=academicDeadlines(source,courses,"all","all","all","Asia/Jerusalem","week",new Date("2026-10-10T10:00:00Z"));
 expect(result.length).toBeGreaterThan(0);
 expect(vi.mocked(dueDay).mock.calls.length).toBeLessThanOrEqual(source.length);
 expect(result.every(value=>source.includes(value))).toBe(true);
 expect(JSON.stringify(source)).toBe(before);
});
it("does not convert future timed records excluded by the overdue filter",()=>{
 const source=Array.from({length:100},(_,i)=>item(String(i),"2027-10-28T09:00:00+02:00"));
 expect(academicDeadlines(source,courses,"all","open","all","Asia/Jerusalem","overdue",new Date("2026-10-28T10:00:00Z"))).toEqual([]);
 expect(vi.mocked(dueDay)).not.toHaveBeenCalled();
});
it("distinguishes date-only days from timed instants including offsets and completion",()=>{
 const now=new Date("2026-10-28T10:00:00Z");
 expect(academicOverdue(item("day","2026-10-28"),now,"Asia/Jerusalem")).toBe(false);
 expect(academicOverdue(item("old","2026-10-27"),now,"Asia/Jerusalem")).toBe(true);
 expect(academicOverdue(item("past","2026-10-28T11:00:00+02:00"),now,"Asia/Jerusalem")).toBe(true);
 expect(academicOverdue(item("future","2026-10-28T14:00:00+03:00"),now,"Asia/Jerusalem")).toBe(false);
 expect(academicOverdue(item("done","2026-10-27",{completed:true}),now,"Asia/Jerusalem")).toBe(false);
 expect(academicOverdue(item("localday","2026-10-27"),new Date("2026-10-27T22:30:00Z"),"Asia/Jerusalem")).toBe(true);
});
it("filters today and seven local calendar dates without including day eight or completed overdue",()=>{
 const now=new Date("2026-10-28T10:00:00Z");
 const source=[item("old","2026-10-27"),item("timed-past","2026-10-28T09:00:00Z"),item("today","2026-10-28"),item("seventh","2026-11-03"),item("eighth","2026-11-04"),item("done","2026-10-27",{completed:true})];
 const list=(period:"overdue"|"today"|"week")=>academicDeadlines(source,courses,"all","all","all","Asia/Jerusalem",period,now).map(x=>x.id);
 expect(list("overdue")).toEqual(["old","timed-past"]);
 expect(list("today")).toEqual(["timed-past","today"]);
 expect(list("week")).toEqual(["timed-past","today","seventh"]);
});
it("applies term, completion and kind filters and excludes unknown courses", () => {
  const source = [item("open", "2026-10-28"), item("done", "2026-10-28", {completed:true}), item("exam", "2026-10-28", {kind:"exam",course_id:"b"}), item("orphan", "2026-10-28", {course_id:"missing"})];
  expect(academicDeadlines(source,courses,"all","open","all","Asia/Jerusalem").map(x=>x.id)).toEqual(["exam","open"]);
  expect(academicDeadlines(source,courses,"one","completed","all","Asia/Jerusalem").map(x=>x.id)).toEqual(["done"]);
  expect(academicDeadlines(source,courses,"two","all","exam","Asia/Jerusalem").map(x=>x.id)).toEqual(["exam"]);
});
