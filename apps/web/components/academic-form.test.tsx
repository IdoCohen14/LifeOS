import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AcademicForm } from "./academic-form";
import type { AcademicItem, Course, Term } from "@/lib/academic";
import type { Settings } from "@/lib/types";
import { ApiError } from "@/lib/api";
const settings: Settings = {
  display_name: "",
  language: "en",
  timezone: "Asia/Jerusalem",
  theme: "dark",
};
const t = (_he: string, en: string) => en;
afterEach(cleanup);
it("hides task completion for an exam while preserving its legacy storage flag", async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<AcademicForm editor={{kind:"items",courseId:"c",record:{id:"exam",title:"Exam fixture",kind:"exam",course_id:"c",due:"2027-03-04",completed:true} as AcademicItem}} terms={[]} settings={settings} t={t} onClose={()=>{}} onSave={save}/>);
  expect(screen.queryByLabelText("Completed")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith("items",expect.objectContaining({kind:"exam",completed:true,due:"2027-03-04"}),"exam"));
});
it("retains a drafted deadline when switching to a specific time", () => {
  render(
    <AcademicForm
      editor={{ kind: "items", courseId: "c" }}
      terms={[]}
      settings={settings}
      t={t}
      onClose={() => {}}
      onSave={async () => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText("Due date"), {
    target: { value: "2026-11-04" },
  });
  fireEvent.click(screen.getByLabelText("Include a specific time"));
  expect(screen.getByLabelText("Due date")).toHaveValue("2026-11-04T12:00");
});

for(const detail of ["academic_busy","other_failure"]){
 it(`retains the draft and only claims no-save for the precise ${detail} response`,async()=>{
  const save=vi.fn().mockRejectedValue(new ApiError(503,detail));
  render(<AcademicForm editor={{kind:"terms"}} terms={[]} settings={settings} t={t} onClose={vi.fn()} onSave={save}/>);
  fireEvent.change(screen.getByLabelText("Term name"),{target:{value:"Busy term draft"}});
  fireEvent.change(screen.getByLabelText("Start date"),{target:{value:"2026-10-01"}});
  fireEvent.change(screen.getByLabelText("End date"),{target:{value:"2027-01-01"}});
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  await screen.findByRole("alert");
  const busy="The database is busy. Nothing was saved by this attempt. Wait a moment and retry.";
  if(detail==="academic_busy")expect(screen.getByText(busy,{exact:true})).toBeVisible();
  else expect(screen.queryByText(busy,{exact:true})).not.toBeInTheDocument();
  expect(screen.getByLabelText("Term name")).toHaveValue("Busy term draft");
  expect(save).toHaveBeenCalledOnce();
 });
}

it("requires an explicit course for quick capture and preserves a date-only deadline", async () => {
 const save=vi.fn().mockResolvedValue(undefined), close=vi.fn();
 const terms=[{id:"term",name:"Current term"}] as Term[];
 const courses=[{id:"a",name:"Algebra",term_id:"term"},{id:"b",name:"Physics",term_id:"term"}] as Course[];
 render(<AcademicForm editor={{kind:"items"}} terms={terms} courses={courses} settings={settings} t={t} onClose={close} onSave={save}/>);
 const course=screen.getByLabelText("Course");
 expect(course).toHaveValue("");expect(course).toBeRequired();
 fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Quick deadline"}});
 fireEvent.change(screen.getByLabelText("Due date"),{target:{value:"2026-11-04"}});
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 expect(save).not.toHaveBeenCalled();
 fireEvent.change(course,{target:{value:"b"}});
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 await waitFor(()=>expect(save).toHaveBeenCalledWith("items",expect.objectContaining({course_id:"b",due:"2026-11-04",title:"Quick deadline"}),undefined));
 expect(close).toHaveBeenCalledOnce();
});
it("uses the selected term for new courses while fixed-course item creation stays fixed", async () => {
 const terms=[{id:"first",name:"Earlier"},{id:"selected",name:"Selected"}] as Term[];
 const save=vi.fn().mockResolvedValue(undefined);
 const view=render(<AcademicForm editor={{kind:"courses",termId:"selected"}} terms={terms} settings={settings} t={t} onClose={()=>{}} onSave={save}/>);
 expect(screen.getByLabelText("Term")).toHaveValue("selected");
 view.unmount();
 render(<AcademicForm editor={{kind:"items",courseId:"fixed"}} terms={terms} settings={settings} t={t} onClose={()=>{}} onSave={save}/>);
 expect(screen.queryByLabelText("Course")).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Fixed fixture"}});
 fireEvent.change(screen.getByLabelText("Due date"),{target:{value:"2026-11-04"}});
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 await waitFor(()=>expect(save).toHaveBeenCalledWith("items",expect.objectContaining({course_id:"fixed"}),undefined));
});
it("keeps academic form content on server failure", async () => {
  const save = vi.fn().mockRejectedValue(new Error("offline"));
  render(
    <AcademicForm
      editor={{ kind: "terms" }}
      terms={[]}
      settings={settings}
      t={t}
      onClose={() => {}}
      onSave={save}
    />,
  );
  fireEvent.change(screen.getByLabelText("Term name"), {
    target: { value: "Fall term" },
  });
  fireEvent.change(screen.getByLabelText("Start date"), {
    target: { value: "2026-10-01" },
  });
  fireEvent.change(screen.getByLabelText("End date"), {
    target: { value: "2027-01-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());
  expect(screen.getByLabelText("Term name")).toHaveValue("Fall term");
});

it("quick weekly session capture requires a course and saves its local weekday and clock",async()=>{
 const save=vi.fn().mockResolvedValue(undefined);
 render(<AcademicForm editor={{kind:"timetable"}} courses={[{id:"c",name:"Course",term_id:"term"} as Course]} terms={[{id:"term",name:"Term"} as Term]} settings={settings} t={t} onClose={()=>{}} onSave={save}/>);
 expect(screen.getByLabelText("Course")).toHaveValue("");
 fireEvent.change(screen.getByLabelText("Course"),{target:{value:"c"}});
 fireEvent.change(screen.getByLabelText("Weekday"),{target:{value:"4"}});
 fireEvent.change(screen.getByLabelText("Start time"),{target:{value:"09:00"}});
 fireEvent.change(screen.getByLabelText("End time"),{target:{value:"11:00"}});
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 await waitFor(()=>expect(save).toHaveBeenCalledWith("timetable",expect.objectContaining({course_id:"c",weekday:4,start_time:"09:00",end_time:"11:00",timezone:"Asia/Jerusalem"}),undefined));
});


for(const due of ["2026-10-25T01:30:21+03:00","2026-10-25T01:30:21+02:00","2026-11-12T15:00:37Z"]){
 it(`preserves the academic deadline ${due} on title-only edit`,async()=>{
  const save=vi.fn().mockResolvedValue(undefined);
  const record:AcademicItem={id:"exact-item",course_id:"c",task_id:"t",title:"Original",notes:"Keep notes",kind:"assignment",due,effort_hours:2,duration_minutes:90,completed:false};
  render(<AcademicForm editor={{kind:"items",record,courseId:"c"}} terms={[]} settings={settings} t={t} onClose={vi.fn()} onSave={save}/>);
  fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Renamed"}});
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith("items",expect.objectContaining({due,title:"Renamed",notes:"Keep notes"}),"exact-item"));
 });
}

it("retains the academic draft timezone when settings refresh",async()=>{
 const save=vi.fn().mockResolvedValue(undefined);
 const record:AcademicItem={id:"zone-item",course_id:"c",task_id:"t",title:"Original",notes:"",kind:"assignment",due:"2026-11-12T15:00:37Z",effort_hours:2,duration_minutes:90,completed:false};
 const props={editor:{kind:"items" as const,record,courseId:"c"},terms:[],settings,t,onClose:vi.fn(),onSave:save};
 const view=render(<AcademicForm {...props}/>);
 fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Renamed"}});
 view.rerender(<AcademicForm {...props} settings={{...settings,timezone:"America/New_York"}}/>);
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 await waitFor(()=>expect(save).toHaveBeenCalledWith("items",expect.objectContaining({due:record.due}),"zone-item"));
});
