import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecordForm } from "./record-form";
import type { Settings } from "@/lib/types";

const settings: Settings = {
  display_name: "",
  language: "en",
  theme: "dark",
  timezone: "Asia/Jerusalem",
};
const t = (_he: string, en: string) => en;
afterEach(cleanup);

describe("record forms", () => {
  it("keeps the local date when converting a midnight event to all-day", () => {
    render(
      <RecordForm
        editor={{
          kind: "event",
          record: {
            id: "e",
            title: "Late",
            notes: "",
            start: "2026-10-25T22:30:00Z",
            end: "2026-10-25T23:30:00Z",
            all_day: false,
            created_at: "",
          },
        }}
        settings={settings}
        t={t}
        onSave={async () => {}}
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByLabelText("All day"));
    expect(screen.getByLabelText("Start")).toHaveValue("2026-10-26");
  });
  it("retains edited dates when changing all-day mode", () => {
    render(
      <RecordForm
        editor={{ kind: "event", day: "2026-10-25" }}
        settings={settings}
        t={t}
        onSave={async () => {}}
        onClose={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Start"), {
      target: { value: "2026-11-01T10:00" },
    });
    fireEvent.click(screen.getByLabelText("All day"));
    expect(screen.getByLabelText("Start")).toHaveValue("2026-11-01");
  });
  it("saves a task and closes only after success", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <RecordForm
        editor={{ kind: "task" }}
        settings={settings}
        t={t}
        onSave={onSave}
        onClose={onClose}
      />,
    );
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Study topology" },
    });
    fireEvent.change(screen.getByLabelText("Due date"), {
      target: { value: "2026-10-25" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        "task",
        expect.objectContaining({
          title: "Study topology",
          due: "2026-10-25",
          completed: false,
        }),
        undefined,
      ),
    );
    expect(onClose).toHaveBeenCalledOnce();
  });
  it("retains entered content and shows retry guidance after failure", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("offline"));
    const onClose = vi.fn();
    render(
      <RecordForm
        editor={{ kind: "task" }}
        settings={settings}
        t={t}
        onSave={onSave}
        onClose={onClose}
      />,
    );
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Keep this title" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Title")).toHaveValue("Keep this title");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
  it("converts inclusive all-day end to exclusive storage", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <RecordForm
        editor={{ kind: "event", day: "2026-10-25" }}
        settings={settings}
        t={t}
        onSave={onSave}
        onClose={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Holiday" },
    });
    fireEvent.click(screen.getByLabelText("All day"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        "event",
        expect.objectContaining({
          start: "2026-10-25",
          end: "2026-10-26",
          all_day: true,
        }),
        undefined,
      ),
    );
  });
});

it("preserves existing notes, priority and timed deadline when optional details stay closed", async () => {
 const onSave=vi.fn().mockResolvedValue(undefined);
 render(<RecordForm editor={{kind:"task",record:{id:"preserved",title:"Keep my details",notes:"Existing private note",priority:"high",due:"2026-11-12T15:00:00Z",completed:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
 expect(screen.getByLabelText("Notes")).not.toBeVisible();
 expect(screen.getByLabelText("Priority")).not.toBeVisible();
 fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Updated title"}});
 fireEvent.click(screen.getByRole("button",{name:"Save"}));
 await waitFor(()=>expect(onSave).toHaveBeenCalledWith("task",expect.objectContaining({title:"Updated title",notes:"Existing private note",priority:"high",due:"2026-11-12T15:00:00Z"}),"preserved"));
});


describe("unchanged explicit instants", () => {
  it.each(["2026-10-25T01:30:21+03:00", "2026-10-25T01:30:21+02:00", "2026-11-12T15:00:37Z"])(
    "keeps the exact task instant %s when only its title changes", async due => {
      const onSave=vi.fn().mockResolvedValue(undefined);
      render(<RecordForm editor={{kind:"task",record:{id:"exact-task",title:"Original",notes:"",priority:"medium",due,completed:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
      fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Renamed"}});
      fireEvent.click(screen.getByRole("button",{name:"Save"}));
      await waitFor(()=>expect(onSave).toHaveBeenCalledWith("task",expect.objectContaining({title:"Renamed",due}),"exact-task"));
    },
  );
  it.each([
    ["2026-10-25T01:45:13+03:00", "2026-10-25T01:15:41+02:00"],
    ["2026-11-12T15:00:13Z", "2026-11-12T16:00:41Z"],
    ["2026-11-12T15:00:13.000001Z", "2026-11-12T15:00:13.000002Z"],
  ])("keeps an event's original explicit range %s to %s",async(start,end)=>{
    const onSave=vi.fn().mockResolvedValue(undefined);
    render(<RecordForm editor={{kind:"event",record:{id:"exact-event",title:"Original",notes:"",start,end,all_day:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Renamed"}});
    fireEvent.click(screen.getByRole("button",{name:"Save"}));
    await waitFor(()=>expect(onSave).toHaveBeenCalledWith("event",expect.objectContaining({title:"Renamed",start,end}),"exact-event"));
  });
  it("still rejects a newly entered ambiguous task time",async()=>{
    const onSave=vi.fn().mockResolvedValue(undefined);
    render(<RecordForm editor={{kind:"task",record:{id:"new-ambiguous",title:"Original",notes:"",priority:"medium",due:"2026-10-25T03:30:00+02:00",completed:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
    fireEvent.click(screen.getByText("Priority and exact time"));
    fireEvent.change(screen.getByLabelText("Due time (optional)"),{target:{value:"01:30"}});
    fireEvent.click(screen.getByRole("button",{name:"Save"}));
    await screen.findByRole("alert");
    expect(onSave).not.toHaveBeenCalled();
  });
});


it("preserves the unchanged fold endpoint when the other endpoint changes",async()=>{
  const onSave=vi.fn().mockResolvedValue(undefined);
  const start="2026-10-25T01:45:13+03:00";
  render(<RecordForm editor={{kind:"event",record:{id:"one-endpoint",title:"Original",notes:"",start,end:"2026-10-25T01:15:41+02:00",all_day:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText("End"),{target:{value:"2026-10-25T03:00"}});
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  await waitFor(()=>expect(onSave).toHaveBeenCalledWith("event",expect.objectContaining({start,end:"2026-10-25T01:00:00Z"}),"one-endpoint"));
});

it("rejects an edited event endpoint that precedes its preserved start",async()=>{
  const onSave=vi.fn();
  render(<RecordForm editor={{kind:"event",record:{id:"backwards",title:"Original",notes:"",start:"2026-10-25T01:45:13+03:00",end:"2026-10-25T01:15:41+02:00",all_day:false,created_at:""}}} settings={settings} t={t} onSave={onSave} onClose={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText("End"),{target:{value:"2026-10-25T00:30"}});
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("End must be after start.");
  expect(onSave).not.toHaveBeenCalled();
});


it("keeps an open event draft in its displayed timezone across a settings refresh",async()=>{
  const onSave=vi.fn().mockResolvedValue(undefined);
  const editor={kind:"event" as const,record:{id:"timezone-draft",title:"Original",notes:"",start:"2026-11-12T15:00:13Z",end:"2026-11-12T16:00:41Z",all_day:false,created_at:""}};
  const props={editor,settings,t,onSave,onClose:vi.fn()};
  const view=render(<RecordForm {...props}/>);
  fireEvent.change(screen.getByLabelText("Title"),{target:{value:"Renamed"}});
  view.rerender(<RecordForm {...props} settings={{...settings,timezone:"America/New_York"}}/>);
  expect(screen.getByLabelText("Start")).toHaveValue("2026-11-12T17:00");
  expect(screen.getByText("Asia/Jerusalem")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"Save"}));
  await waitFor(()=>expect(onSave).toHaveBeenCalledWith("event",expect.objectContaining({start:editor.record.start,end:editor.record.end}),"timezone-draft"));
});
