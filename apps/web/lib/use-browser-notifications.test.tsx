import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useBrowserNotifications } from "./use-browser-notifications";
import { setBrowserNotices } from "./browser-notifications";
import { api } from "./api";
import type { NotificationFeed } from "@/components/notification-center";

vi.mock("./api", () => ({ api: vi.fn() }));
const show = vi.fn(async () => {});
const oldWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker");
const oldLocks = Object.getOwnPropertyDescriptor(navigator, "locks");
const feed: NotificationFeed = {
  preferences: {
    enabled: true,
    tasks: true,
    conflicts: true,
    quiet_enabled: true,
    quiet_start: "22:00",
    quiet_end: "07:00",
  },
  items: [
    {
      id: "a".repeat(64),
      title: "Private fixture",
      kind: "overdue",
      target: "tasks",
      source_ids: ["t"],
      read: false,
    },
  ],
  unread: 1,
  quiet: false,
  truncated: false,
  conflicts_limited: false,
  stale_sources: [],
};
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setBrowserNotices(localStorage, true);
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("Notification", {
    permission: "granted",
    requestPermission: vi.fn(),
  });
  vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { ready: Promise.resolve({ showNotification: show }) },
  });
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: async (
        _name: string,
        _options: unknown,
        callback: (lock: object) => unknown,
      ) => callback({}),
    },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
  if (oldWorker) Object.defineProperty(navigator, "serviceWorker", oldWorker);
  else Reflect.deleteProperty(navigator, "serviceWorker");
  if (oldLocks) Object.defineProperty(navigator, "locks", oldLocks);
  else Reflect.deleteProperty(navigator, "locks");
});

it("refreshes eligibility rather than delivering a cached pre-quiet snapshot", async () => {
  vi.mocked(api).mockResolvedValue({ ...feed, quiet: true });
  renderHook(() => useBrowserNotifications(feed, "en", "Asia/Jerusalem"));
  await waitFor(() => expect(api).toHaveBeenCalledWith("notifications"));
  await act(async () => {
    await Promise.resolve();
  });
  expect(show).not.toHaveBeenCalled();
  expect(Notification.requestPermission).not.toHaveBeenCalled();
});

it("does not fall back to stale unread data when authenticated refresh fails", async () => {
  vi.mocked(api).mockRejectedValue(Error("offline"));
  const { result } = renderHook(() =>
    useBrowserNotifications(feed, "en", "Asia/Jerusalem"),
  );
  await waitFor(() => expect(result.current.error).toBe(true));
  expect(show).not.toHaveBeenCalled();
});
