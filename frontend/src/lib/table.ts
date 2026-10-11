/**
 * The logic behind components/DataTable.vue, kept free of Vue so it can be tested: Excel-like
 * column filters (a checklist of distinct values and a "contains" text), a free-text search
 * across columns and a Persian-aware sort with empty values always last.
 */
import { display, fa } from "./jalali"

export type ColumnType = "text" | "number" | "date" | "bool"

export interface TableColumn<Row = any> {
  key: string
  label: string
  /** The value used for sorting (and, without `format`, for display). Default: row[key]. */
  value?: (row: Row) => unknown
  /** The text shown in the cell, also what the value checklist and "contains" match. */
  format?: (row: Row) => string
  type?: ColumnType
  sortable?: boolean // default true
  filterable?: boolean // default true
  class?: string // added to the cells of this column
}

export type SortDir = "asc" | "desc"

export interface SortState {
  key: string
  dir: SortDir
}

export interface ColumnFilter {
  /** The display texts that are shown; null or missing = every value. */
  values?: string[] | null
  /** Keep only rows whose display text contains this. */
  contains?: string
}

export interface TableState {
  sort: SortState | null
  filters: Record<string, ColumnFilter>
}

export interface DistinctValue {
  text: string // "" for empty cells
  count: number
}

export const emptyState = (): TableState => ({ sort: null, filters: {} })

export function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === "" || (typeof value === "number" && Number.isNaN(value))
}

/** Text for searching: ASCII digits, Persian ی/ک, no half-spaces, lower case. */
export function normalize(text: string): string {
  return text
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/[يى]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/[‌‏‎]/g, "")
    .toLowerCase()
    .trim()
}

export function rawValue<Row>(column: TableColumn<Row>, row: Row): unknown {
  return column.value ? column.value(row) : (row as Record<string, unknown>)[column.key]
}

/** What the cell shows. Numbers and dates get Persian digits; booleans a check mark. */
export function cellText<Row>(column: TableColumn<Row>, row: Row): string {
  if (column.format) return column.format(row) ?? ""
  const value = rawValue(column, row)
  if (isEmpty(value)) return ""
  if (column.type === "bool" || typeof value === "boolean") return value ? "✓" : ""
  if (column.type === "date") return display(String(value))
  if (column.type === "number" || typeof value === "number") return fa(value)
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function asNumber(value: unknown): number {
  if (typeof value === "number") return value
  if (typeof value === "boolean") return value ? 1 : 0
  return Number(normalize(String(value)).replace(/,/g, ""))
}

/** Compares two non-empty values: numbers numerically, text the Persian way. */
export function compareValues(a: unknown, b: unknown, type?: ColumnType): number {
  const numeric =
    type === "number" || type === "bool" || (typeof a === "number" && typeof b === "number") ||
    (typeof a === "boolean" && typeof b === "boolean")
  if (numeric) {
    const x = asNumber(a)
    const y = asNumber(b)
    if (!Number.isNaN(x) && !Number.isNaN(y)) return x - y
  }
  const x = String(a)
  const y = String(b)
  // Jalali dates ("1405/07/14") and times are zero-padded: plain string order is date order
  if (type === "date") return x < y ? -1 : x > y ? 1 : 0
  return x.localeCompare(y, "fa", { numeric: true, sensitivity: "base" })
}

/** Sorts a copy of the rows; empty values stay last in both directions; ties keep their order. */
export function sortRows<Row>(rows: Row[], column: TableColumn<Row> | undefined, dir: SortDir): Row[] {
  if (!column) return [...rows]
  const sign = dir === "asc" ? 1 : -1
  return rows
    .map((row, index) => ({ row, index, value: rawValue(column, row) }))
    .sort((a, b) => {
      const ea = isEmpty(a.value)
      const eb = isEmpty(b.value)
      if (ea || eb) return ea === eb ? a.index - b.index : ea ? 1 : -1
      return sign * compareValues(a.value, b.value, column.type) || a.index - b.index
    })
    .map((item) => item.row)
}

export function filterActive(filter: ColumnFilter | undefined): boolean {
  return !!filter && (Array.isArray(filter.values) || !!filter.contains?.trim())
}

export function activeFilterCount(state: TableState): number {
  return Object.values(state.filters).filter(filterActive).length
}

function passes<Row>(column: TableColumn<Row>, filter: ColumnFilter | undefined, row: Row): boolean {
  if (!filterActive(filter)) return true
  const text = cellText(column, row)
  if (Array.isArray(filter!.values) && !filter!.values.includes(text)) return false
  const contains = normalize(filter!.contains ?? "")
  return !contains || normalize(text).includes(contains)
}

/** True when any column's display text contains every word of the search. */
export function matchesSearch<Row>(columns: TableColumn<Row>[], row: Row, search: string): boolean {
  const words = normalize(search).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const haystack = columns.map((c) => normalize(cellText(c, row))).join(" ")
  return words.every((word) => haystack.includes(word))
}

/** Rows that pass the search and every column filter (except the one named by `skip`). */
export function filterRows<Row>(
  rows: Row[],
  columns: TableColumn<Row>[],
  filters: Record<string, ColumnFilter>,
  search = "",
  skip?: string
): Row[] {
  const active = columns.filter((c) => c.key !== skip && filterActive(filters[c.key]))
  return rows.filter(
    (row) => active.every((c) => passes(c, filters[c.key], row)) && matchesSearch(columns, row, search)
  )
}

/** Filters, then sorts: what the table shows. */
export function applyTable<Row>(rows: Row[], columns: TableColumn<Row>[], state: TableState, search = ""): Row[] {
  const filtered = filterRows(rows, columns, state.filters, search)
  if (!state.sort) return filtered
  const column = columns.find((c) => c.key === state.sort!.key)
  return sortRows(filtered, column, state.sort.dir)
}

/**
 * The values a column's checklist offers: the display texts of the rows that pass the other
 * filters, in the column's sort order, empty last, with how many rows have each.
 */
export function distinctValues<Row>(
  rows: Row[],
  columns: TableColumn<Row>[],
  key: string,
  filters: Record<string, ColumnFilter> = {},
  search = ""
): DistinctValue[] {
  const column = columns.find((c) => c.key === key)
  if (!column) return []
  const seen = new Map<string, { count: number; value: unknown }>()
  for (const row of filterRows(rows, columns, filters, search, key)) {
    const text = cellText(column, row)
    const entry = seen.get(text)
    if (entry) entry.count++
    else seen.set(text, { count: 1, value: text === "" ? null : rawValue(column, row) })
  }
  const items = [...seen.entries()].map(([text, { count, value }]) => ({ text, count, value }))
  const sorted = sortRows(items, { key: "value", label: "", type: column.type, value: (i) => i.value }, "asc")
  return sorted.map(({ text, count }) => ({ text, count }))
}

/** Reads a saved table state; anything unreadable gives the empty state. */
export function loadState(storageKey: string | undefined): TableState {
  if (!storageKey) return emptyState()
  try {
    const saved = JSON.parse(localStorage.getItem(`hozur.table.${storageKey}`) || "null")
    if (!saved || typeof saved !== "object") return emptyState()
    const sort = saved.sort && typeof saved.sort.key === "string" && (saved.sort.dir === "asc" || saved.sort.dir === "desc")
      ? { key: saved.sort.key, dir: saved.sort.dir as SortDir }
      : null
    const filters = saved.filters && typeof saved.filters === "object" ? saved.filters : {}
    return { sort, filters }
  } catch {
    return emptyState()
  }
}

export function saveState(storageKey: string | undefined, state: TableState): void {
  if (!storageKey) return
  try {
    const filters = Object.fromEntries(Object.entries(state.filters).filter(([, f]) => filterActive(f)))
    localStorage.setItem(`hozur.table.${storageKey}`, JSON.stringify({ sort: state.sort, filters }))
  } catch {
    // private windows and blocked storage: the table simply forgets
  }
}
