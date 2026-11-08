import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AcademicView } from "./academic-view";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

for (const outcome of ["snapshot", "expired", "unmounted"] as const) {
 it(`ignores an obsolete academic ${outcome} response`, async()=>{
  let release!:(value:unknown)=>void;
  const old=new Promise(resolve=>{release=resolve;});
  let courseCalls=0;
  const response=(value:unknown,status=200)=>({ok:status===200,status,json:async()=>value});
  const course={id:"c",term_id:"t",name:"Current course fixture",code:"",instructor:"",credits:3,color:"#a597ff"};
  vi.stubGlobal("fetch",vi.fn((path:string)=>{
   if(path.endsWith("/courses")){courseCalls++;return courseCalls===1?old:Promise.resolve(response([course]));}
   return Promise.resolve(response([]));
  }));
  const expired=vi.fn();
  const props={settings:{display_name:"",language:"en" as const,theme:"dark" as const,timezone:"Asia/Jerusalem"},t:(_he:string,en:string)=>en,courseId:null,onSelect:vi.fn(),onChanged:vi.fn(async()=>{}),onUnauthorized:expired};
  const view=render(<AcademicView {...props} csrf="old"/>);
  await waitFor(()=>expect(courseCalls).toBe(1));
  if(outcome==="unmounted") view.unmount();
  else {
   view.rerender(<AcademicView {...props} csrf="new"/>);
   await screen.findByText(course.name,{exact:true});
  }
  await act(async()=>release(outcome==="snapshot"?response([{...course,name:"Obsolete course fixture"}]):response({detail:"Old session"},401)));
  expect(expired).not.toHaveBeenCalled();
  if(outcome!=="unmounted"){
   fireEvent.click(screen.getByText(course.name,{exact:true}).closest("details")!.querySelector("summary")!);
   expect(screen.getByText(course.name,{exact:true})).toBeVisible();
   expect(screen.queryByText("Obsolete course fixture",{exact:true})).not.toBeInTheDocument();
   expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  }
 });
}
it("requests reauthentication when the initial academic load expires", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Expired" }),
      }),
  );
  const expired = vi.fn();
  render(
    <AcademicView
      settings={{
        display_name: "",
        language: "en",
        theme: "dark",
        timezone: "Asia/Jerusalem",
      }}
      csrf="old"
      t={(_he, en) => en}
      courseId={null}
      onSelect={() => {}}
      onChanged={async () => {}}
      onUnauthorized={expired}
    />,
  );
  await waitFor(() => expect(expired).toHaveBeenCalledOnce());
});
