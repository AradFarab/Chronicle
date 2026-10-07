/**
 * Register the service worker. It is served by the API with Service-Worker-Allowed so it can
 * control /hozur/ (the app's own assets live under /assets/hozur/).
 */
export function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/api/method/hozur.api.pwa.service_worker", { scope: "/hozur/" }).catch(() => {
      // The app works without it; installing needs HTTPS (or localhost).
    })
  })
}
