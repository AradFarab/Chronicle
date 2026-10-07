// Hozur PWA service worker: cache the app shell, keep data (/api) always fresh.
const CACHE = "hozur-v2"
self.addEventListener("install", () => self.skipWaiting())
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/fonts/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(event.request)
        const network = fetch(event.request).then((response) => {
          if (response.ok) cache.put(event.request, response.clone())
          return response
        })
        return cached || network
      })
    )
    return
  }
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(
        () =>
          new Response(
            '<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body style="font-family:Tahoma,sans-serif;text-align:center;padding:4rem 1rem">اتصال به سرور برقرار نیست. دوباره امتحان کنید.</body></html>',
            { headers: { "Content-Type": "text/html; charset=utf-8" } }
          )
      )
    )
  }
})
