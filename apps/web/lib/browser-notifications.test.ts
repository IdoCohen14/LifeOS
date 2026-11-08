import { expect, it, vi } from "vitest";
import {
  BROWSER_NOTICE_KEY,
  browserQuietNow,
  deliverBrowserNotification,
  readBrowserNotices,
  setBrowserNotices,
} from "./browser-notifications";

it("checks the actual quiet boundary again in workspace local wall time", () => {
  expect(
    browserQuietNow(
      feed.preferences,
      new Date("2026-10-26T19:59:59Z"),
      "Asia/Jerusalem",
    ),
  ).toBe(false);
  expect(
    browserQuietNow(
      feed.preferences,
      new Date("2026-10-26T20:00:00Z"),
      "Asia/Jerusalem",
    ),
  ).toBe(true);
  expect(
    browserQuietNow(
      feed.preferences,
      new Date("2026-10-27T05:00:00Z"),
      "Asia/Jerusalem",
    ),
  ).toBe(false);
  expect(
    browserQuietNow(
      feed.preferences,
      new Date("2026-10-26T20:00:00Z"),
      "America/New_York",
    ),
  ).toBe(false);
});
import type { NotificationFeed } from "@/components/notification-center";

const feed: NotificationFeed = {
  items: [
    {
      id: "a".repeat(64),
      kind: "overdue",
      title: "Private fixture title",
      due: "2026-10-25",
      target: "tasks",
      source_ids: ["task"],
      read: false,
    },
  ],
  unread: 1,
  quiet: false,
  preferences: {
    enabled: true,
    tasks: true,
    conflicts: true,
    quiet_enabled: true,
    quiet_start: "22:00",
    quiet_end: "07:00",
  },
  truncated: false,
  conflicts_limited: false,
  stale_sources: [],
};
const locks = {
  request: async (
    _name: string,
    _options: unknown,
    callback: (lock: object) => Promise<boolean>,
  ) => callback({}),
};

it("concurrent same-origin deliveries share the tab lock and cannot duplicate a batch", async () => {
  const storage = fixture();
  setBrowserNotices(storage, true);
  let release!: () => void;
  let held = false;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const serialized = {
    request: async (
      _name: string,
      _options: unknown,
      callback: (lock: unknown) => Promise<boolean>,
    ) => {
      if (held) return callback(null);
      held = true;
      try {
        return await callback({});
      } finally {
        held = false;
      }
    },
  };
  const show = vi.fn(async () => {
    await pending;
  });
  const input = {
    storage,
    show,
    locks: serialized,
    feed,
    hidden: true,
    permission: "granted" as const,
    language: "en" as const,
  };
  const first = deliverBrowserNotification(input);
  expect(await deliverBrowserNotification(input)).toBe(false);
  release();
  expect(await first).toBe(true);
  expect(await deliverBrowserNotification(input)).toBe(false);
  expect(show).toHaveBeenCalledTimes(1);
});
function fixture() {
  const storage = new Map<string, string>();
  return {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value);
    },
  };
}

it("requires opt-in, hidden page, unread data, granted permission and quiet/category eligibility", async () => {
  const storage = fixture(),
    show = vi.fn(async () => {});
  const base = {
    storage,
    show,
    locks,
    feed,
    hidden: true,
    permission: "granted" as const,
    language: "en" as const,
    now: 1000000,
  };
  expect(await deliverBrowserNotification(base)).toBe(false);
  setBrowserNotices(storage, true);
  for (const change of [
    { hidden: false },
    { permission: "denied" as const },
    { feed: null },
    { feed: { ...feed, quiet: true } },
    { feed: { ...feed, preferences: { ...feed.preferences, enabled: false } } },
    { feed: { ...feed, items: [{ ...feed.items[0], read: true }] } },
  ])
    expect(await deliverBrowserNotification({ ...base, ...change })).toBe(
      false,
    );
  expect(show).not.toHaveBeenCalled();
  expect(await deliverBrowserNotification(base)).toBe(true);
  expect(show.mock.calls[0]).not.toContain("Private fixture title");
  expect(JSON.stringify(show.mock.calls)).not.toContain(
    "Private fixture title",
  );
  expect(await deliverBrowserNotification(base)).toBe(false);
  expect(show).toHaveBeenCalledTimes(1);
});

it("uses a new snooze delivery key and reserves before display failure to prevent loops", async () => {
  const storage = fixture(),
    show = vi.fn(async () => {});
  setBrowserNotices(storage, true);
  const base = {
    storage,
    show,
    locks,
    feed,
    hidden: true,
    permission: "granted" as const,
    language: "he" as const,
    now: 1000000,
  };
  await deliverBrowserNotification(base);
  await deliverBrowserNotification({
    ...base,
    feed: { ...feed, items: [{ ...feed.items[0], snoozed_until: 900 }] },
  });
  expect(show).toHaveBeenCalledTimes(2);
  const broken = {
    ...base,
    feed: { ...feed, items: [{ ...feed.items[0], id: "b".repeat(64) }] },
    show: vi.fn(async () => {
      throw Error("OS blocked");
    }),
  };
  await expect(deliverBrowserNotification(broken)).rejects.toThrow(
    "OS blocked",
  );
  expect(await deliverBrowserNotification(broken)).toBe(false);
});

it("rejects malformed storage, bounds metadata and honors an unavailable tab lock", async () => {
  const storage = fixture();
  storage.setItem(BROWSER_NOTICE_KEY, "not-json");
  expect(readBrowserNotices(storage).enabled).toBe(false);
  storage.setItem(
    BROWSER_NOTICE_KEY,
    JSON.stringify({
      enabled: true,
      claims: Array.from({ length: 1000 }, (_, i) => ({
        key: `${"a".repeat(64)}:${i}`,
        at: 1000000,
      })),
    }),
  );
  expect(readBrowserNotices(storage).claims.length).toBeLessThanOrEqual(200);
  const show = vi.fn(async () => {});
  const unavailable = {
    request: async (
      _name: string,
      _options: unknown,
      callback: (lock: null) => Promise<boolean>,
    ) => callback(null),
  };
  expect(
    await deliverBrowserNotification({
      storage,
      show,
      locks: unavailable,
      feed,
      hidden: true,
      permission: "granted",
      language: "en",
    }),
  ).toBe(false);
  expect(show).not.toHaveBeenCalled();
});
it.each(['new_mail','upcoming_event','moodle_update'] as const)('keeps in-app-only %s out of browser delivery',async(kind)=>{
 const storage=fixture();setBrowserNotices(storage,true);const show=vi.fn(async()=>{});
 const mailFeed:NotificationFeed={...feed,items:[{...feed.items[0],kind,target:'dashboard'}]};
 expect(await deliverBrowserNotification({storage,locks,feed:mailFeed,hidden:true,permission:'granted',language:'en',show})).toBe(false);
 expect(show).not.toHaveBeenCalled();
});
