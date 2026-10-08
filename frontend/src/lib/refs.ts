import { reactive } from "vue"
import { api } from "./api"
import { rowLabel, type Option } from "./resources"

/** Rows of admin resources used as options (branches, employees, shifts...), loaded once. */
const cache = reactive<Record<string, Record<string, unknown>[]>>({})
const loading: Record<string, Promise<void> | undefined> = {}

export function refRows(name: string): Record<string, unknown>[] {
  if (!cache[name] && !loading[name]) {
    loading[name] = api
      .get<Record<string, unknown>[]>(`/admin/${name}`)
      .then((rows) => {
        cache[name] = rows
      })
      .catch(() => {
        cache[name] = []
      })
      .finally(() => {
        loading[name] = undefined
      })
  }
  return cache[name] ?? []
}

export function refOptions(name: string): Option[] {
  return refRows(name).map((row) => ({ value: row.id as number, label: rowLabel(row) }))
}

export function refLabel(name: string, id: unknown): string {
  if (id === null || id === undefined || id === "") return ""
  const row = refRows(name).find((r) => r.id === id)
  return row ? rowLabel(row) : String(id)
}

/** Forget a resource after it changed, so pickers show the new rows. */
export function invalidateRef(name: string): void {
  delete cache[name]
}
