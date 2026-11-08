import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RecurringEvents } from "./recurring-events";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: vi.fn(), ApiError: class extends Error {} }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, failed) => { resolve = done; reject = failed; });
  return { promise, resolve, reject };
}

it.each(["creation", "deletion"].flatMap(kind => ["button", "escape"].map(method => ({ kind, method }))))("closes $kind with $method after acknowledgement while calendar refresh is pending", async ({ kind, method }) => {
  const acknowledgement = deferred<{ deleted_count: number }>();
  const refresh = deferred<void>();
  const onChanged = vi.fn(() => refresh.promise);
  const occurrence = { id: "event", title: "Fixture", start: "2026-10-28", end: "2026-10-29", all_day: true, modified: false, unknown: false };
  vi.mocked(api).mockImplementation(async path => {
    if (path === "recurrence/series") return { items: [{ id: "series", title: "Fixture", count: 2, timezone: "Asia/Jerusalem" }], next_cursor: null };
    if (path.endsWith("/confirm")) return acknowledgement.promise;
    return { id: "preview", title: "Fixture", timezone: "Asia/Jerusalem", skipped_modified: 0, events: [occurrence] };
  });
  render(<RecurringEvents csrf="fixture" today="2026-10-27" settings={{ display_name: "", language: "en", timezone: "Asia/Jerusalem", theme: "dark" }} t={(_he, en) => en} onChanged={onChanged} onUnauthorized={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: kind === "creation" ? "Weekly recurring event" : "Manage weekly series" }));
  if (kind === "creation") {
    fireEvent.change(screen.getByLabelText("Recurring event title"), { target: { value: "Fixture" } });
    fireEvent.submit(screen.getByLabelText("Recurring event title").closest("form")!);
  } else {
    await waitFor(() => expect(screen.getByRole("button", { name: "Preview deletion" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Preview deletion" }));
  }
  fireEvent.click(await screen.findByRole("button", { name: /Confirm.*(save|creation|deletion)/i }));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.getByRole("dialog")).toBeVisible();
  await act(async () => acknowledgement.resolve({ deleted_count: 1 }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  if (method === "button") fireEvent.click(screen.getByRole("button", { name: "Close" }));
  else fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  if (kind === "creation") {
    fireEvent.click(screen.getByRole("button", { name: "Weekly recurring event" }));
    fireEvent.change(screen.getByLabelText("Recurring event title"), { target: { value: "New unsent draft" } });
    await act(async () => refresh.reject(new Error("Fixture refresh failure")));
    expect(screen.getByLabelText("Recurring event title")).toHaveValue("New unsent draft");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  } else await act(async () => refresh.resolve());
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith("/confirm"))).toHaveLength(1);
});
