import { reactive } from "vue"
import { api } from "./api"

/** The Excel import specs the server offers (GET /import), loaded once: name -> title. */
const specs = reactive<{ loaded: boolean; names: string[] }>({ loaded: false, names: [] })
let loading: Promise<void> | undefined

export function hasImport(name: string): boolean {
  if (!specs.loaded && !loading) {
    loading = api
      .get<{ name: string }[]>("/import")
      .then((rows) => {
        specs.names = rows.map((r) => r.name)
      })
      .catch(() => undefined)
      .finally(() => {
        specs.loaded = true
        loading = undefined
      })
  }
  return specs.names.includes(name)
}
