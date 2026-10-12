import { reactive } from "vue"
import { api } from "./api"
import type { ImportColumn, ImportField, ImportInspection, ImportMapping } from "./types"

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

// --- the column-mapping panel -------------------------------------------------------------

/** What each field takes: a column ("3"), the same value for every row ("value") or nothing. */
export const SKIP = "skip"
export const FIXED = "value"

export interface MappingState {
  choice: Record<string, string>
  fixed: Record<string, string>
}

/** 1 -> "A", 27 -> "AA" (the column letters Excel shows). */
export function columnLetter(index: number): string {
  let n = index
  let out = ""
  while (n > 0) {
    const r = (n - 1) % 26
    out = String.fromCharCode(65 + r) + out
    n = Math.floor((n - 1) / 26)
  }
  return out
}

/** The mapping the panel starts with: the remembered one for this header row, else the server's guess. */
export function initialMapping(inspection: ImportInspection, remembered?: ImportMapping | null): MappingState {
  const state: MappingState = { choice: {}, fixed: {} }
  const count = inspection.columns.length
  const valid = (i: unknown): i is number => typeof i === "number" && Number.isInteger(i) && i >= 1 && i <= count
  for (const field of inspection.fields) {
    state.choice[field.key] = SKIP
    state.fixed[field.key] = ""
    const source = remembered ? remembered[field.key] : inspection.suggested[field.key]
    if (valid(source)) state.choice[field.key] = String(source)
    else if (source && typeof source === "object" && typeof source.value === "string") {
      state.choice[field.key] = FIXED
      state.fixed[field.key] = source.value
    }
  }
  return state
}

/** The `mapping` the server takes: field -> column index or {value}; skipped fields are left out. */
export function toPayload(state: MappingState, fields: ImportField[]): ImportMapping {
  const out: ImportMapping = {}
  for (const field of fields) {
    const choice = state.choice[field.key]
    if (choice === FIXED) {
      const value = (state.fixed[field.key] ?? "").trim()
      if (value) out[field.key] = { value }
    } else if (choice && choice !== SKIP) out[field.key] = Number(choice)
  }
  return out
}

/** Required fields with nothing connected. */
export function missingFields(state: MappingState, fields: ImportField[]): ImportField[] {
  const payload = toPayload(state, fields)
  return fields.filter((f) => f.required && payload[f.key] === undefined)
}

/** Columns of the file no field uses (empty columns without a header are left out). */
export function unusedColumns(state: MappingState, columns: ImportColumn[]): ImportColumn[] {
  const used = new Set(Object.values(state.choice))
  return columns.filter((c) => !used.has(String(c.index)) && (c.header || c.samples.length))
}

/** The standardisation note of one field ("Start: «9.30» → 09:30" starts with the field's label). */
export function noteFor(notes: string[], label: string): string | undefined {
  return notes.find((n) => n.startsWith(`${label}:`))
}

/** The key the mapping is remembered under: the file's header row. */
export function headerSignature(columns: ImportColumn[]): string {
  return columns.map((c) => c.header.trim()).join("|")
}

const STORE = "chronicle.import-mapping."
const REMEMBERED = 10 // header rows remembered per import

/** The last mapping used for a file with this header row (per import), if any. */
export function rememberedMapping(name: string, signature: string): ImportMapping | null {
  try {
    const all = JSON.parse(localStorage.getItem(STORE + name) || "{}") as Record<string, ImportMapping>
    const found = all[signature]
    return found && typeof found === "object" ? found : null
  } catch {
    return null
  }
}

export function rememberMapping(name: string, signature: string, mapping: ImportMapping): void {
  try {
    const all = JSON.parse(localStorage.getItem(STORE + name) || "{}") as Record<string, ImportMapping>
    delete all[signature]
    all[signature] = mapping
    const keys = Object.keys(all)
    for (const key of keys.slice(0, Math.max(0, keys.length - REMEMBERED))) delete all[key]
    localStorage.setItem(STORE + name, JSON.stringify(all))
  } catch {
    // private window or storage blocked: the panel just starts from the suggestions
  }
}
