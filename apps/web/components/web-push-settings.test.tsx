import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { WebPushSettings } from "./web-push-settings";
vi.mock("@/lib/api", async () => ({ ...await vi.importActual("@/lib/api"), api: vi.fn() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
it("explains iPhone Home Screen setup without asking permission or subscribing on opening the guide", () => {
  const requestPermission = vi.fn();
  vi.stubGlobal("Notification", { requestPermission });
  render(<WebPushSettings csrf="fixture" settings={{ language: "en", timezone: "Asia/Jerusalem", display_name: "", theme: "dark" }} t={(_he, en) => en} />);
  fireEvent.click(screen.getByText("Enable notifications on iPhone"));
  expect(screen.getByText(/Requires iOS 16.4 or later/)).toBeInTheDocument();
  expect(screen.getByText(/In the Share menu, choose Add to Home Screen/)).toBeInTheDocument();
  expect(requestPermission).not.toHaveBeenCalled();
});
it("loads sender setup before iPhone Home Screen installation without subscribing", async () => {
  const requestPermission = vi.fn();
  vi.stubGlobal("Notification", { requestPermission });
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("navigator", { standalone: false });
  vi.mocked(api).mockImplementation(async path => {
    if (path === "push/config") return { configured: false, contact: "", public_key: null, revision: 0 } as never;
    if (path === "push/subscriptions") return [] as never;
    throw Error("Unexpected subscription or send request");
  });
  render(<WebPushSettings csrf="fixture" settings={{ language: "en", timezone: "Asia/Jerusalem", display_name: "", theme: "dark" }} t={(_he, en) => en} />);
  fireEvent.click(screen.getByRole("button", { name: "Load Push settings" }));
  await screen.findByText("Push off in this browser");
  expect(screen.getByRole("button", { name: "Enable Push in this browser" })).toBeDisabled();
  expect(requestPermission).not.toHaveBeenCalled();
  expect(api).toHaveBeenCalledTimes(2);
});
