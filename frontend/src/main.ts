import { createApp } from "vue"
import App from "./App.vue"
import { call } from "./lib/api"
import { __, setMessages } from "./lib/i18n"
import { registerServiceWorker } from "./lib/pwa"
import { refreshSession } from "./lib/session"
import { router } from "./router"
import "./style.css"

async function start() {
  // /hozur renders the boot data into the page; the Vite dev server does not, so ask the API.
  if (!window.hozur_boot) {
    try {
      await refreshSession()
      setMessages(await call<Record<string, string>>("hozur.api.pwa.translations"))
    } catch {
      window.location.href = "/login?redirect-to=" + encodeURIComponent(window.location.pathname)
      return
    }
  }
  const app = createApp(App)
  app.config.globalProperties.__ = __
  app.use(router)
  app.mount("#app")
  registerServiceWorker()
}

start()

declare module "vue" {
  interface ComponentCustomProperties {
    __: typeof __
  }
}
