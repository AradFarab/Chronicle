import { createApp } from "vue"
import App from "./App.vue"
import { api, setUnauthorizedHandler } from "./lib/api"
import { __, setMessages } from "./lib/i18n"
import { registerServiceWorker } from "./lib/pwa"
import { refreshSession, session } from "./lib/session"
import { router } from "./router"
import "./style.css"

async function start() {
  const [, messages] = await Promise.all([
    refreshSession(),
    api.get<Record<string, string>>("/translations/fa").catch(() => ({})),
  ])
  setMessages(messages)
  setUnauthorizedHandler(() => {
    if (router.currentRoute.value.name !== "login") {
      router.push({ name: "login", query: { next: router.currentRoute.value.fullPath } })
    }
  })
  const app = createApp(App)
  app.config.globalProperties.__ = __
  app.config.globalProperties.session = session
  app.use(router)
  app.mount("#app")
  registerServiceWorker()
}

start()

declare module "vue" {
  interface ComponentCustomProperties {
    __: typeof __
    session: typeof session
  }
}
