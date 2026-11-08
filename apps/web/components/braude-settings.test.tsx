import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { BraudeSettings } from "./braude-settings";
vi.mock("@/lib/api", async () => ({ ...await vi.importActual("@/lib/api"), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function show() {
  let disconnected = false;
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === "integrations/braude/disconnect" && method === "POST") disconnected = true;
    return { configured: !disconnected, connected: !disconnected, last_success: disconnected ? null : 1793620000,
      syncing: false, stale: false, event_count: disconnected ? 0 : 150, error: null } as never;
  });
  const changed = vi.fn().mockResolvedValue(undefined);
  render(<BraudeSettings csrf="fixture-csrf" t={(_he, en) => en} settings={{ language: "en", timezone: "Asia/Jerusalem", display_name: "", theme: "dark" }} onChanged={changed} onUnauthorized={vi.fn()} />);
  return changed;
}
it("queues an existing subscription refresh without claiming that new data already arrived", async () => {
  show(); await screen.findByText("150 events saved at the last sync.");
  fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
  await screen.findByText("Sync requested. Data will refresh after a successful sync.");
  expect(api).toHaveBeenCalledWith("integrations/braude/sync?background=true", "POST", undefined, "fixture-csrf");
});
it("disconnects only after explicit local confirmation and explains that academic records remain", async () => {
  const changed = show(); await screen.findByText("150 events saved at the last sync.");
  fireEvent.click(screen.getByRole("button", { name: "Disconnect student portal" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Existing courses, assignments and exams remain.");
  expect(api).not.toHaveBeenCalledWith("integrations/braude/disconnect", "POST", undefined, "fixture-csrf");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(changed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect student portal" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm disconnection" }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(api).toHaveBeenCalledWith("integrations/braude/disconnect", "POST", undefined, "fixture-csrf");
  await screen.findByRole("button", { name: "Connect student portal" });
});
