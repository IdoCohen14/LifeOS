import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  NotificationCenter,
  type NotificationFeed,
} from "./notification-center";

afterEach(cleanup);

it("snoozes only on explicit action and restores from the hidden tab", async () => {
  const onAction = vi.fn(async () => {});
  render(
    <NotificationCenter
      {...props}
      onAction={onAction}
      data={{
        ...feed,
        hidden: [{ ...feed.items[0], dismissed: true }],
        hidden_total: 1,
      }}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Notifications: 1 unread" }),
  );
  fireEvent.click(screen.getByText("More actions"));
  fireEvent.click(screen.getByRole("button", { name: "Snooze" }));
  expect(onAction).toHaveBeenCalledWith({
    id: "a".repeat(64),
    action: "snooze",
    minutes: 60,
  });
  fireEvent.click(screen.getByRole("button", { name: "Hidden (1)" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Restore notification" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Restore notification" }));
  expect(onAction).toHaveBeenCalledWith({
    id: "a".repeat(64),
    action: "restore",
  });
});
const feed: NotificationFeed = {
  preferences: {
    enabled: true,
    tasks: true,
    conflicts: true,
    quiet_enabled: true,
    quiet_start: "22:00",
    quiet_end: "07:00",
  },
  unread: 1,
  quiet: false,
  truncated: false,
  conflicts_limited: false,
  stale_sources: [],
  items: [
    {
      id: "a".repeat(64),
      kind: "overdue",
      title: "Notification fixture",
      due: "2026-10-25",
      target: "tasks",
      source_ids: ["task"],
      read: false,
    },
  ],
};
const props = {
  settings: {
    language: "en" as const,
    theme: "dark" as const,
    timezone: "Asia/Jerusalem",
    display_name: "",
  },
  t: (_he: string, en: string) => en,
  onRead: vi.fn(async () => {}),
  onSave: vi.fn(async () => {}),
  onOpen: vi.fn(),
  onRefresh: vi.fn(async () => {}),
};

it("opening is read-only and marking displayed unread requires its explicit control", () => {
  render(<NotificationCenter {...props} data={feed} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Notifications: 1 unread" }),
  );
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(props.onRead).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Mark displayed as read" }),
  );
  expect(props.onRead).toHaveBeenCalledWith(["a".repeat(64)]);
});

it("quiet hours suppress the badge but preserve the explicitly opened list", () => {
  render(<NotificationCenter {...props} data={{ ...feed, quiet: true }} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Notifications · Quiet hours" }),
  );
  expect(screen.getByText("Notification fixture")).toBeVisible();
  expect(screen.getByText(/Quiet hours are active/)).toBeVisible();
});
