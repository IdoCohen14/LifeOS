import type { NotificationFeed } from "@/components/notification-center";

export const BROWSER_NOTICE_KEY = "lifeos.browser-notices.v1";
export const BROWSER_NOTICE_LOCK = "lifeos-browser-notice-delivery";
const MAX_CLAIMS = 200;
const AGE = 30 * 86400000;
type Store = Pick<Storage, "getItem" | "setItem">;
type Claim = { key: string; at: number };
type State = { enabled: boolean; claims: Claim[] };
type Locks = {
  request: (
    name: string,
    options: { ifAvailable: true },
    callback: (lock: unknown) => Promise<boolean>,
  ) => Promise<boolean>;
};

export function readBrowserNotices(storage: Store): State {
  try {
    const raw = storage.getItem(BROWSER_NOTICE_KEY);
    if (!raw || raw.length > 50000) return { enabled: false, claims: [] };
    const value = JSON.parse(raw);
    if (typeof value?.enabled !== "boolean" || !Array.isArray(value.claims))
      return { enabled: false, claims: [] };
    return {
      enabled: value.enabled,
      claims: value.claims
        .filter(
          (row: Claim) =>
            row &&
            typeof row.key === "string" &&
            /^[a-f0-9]{64}:\d{1,12}$/.test(row.key) &&
            Number.isSafeInteger(row.at) &&
            row.at >= 0,
        )
        .slice(0, MAX_CLAIMS),
    };
  } catch {
    return { enabled: false, claims: [] };
  }
}

export function setBrowserNotices(storage: Store, enabled: boolean) {
  storage.setItem(
    BROWSER_NOTICE_KEY,
    JSON.stringify({ ...readBrowserNotices(storage), enabled }),
  );
}

export function genericBrowserNotice(language: "he" | "en") {
  return {
    title: "LifeOS",
    options: {
      body:
        language === "he"
          ? "יש עדכונים חדשים במרכז ההתראות שלך."
          : "There are updates in your notification center.",
      tag: "lifeos-attention",
      icon: "/icon-192.png",
      data: { kind: "lifeos-inapp" },
    } satisfies NotificationOptions,
  };
}

export function browserQuietNow(
  preferences: NotificationFeed["preferences"],
  now: Date,
  zone: string,
) {
  if (!preferences.quiet_enabled) return false;
  const local = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(now);
  const start = preferences.quiet_start,
    end = preferences.quiet_end;
  return (
    start === end ||
    (start < end
      ? start <= local && local < end
      : local >= start || local < end)
  );
}

export async function deliverBrowserNotification({
  storage,
  locks,
  feed,
  hidden,
  permission,
  language,
  show,
  now = Date.now(),
}: {
  storage: Store;
  locks: Locks;
  feed: NotificationFeed | null;
  hidden: boolean;
  permission: NotificationPermission;
  language: "he" | "en";
  show: (title: string, options: NotificationOptions) => Promise<void>;
  now?: number;
}) {
  if (
    !feed ||
    !hidden ||
    permission !== "granted" ||
    feed.quiet ||
    !feed.preferences.enabled
  )
    return false;
  return locks.request(
    BROWSER_NOTICE_LOCK,
    { ifAvailable: true },
    async (lock) => {
      if (!lock) return false;
      const state = readBrowserNotices(storage);
      if (!state.enabled) return false;
      const claims = state.claims.filter(
        (row) => row.at <= now && row.at > now - AGE,
      );
      const seen = new Set(claims.map((row) => row.key));
      const fresh = [
        ...new Set(
          feed.items
            .filter((item) => !item.read && item.kind !== "new_mail" && item.kind !== "upcoming_event" && item.kind !== "moodle_update")
            .map((item) => `${item.id}:${item.snoozed_until ?? 0}`),
        ),
      ].filter((key) => !seen.has(key));
      if (!fresh.length) return false;
      // Claim before display: storage/OS failures cannot create a repeated alert loop.
      storage.setItem(
        BROWSER_NOTICE_KEY,
        JSON.stringify({
          enabled: true,
          claims: [...fresh.map((key) => ({ key, at: now })), ...claims].slice(
            0,
            MAX_CLAIMS,
          ),
        }),
      );
      const notice = genericBrowserNotice(language);
      await show(notice.title, notice.options);
      return true;
    },
  );
}
