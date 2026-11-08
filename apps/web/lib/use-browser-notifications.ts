"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import type { NotificationFeed } from "@/components/notification-center";
import {
  BROWSER_NOTICE_LOCK,
  browserQuietNow,
  deliverBrowserNotification,
  genericBrowserNotice,
  readBrowserNotices,
  setBrowserNotices,
} from "./browser-notifications";
import { api } from "./api";
import { PUSH_DEVICE_KEY } from "./web-push";

const CHANGE = "lifeos-browser-notices-change";
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("focus", callback);
  window.addEventListener(CHANGE, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("focus", callback);
    window.removeEventListener(CHANGE, callback);
  };
}
function permission() {
  return window.isSecureContext &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    "locks" in navigator
    ? Notification.permission
    : "unsupported";
}
function optedIn() {
  try {
    return readBrowserNotices(window.localStorage).enabled && !pushOptedIn();
  } catch {
    return false;
  }
}
function pushOptedIn() {
  try { return !!window.localStorage.getItem(PUSH_DEVICE_KEY); } catch { return false; }
}
async function registration() {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => reject(Error("worker_unavailable")), 5000);
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

export function useBrowserNotifications(
  feed: NotificationFeed | null,
  language: "he" | "en",
  zone: string,
) {
  const status = useSyncExternalStore(
    subscribe,
    permission,
    () => "unsupported" as const,
  );
  const pushActive = useSyncExternalStore(subscribe, pushOptedIn, () => false);
  const opted = useSyncExternalStore(subscribe, optedIn, () => false);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const enabled = opted && status === "granted";
  useEffect(() => {
    if (!enabled || !feed) return;
    let cancelled = false;
    const deliver = () => {
      if (cancelled || !document.hidden) return;
      void (async () => {
        const current = await api<NotificationFeed>("notifications");
        if (cancelled || !document.hidden || !optedIn()) return;
        await deliverBrowserNotification({
          storage: window.localStorage,
          locks: navigator.locks,
          feed: current,
          hidden: document.hidden,
          permission: Notification.permission,
          language,
          show: async (title, options) => {
            const worker = await registration();
            if (
              cancelled ||
              !document.hidden ||
              Notification.permission !== "granted" ||
              !optedIn() ||
              browserQuietNow(current.preferences, new Date(), zone)
            )
              throw Error("delivery_cancelled");
            await worker.showNotification(title, options);
          },
        });
      })().catch(() => {
        if (!cancelled) setError(true);
      });
    };
    deliver();
    document.addEventListener("visibilitychange", deliver);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", deliver);
    };
  }, [enabled, feed, language, zone]);
  async function toggle() {
    setBusy(true);
    setError(false);
    try {
      if (opted) {
        if ("locks" in navigator)
          await navigator.locks.request(BROWSER_NOTICE_LOCK, async () =>
            setBrowserNotices(window.localStorage, false),
          );
        else setBrowserNotices(window.localStorage, false);
      } else {
        if (status === "unsupported" || status === "denied" || pushOptedIn()) return;
        // Request immediately in this user gesture; never from an effect or timer.
        const allowed = await Notification.requestPermission();
        await navigator.locks.request(BROWSER_NOTICE_LOCK, async () =>
          setBrowserNotices(window.localStorage, allowed === "granted" && !pushOptedIn()),
        );
      }
    } catch {
      setError(true);
    } finally {
      window.dispatchEvent(new Event(CHANGE));
      setBusy(false);
    }
  }
  async function test() {
    setBusy(true);
    setError(false);
    try {
      if (!enabled || Notification.permission !== "granted")
        throw Error("permission_required");
      const worker = await registration();
      const notice = genericBrowserNotice(language);
      await worker.showNotification(notice.title, notice.options);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return { enabled, opted, status, error, busy, pushActive, toggle, test };
}
