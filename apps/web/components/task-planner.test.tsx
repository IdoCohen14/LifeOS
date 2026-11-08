import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { TaskPlanner } from "./task-planner";
import type { Task } from "@/lib/types";

afterEach(cleanup);
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
beforeEach(() => { vi.mocked(api).mockReset(); });
const task: Task = {
  id: "00000000-0000-0000-0000-000000000001",
  title: "Plan fixture",
  notes: "",
  priority: "high",
  due: null,
  completed: false,
  created_at: "",
};
it("starts with a request form and cannot save an event before a proposal exists", async () => {
  render(
    <TaskPlanner
      tasks={[task]}
      settings={{
        display_name: "",
        language: "en",
        timezone: "Asia/Jerusalem",
        theme: "dark",
      }}
      today="2026-10-26"
      csrf="fixture"
      t={(_he, en) => en}
      onChanged={vi.fn(async () => {})}
      onUnauthorized={vi.fn()}
      onDay={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Find a time block" }));
  expect(
    await screen.findByRole("dialog", { name: "Plan time for a task" }),
  ).toBeVisible();
  expect(screen.getByLabelText("Duration in minutes")).toHaveValue(30);
  expect(
    screen.queryByRole("button", { name: "Confirm and save to calendar" }),
  ).not.toBeInTheDocument();
});

for (const method of ["button", "escape", "calendar"] as const) {
  it(`isolates an acknowledged save from reopened drafts via ${method}`, async () => {
    let acknowledge!: () => void;
    let rejectRefresh!: (error: Error) => void;
    const write = new Promise<void>(resolve => { acknowledge = resolve; });
    const refresh = new Promise<void>((_resolve, reject) => { rejectRefresh = reject; });
    const changed = vi.fn(() => refresh);
    const navigate = vi.fn();
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "planning/preferences") return { enabled: false };
      if (path === "planning/propose") return { proposal: { id: "proposal-fixture", kind: "event", payload: { title: task.title, start: "2026-10-27T08:00:00Z", end: "2026-10-27T08:30:00Z", all_day: false } } };
      if (path === "assistant/confirm") return write;
      throw new Error(`Unexpected ${path}`);
    });
    render(<TaskPlanner tasks={[task]} settings={{ display_name: "", language: "en", timezone: "Asia/Jerusalem", theme: "dark" }} today="2026-10-26" csrf="fixture" t={(_he,en)=>en} onChanged={changed} onUnauthorized={vi.fn()} onDay={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Find a time block" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Suggest a time" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm and save to calendar" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByRole("dialog")).toBeVisible();
    await act(async () => acknowledge());
    await screen.findByText("Saved to your calendar. The task stays open.");
    if (method === "button") fireEvent.click(screen.getByRole("button", { name: "Close" }));
    else if (method === "escape") fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    else fireEvent.click(screen.getByRole("button", { name: "Open in calendar" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Find a time block" }));
    await screen.findByRole("dialog");
    fireEvent.change(screen.getByLabelText("Duration in minutes"), { target: { value: "45" } });
    await act(async () => rejectRefresh(new Error("Old refresh failure")));
    expect(screen.getByLabelText("Duration in minutes")).toHaveValue(45);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Saved to your calendar. The task stays open.")).not.toBeInTheDocument();
    expect(vi.mocked(api).mock.calls.filter(([path]) => path === "assistant/confirm")).toHaveLength(1);
    expect(changed).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledTimes(method === "calendar" ? 1 : 0);
  });
}

it("compact academic entry preselects the real linked task and never saves without approval", async () => {
  vi.mocked(api).mockImplementation(async path => {
    if (path === "planning/preferences") return {enabled:false};
    if (path === "planning/propose") return {proposal:null,reason:"no_slot"};
    throw new Error(`Unexpected ${path}`);
  });
  render(<TaskPlanner compact tasks={[task]} settings={{display_name:"",language:"en",timezone:"Asia/Jerusalem",theme:"dark"}} today="2026-10-28" csrf="fixture" t={(_he,en)=>en} onChanged={vi.fn(async()=>{})} onUnauthorized={vi.fn()} onDay={vi.fn()}/>);
  expect(screen.queryByRole("heading",{name:"Make time for an important task"})).not.toBeInTheDocument();
  expect(api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:`Plan time: ${task.title}`}));
  await screen.findByRole("dialog");
  expect(screen.getByLabelText("Task to plan")).toHaveValue(task.id);
  fireEvent.click(screen.getByRole("button",{name:"Suggest a time"}));
  await screen.findByText("No suitable block was found in your chosen window. Try another date, duration or planning options.");
  const request=vi.mocked(api).mock.calls.find(([path])=>path==="planning/propose");
  expect(request?.[2]).toMatchObject({task_id:task.id});
  expect(vi.mocked(api).mock.calls.some(([path])=>path==="assistant/confirm")).toBe(false);
});
