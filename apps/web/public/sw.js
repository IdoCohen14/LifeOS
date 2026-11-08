const CACHE = "lifeos-static-v4";
const STATIC = [
  "/offline.html",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/manifest.webmanifest",
];
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(STATIC))
      .then(() => self.skipWaiting()),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("lifeos-static-") && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    url.origin !== self.location.origin ||
    event.request.method !== "GET" ||
    url.pathname.startsWith("/api/")
  )
    return;
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/offline.html")),
    );
    return;
  }
  if (STATIC.includes(url.pathname))
    event.respondWith(
      caches
        .match(event.request)
        .then((cached) => cached || fetch(event.request)),
    );
});

self.addEventListener("notificationclick", (event) => {
  if (event.notification.tag !== "lifeos-attention") return;
  event.notification.close();
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      const existing = windows.find(
        (client) => new URL(client.url).origin === self.location.origin,
      );
      const destination = lessonDestination(event.notification.data?.url);
      if (existing) {
        if (destination) await existing.navigate(destination);
        await existing.focus();
        if (!destination) existing.postMessage({ type: "lifeos:open-notifications" });
      } else {
        await self.clients.openWindow(destination || "/?notifications=open");
      }
    })(),
  );
});

function lessonDestination(value) {
  if (typeof value !== 'string' || !/^\/\?view=timetable&day=\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const day = value.slice(-10), date = new Date(day + 'T12:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0,10) === day ? value : null;
}

function pushNotice(value, now) {
  if (!value || Array.isArray(value)) return null;
  const visible = value.visible_required === true;
  const detailed = Object.prototype.hasOwnProperty.call(value, 'notice_title') || Object.prototype.hasOwnProperty.call(value, 'notice_body');
  if (detailed && (typeof value.notice_title !== 'string' || typeof value.notice_body !== 'string' || !value.notice_title.trim() || value.notice_title.length > 100 || value.notice_body.length > 300 || /[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/.test(value.notice_title + value.notice_body))) return null;
  const keys = ['expires','id','language','quiet_enabled','quiet_end','quiet_start','zone', ...(visible ? ['visible_required'] : []), ...(detailed ? ['notice_title','notice_body'] : [])].sort().join(',');
  if (Object.keys(value).sort().join(',') !== keys) return null;
  if (!/^[a-f0-9]{64}$/.test(value.id) || !['he', 'en'].includes(value.language) || typeof value.zone !== 'string' || value.zone.length > 80 || typeof value.quiet_enabled !== 'boolean' || !Number.isSafeInteger(value.expires) || (!visible && value.expires * 1000 <= now) || value.expires * 1000 > now + 600000) return null;
  const clock = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/;
  if (!clock.test(value.quiet_start) || !clock.test(value.quiet_end)) return null;
  try {
    const local = new Intl.DateTimeFormat('en-GB', { timeZone: value.zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(now));
    const start = value.quiet_start, end = value.quiet_end;
    if (!visible && value.quiet_enabled && (start === end || (start < end ? start <= local && local < end : local >= start || local < end))) return null;
  } catch { return null; }
  const body = visible ? (value.language === 'he' ? 'פתחו את LifeOS לצפייה במרכז ההתראות.' : 'Open LifeOS to view your notification center.')
    : (value.language === 'he' ? 'יש עדכונים חדשים במרכז ההתראות שלך.' : 'There are updates in your notification center.');
  const freshCopy = detailed && value.expires * 1000 > now;
  const lesson = freshCopy && /^(?:שיעור הבא|Next class) — /.test(value.notice_title) && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} · /.test(value.notice_body);
  const destination = lesson ? lessonDestination('/?view=timetable&day=' + value.notice_body.slice(0,10)) : null;
  return { title: freshCopy ? value.notice_title : 'LifeOS', options: { body: freshCopy ? value.notice_body : body, tag: 'lifeos-attention', renotify: false, icon: '/icon-192.png', data: { kind: 'lifeos-inapp', ...(destination ? {url:destination} : {}) } } };
}

function claimPushDelivery(id, now) {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open('lifeos-push-notices-v1', 1);
    open.onupgradeneeded = () => { const store = open.result.createObjectStore('claims', { keyPath: 'id' }); store.createIndex('at', 'at'); };
    open.onerror = () => reject(Error('push_metadata_unavailable'));
    open.onsuccess = () => {
      const db = open.result;
      const transaction = db.transaction('claims', 'readwrite');
      const store = transaction.objectStore('claims');
      let claimed = false;
      const previous = store.get(id);
      previous.onsuccess = () => {
        if (previous.result && previous.result.at >= now - 30 * 86400000) return;
        claimed = true; store.put({ id, at: now });
        let count = 0, scanned = 0;
        const request = store.index('at').openCursor(null, 'prev');
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor) return;
          if (++scanned > 500) { store.clear(); store.put({ id, at: now }); return; }
          if (cursor.primaryKey !== id && (++count >= 200 || cursor.value.at < now - 30 * 86400000)) cursor.delete();
          cursor.continue();
        };
      };
      transaction.oncomplete = () => { db.close(); resolve(claimed); };
      transaction.onerror = transaction.onabort = () => { db.close(); reject(Error('push_metadata_unavailable')); };
    };
  });
}

async function handleLifeosPush(value) {
  const notice = pushNotice(value, Date.now());
  if (notice && value.visible_required === true) {
    // Apple forbids silent deliveries. Quiet hours are checked by the server;
    // TTL=0 avoids offline queues. Repeated deliveries replace the same tag.
    await self.registration.showNotification(notice.title, notice.options);
    return true;
  }
  if (!notice || !await claimPushDelivery(value.id, Date.now())) return false;
  // Claim precedes display: OS/display failure may miss a notice, never a retry loop.
  if (!pushNotice(value, Date.now())) return false;
  await self.registration.showNotification(notice.title, notice.options);
  return true;
}
self.addEventListener('push', event => {
  event.waitUntil((async () => {
    if (!event.data) return;
    const text = event.data.text();
    if (text.length > 1024) return;
    let value;
    try { value = JSON.parse(text); } catch { return; }
    await handleLifeosPush(value);
  })().catch(() => {}));
});
