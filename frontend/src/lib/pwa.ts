/** Register the service worker (public/sw.js, served at /sw.js so it controls the whole app). */
export function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // The app works without it; installing needs HTTPS (or localhost).
    })
  })
}
