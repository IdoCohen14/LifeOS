// @vitest-environment node
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

it("notification click ignores payload URLs and opens only the fixed local center", async () => {
  const listeners: Record<string, (event: unknown) => void> = {};
  const openWindow = vi.fn(async () => {});
  const self = {
    addEventListener: (name: string, callback: (event: unknown) => void) => {
      listeners[name] = callback;
    },
    location: { origin: "http://127.0.0.1:3100" },
    clients: { matchAll: async () => [], openWindow },
  };
  runInNewContext(
    readFileSync(new URL("../public/sw.js", import.meta.url), "utf8"),
    { self, URL },
  );
  expect(typeof listeners.notificationclick).toBe("function");
  let pending: Promise<void> | undefined;
  const close = vi.fn();
  listeners.notificationclick({
    notification: {
      tag: "lifeos-attention",
      data: { url: "https://untrusted.invalid" },
      close,
    },
    waitUntil: (promise: Promise<void>) => {
      pending = promise;
    },
  });
  await pending;
  expect(openWindow).toHaveBeenCalledWith("/?notifications=open");
  expect(close).toHaveBeenCalledTimes(1);
});

it("focuses and messages an existing app window without navigating away from its draft", async () => {
  const listeners: Record<string, (event: unknown) => void> = {};
  const client = {
    url: "http://127.0.0.1:3100/?view=tasks",
    focus: vi.fn(async () => {}),
    postMessage: vi.fn(),
    navigate: vi.fn(),
  };
  const openWindow = vi.fn();
  const self = {
    addEventListener: (name: string, callback: (event: unknown) => void) => {
      listeners[name] = callback;
    },
    location: { origin: "http://127.0.0.1:3100" },
    clients: { matchAll: async () => [client], openWindow },
  };
  runInNewContext(
    readFileSync(new URL("../public/sw.js", import.meta.url), "utf8"),
    { self, URL },
  );
  let pending: Promise<void> | undefined;
  listeners.notificationclick({
    notification: { tag: "lifeos-attention", close: vi.fn() },
    waitUntil: (promise: Promise<void>) => {
      pending = promise;
    },
  });
  await pending;
  expect(client.focus).toHaveBeenCalledTimes(1);
  expect(client.postMessage).toHaveBeenCalledWith({
    type: "lifeos:open-notifications",
  });
  expect(client.navigate).not.toHaveBeenCalled();
  expect(openWindow).not.toHaveBeenCalled();
});
