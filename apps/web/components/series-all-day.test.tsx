import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SeriesManagement } from "./series-management";
import { api } from "@/lib/api";
vi.mock("@/lib/api", () => ({ api: vi.fn(), ApiError: class extends Error {} }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("requires explicit all-day selection and reviews inclusive new multi-day range without time conversion", async () => {
  vi.mocked(api).mockImplementation(async path => path === "recurrence/series" ? {items:[{id:"series",title:"Fixture",count:2,timezone:"Asia/Jerusalem"}],next_cursor:null} : {id:"preview",title:"Fixture",timezone:"Asia/Jerusalem",skipped_modified:0,events:[{id:"event",title:"Multi-day fixture",start:"2026-10-28",end:"2026-10-31",new_start:"2026-10-30",new_end:"2026-11-02",all_day:true,modified:false,unknown:false}]});
  render(<SeriesManagement csrf="fixture" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_he,en)=>en} onClose={vi.fn()} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()} />);
  await waitFor(()=>expect(screen.getByRole("button",{name:"Preview deletion"})).toBeEnabled());
  expect(screen.queryByLabelText("Include all-day occurrences")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Series action"),{target:{value:"shift"}});
  const toggle=screen.getByLabelText("Include all-day occurrences");
  expect(toggle).not.toBeChecked();
  fireEvent.click(toggle);
  fireEvent.change(screen.getByLabelText("Calendar days to shift"),{target:{value:"2"}});
  fireEvent.click(screen.getByRole("button",{name:"Preview date shift"}));
  await screen.findByRole("button",{name:"Confirm shift of 1 occurrences"});
  expect(vi.mocked(api).mock.calls.find(([path])=>path.endsWith("reschedule-preview"))?.[2]).toMatchObject({include_all_day:true,preserve_time:true,day_shift:2});
  expect(screen.getByText(/New dates:/).closest("p")).toHaveTextContent("30/10/2026 — 01/11/2026 (inclusive) · All day");
  expect(screen.getByText(/Current dates:/).closest("p")).toHaveTextContent("28/10/2026 — 30/10/2026 (inclusive) · All day");
  expect(vi.mocked(api).mock.calls.some(([path])=>path.endsWith("/confirm"))).toBe(false);
});


it("reviews an explicit title-only action without clock or day replacements",async()=>{
 vi.mocked(api).mockImplementation(async path=>path==="recurrence/series"?{items:[{id:"series",title:"Original series fixture",count:2,timezone:"Asia/Jerusalem"}],next_cursor:null}:{id:"preview",title:"Original series fixture",timezone:"Asia/Jerusalem",skipped_modified:0,events:[{id:"event",title:"Old occurrence fixture",new_title:"Next block fixture",start:"2026-10-28",end:"2026-10-29",new_start:"2026-10-28",new_end:"2026-10-29",all_day:true,modified:false,unknown:false}]});
 render(<SeriesManagement csrf="fixture" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_he,en)=>en} onClose={vi.fn()} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()} />);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Preview deletion"})).toBeEnabled());
 fireEvent.change(screen.getByLabelText("Series action"),{target:{value:"rename"}});
 expect(screen.getByLabelText("New title for selected occurrences")).toHaveValue("");
 fireEvent.change(screen.getByLabelText("New title for selected occurrences"),{target:{value:"Next block fixture"}});
 fireEvent.click(screen.getByRole("button",{name:"Preview title changes"}));
 await screen.findByRole("button",{name:"Confirm title changes for 1 occurrences"});
 const body=vi.mocked(api).mock.calls.find(([path])=>path.endsWith("reschedule-preview"))?.[2];
 expect(body).toMatchObject({new_title:"Next block fixture",include_modified:false});
 expect(body).not.toHaveProperty("clock");expect(body).not.toHaveProperty("day_shift");
 expect(screen.getByText("Old occurrence fixture")).toBeVisible();
 expect(screen.getByText("Next block fixture")).toBeVisible();
 expect(screen.queryByText(/New dates:/)).not.toBeInTheDocument();
 expect(vi.mocked(api).mock.calls.some(([path])=>path.endsWith("/confirm"))).toBe(false);
});


it("requires an explicit type and formats the destination using its new timed type",async()=>{
 vi.mocked(api).mockImplementation(async path=>path==="recurrence/series"?{items:[{id:"series",title:"Fixture",count:2,timezone:"Asia/Jerusalem"}],next_cursor:null}:{id:"preview",title:"Fixture",timezone:"Asia/Jerusalem",skipped_modified:0,events:[{id:"event",title:"Conversion fixture",start:"2026-10-28",end:"2026-10-29",new_start:"2026-10-28T09:00:00Z",new_end:"2026-10-28T10:30:00Z",all_day:true,new_all_day:false,modified:false,unknown:false}]});
 render(<SeriesManagement csrf="fixture" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_he,en)=>en} onClose={vi.fn()} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()} />);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Preview deletion"})).toBeEnabled());
 fireEvent.change(screen.getByLabelText("Series action"),{target:{value:"convert"}});
 expect(screen.getByLabelText("New occurrence type")).toHaveValue("");
 fireEvent.change(screen.getByLabelText("New occurrence type"),{target:{value:"timed"}});
 fireEvent.change(screen.getByLabelText("New occurrence time"),{target:{value:"11:00"}});
 fireEvent.change(screen.getByLabelText("New duration in minutes"),{target:{value:"90"}});
 fireEvent.click(screen.getByRole("button",{name:"Preview type conversion"}));
 await screen.findByRole("button",{name:"Confirm type conversion for 1 occurrences"});
 expect(vi.mocked(api).mock.calls.find(([path])=>path.endsWith("reschedule-preview"))?.[2]).toMatchObject({target_all_day:false,clock:"11:00",duration:90});
 const newRange=screen.getByText(/New time:/).closest("p");
 expect(newRange).toHaveTextContent("11:00");
 expect(newRange).not.toHaveTextContent("All day");
});


it("sends a separately approved combined date-and-time operation",async()=>{
 vi.mocked(api).mockImplementation(async path=>path==="recurrence/series"?{items:[{id:"series",title:"Fixture",count:2,timezone:"Asia/Jerusalem"}],next_cursor:null}:{id:"preview",title:"Fixture",timezone:"Asia/Jerusalem",skipped_modified:0,events:[{id:"event",title:"Combined fixture",start:"2026-10-28T07:00:00Z",end:"2026-10-28T08:00:00Z",new_start:"2026-10-29T11:00:00Z",new_end:"2026-10-29T11:30:00Z",all_day:false,modified:false,unknown:false}]});
 render(<SeriesManagement csrf="fixture" settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} t={(_he,en)=>en} onClose={vi.fn()} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()} />);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Preview deletion"})).toBeEnabled());
 fireEvent.change(screen.getByLabelText("Series action"),{target:{value:"combined"}});
 fireEvent.change(screen.getByLabelText("Calendar days to shift"),{target:{value:"1"}});
 fireEvent.change(screen.getByLabelText("New occurrence time"),{target:{value:"13:00"}});
 fireEvent.change(screen.getByLabelText("New duration in minutes"),{target:{value:"30"}});
 fireEvent.click(screen.getByRole("button",{name:"Preview date and time changes"}));
 await screen.findByRole("button",{name:"Confirm date and time changes for 1 occurrences"});
 expect(vi.mocked(api).mock.calls.find(([path])=>path.endsWith("reschedule-preview"))?.[2]).toMatchObject({shift_and_time:true,day_shift:1,clock:"13:00",duration:30});
});
