import { readFileSync } from "node:fs";
import vm from "node:vm";
import { expect, it, vi } from "vitest";

const origin = "https://lifeos-fixture.example.test";
const destination = "/?view=timetable&day=2026-11-05";

function worker(open: boolean) {
  const listeners = new Map<string, (event: unknown) => void>();
  const client = {
    url: `${origin}/?view=academic`,
    navigate: vi.fn().mockResolvedValue(undefined),
    focus: vi.fn().mockResolvedValue(undefined),
    postMessage: vi.fn(),
  };
  const openWindow = vi.fn().mockResolvedValue(undefined);
  const context = vm.createContext({
    self: {
      location: { origin },
      addEventListener: (type: string, handler: (event: unknown) => void) => listeners.set(type, handler),
      clients: { matchAll: vi.fn().mockResolvedValue(open ? [client] : []), openWindow },
    },
    Date, Intl, URL,
  });
  vm.runInContext(readFileSync("public/sw.js", "utf8"), context);
  async function click(url?: string, tag = "lifeos-attention") {
    const close = vi.fn();
    let completion: Promise<unknown> | undefined;
    listeners.get("notificationclick")!({
      notification: { tag, data: url ? { url } : {}, close },
      waitUntil: (pending: Promise<unknown>) => { completion = pending; },
    });
    await completion;
    return close;
  }
  return { client, openWindow, click };
}

it("a lesson tap navigates the existing LifeOS window and focuses it", async () => {
  const { client, openWindow, click } = worker(true);
  const close = await click(destination);
  expect(close).toHaveBeenCalledOnce();
  expect(client.navigate).toHaveBeenCalledWith(destination);
  expect(client.focus).toHaveBeenCalledOnce();
  expect(client.postMessage).not.toHaveBeenCalled();
  expect(openWindow).not.toHaveBeenCalled();
});

it("a lesson tap opens its dated timetable when no LifeOS window exists", async () => {
  const { client, openWindow, click } = worker(false);
  await click(destination);
  expect(openWindow).toHaveBeenCalledWith(destination);
  expect(client.navigate).not.toHaveBeenCalled();
});

it.each([undefined, "https://outside.example.test/", "/?view=timetable&day=2026-02-31"])(
  "an ordinary or unsupported destination keeps the notification center action: %s",
  async (url) => {
    const { client, openWindow, click } = worker(true);
    await click(url);
    expect(client.navigate).not.toHaveBeenCalled();
    expect(client.focus).toHaveBeenCalledOnce();
    expect(client.postMessage).toHaveBeenCalledWith({ type: "lifeos:open-notifications" });
    expect(openWindow).not.toHaveBeenCalled();
  },
);

it("an ordinary notice opens the inbox when LifeOS is closed", async () => {
  const { openWindow, click } = worker(false);
  await click();
  expect(openWindow).toHaveBeenCalledWith("/?notifications=open");
});

it("ignores notifications outside the LifeOS notification channel", async () => {
  const { client, openWindow, click } = worker(true);
  const close = await click(destination, "other-notification");
  expect(close).not.toHaveBeenCalled();
  expect(client.navigate).not.toHaveBeenCalled();
  expect(client.focus).not.toHaveBeenCalled();
  expect(openWindow).not.toHaveBeenCalled();
});
