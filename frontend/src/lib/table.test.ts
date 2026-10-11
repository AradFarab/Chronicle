import { afterEach, describe, expect, it } from "vitest"
import {
  activeFilterCount,
  applyTable,
  cellText,
  distinctValues,
  loadState,
  matchesSearch,
  normalize,
  saveState,
  sortRows,
  type TableColumn,
} from "./table"

interface Row {
  id: number
  name: string
  code: string
  hours: number | null
  jdate: string | null
  active: boolean
  dept: string | null
}

const rows: Row[] = [
  { id: 1, name: "ژاله", code: "E10", hours: 8, jdate: "1405/07/14", active: true, dept: "فروش" },
  { id: 2, name: "آرش", code: "E9", hours: 44, jdate: null, active: false, dept: "مالی" },
  { id: 3, name: "بهرام", code: "E100", hours: null, jdate: "1404/12/29", active: true, dept: "فروش" },
  { id: 4, name: "پریسا", code: "E2", hours: 7.5, jdate: "1405/01/01", active: true, dept: null },
]

const columns: TableColumn<Row>[] = [
  { key: "name", label: "Name" },
  { key: "code", label: "Code" },
  { key: "hours", label: "Hours", type: "number" },
  { key: "jdate", label: "Date", type: "date" },
  { key: "active", label: "Active", type: "bool" },
  { key: "dept", label: "Department" },
]
const col = (key: string) => columns.find((c) => c.key === key)!
const ids = (list: Row[]) => list.map((r) => r.id)

describe("table sorting", () => {
  it("sorts Persian text in the Persian alphabet order", () => {
    // آ < ب < پ < ژ
    expect(ids(sortRows(rows, col("name"), "asc"))).toEqual([2, 3, 4, 1])
    expect(ids(sortRows(rows, col("name"), "desc"))).toEqual([1, 4, 3, 2])
  })
  it("sorts numbers numerically and codes naturally", () => {
    expect(ids(sortRows(rows, col("hours"), "asc"))).toEqual([4, 1, 2, 3])
    expect(ids(sortRows(rows, col("code"), "asc"))).toEqual([4, 2, 1, 3]) // E2 E9 E10 E100
  })
  it("sorts Jalali dates and keeps empty values last in both directions", () => {
    expect(ids(sortRows(rows, col("jdate"), "asc"))).toEqual([3, 4, 1, 2])
    expect(ids(sortRows(rows, col("jdate"), "desc"))).toEqual([1, 4, 3, 2])
    expect(ids(sortRows(rows, col("hours"), "desc"))).toEqual([2, 1, 4, 3])
  })
  it("does not change the rows it is given", () => {
    const copy = [...rows]
    sortRows(rows, col("name"), "asc")
    expect(rows).toEqual(copy)
  })
})

describe("table filters", () => {
  it("shows cells with Persian digits", () => {
    expect(cellText(col("hours"), rows[1])).toBe("۴۴")
    expect(cellText(col("jdate"), rows[0])).toBe("۱۴۰۵/۰۷/۱۴")
    expect(cellText(col("active"), rows[1])).toBe("")
    expect(cellText({ key: "x", label: "", format: (r: Row) => `#${r.id}` }, rows[0])).toBe("#1")
  })
  it("keeps only the checked values", () => {
    const state = { sort: null, filters: { dept: { values: ["فروش"] } } }
    expect(ids(applyTable(rows, columns, state))).toEqual([1, 3])
    const blanks = { sort: null, filters: { dept: { values: [""] } } }
    expect(ids(applyTable(rows, columns, blanks))).toEqual([4])
  })
  it("matches 'contains' with either digit set and Arabic ي / ك", () => {
    const state = { sort: null, filters: { hours: { contains: "4" } } }
    expect(ids(applyTable(rows, columns, state))).toEqual([2])
    expect(ids(applyTable(rows, columns, { sort: null, filters: { jdate: { contains: "۱۴۰۵" } } }))).toEqual([1, 4])
    expect(normalize("علي كريمي")).toBe("علی کریمی")
  })
  it("combines filters, search and sort", () => {
    const state = { sort: { key: "name", dir: "desc" as const }, filters: { active: { values: ["✓"] } } }
    expect(ids(applyTable(rows, columns, state))).toEqual([1, 4, 3])
    expect(ids(applyTable(rows, columns, state, "فروش"))).toEqual([1, 3])
    expect(matchesSearch(columns, rows[0], "ژاله ۱۴۰۵")).toBe(true)
    expect(matchesSearch(columns, rows[0], "ژاله ۱۴۰۴")).toBe(false)
  })
  it("lists distinct values from the rows the other filters keep", () => {
    expect(distinctValues(rows, columns, "dept")).toEqual([
      { text: "فروش", count: 2 },
      { text: "مالی", count: 1 },
      { text: "", count: 1 },
    ])
    // a filter on the column itself does not hide its own choices
    const filters = { dept: { values: ["مالی"] }, active: { values: ["✓"] } }
    expect(distinctValues(rows, columns, "dept", filters)).toEqual([
      { text: "فروش", count: 2 },
      { text: "", count: 1 },
    ])
    expect(distinctValues(rows, columns, "hours").map((v) => v.text)).toEqual(["۷.۵", "۸", "۴۴", ""])
  })
  it("counts the active filters", () => {
    expect(activeFilterCount({ sort: null, filters: { a: {}, b: { contains: " " }, c: { values: [] } } })).toBe(1)
  })
})

describe("table state storage", () => {
  afterEach(() => {
    delete (globalThis as { localStorage?: unknown }).localStorage
  })
  it("survives storage that is missing or throws", () => {
    expect(loadState("x")).toEqual({ sort: null, filters: {} })
    ;(globalThis as { localStorage?: unknown }).localStorage = {
      getItem: () => {
        throw new Error("blocked")
      },
      setItem: () => {
        throw new Error("blocked")
      },
    }
    expect(() => saveState("x", { sort: null, filters: {} })).not.toThrow()
    expect(loadState("x")).toEqual({ sort: null, filters: {} })
  })
  it("round-trips the sort and the active filters", () => {
    const store: Record<string, string> = {}
    ;(globalThis as { localStorage?: unknown }).localStorage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => (store[k] = v),
    }
    saveState("t", { sort: { key: "name", dir: "desc" }, filters: { dept: { values: ["فروش"] }, code: {} } })
    expect(loadState("t")).toEqual({ sort: { key: "name", dir: "desc" }, filters: { dept: { values: ["فروش"] } } })
  })
})
