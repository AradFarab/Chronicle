import { describe, expect, it } from "vitest"
import { columnLetter, initialMapping, missingFields, noteFor, toPayload, unusedColumns } from "./imports"
import type { ImportInspection } from "./types"

const inspection: ImportInspection = {
  sheets: ["Sheet1"],
  sheet: "Sheet1",
  header_row: 1,
  row_count: 2,
  columns: [
    { index: 1, header: "Start", samples: ["9.30"] },
    { index: 2, header: "Name", samples: ["Office"] },
    { index: 3, header: "Notes", samples: [] },
    { index: 4, header: "", samples: [] },
  ],
  fields: [
    { key: "name", label: "Name", kind: "text", required: true, help: "", example: "", choices: [] },
    { key: "start_time", label: "Start", kind: "time", required: true, help: "", example: "", choices: [] },
    { key: "shift_type", label: "Type", kind: "choice", required: false, help: "", example: "", choices: ["Fixed"] },
  ],
  suggested: { name: 2, start_time: 1, shift_type: null },
}

describe("import mapping", () => {
  it("names columns like Excel", () => {
    expect([1, 26, 27, 52, 703].map(columnLetter)).toEqual(["A", "Z", "AA", "AZ", "AAA"])
  })

  it("starts from the suggestions and sends indexes and fixed values", () => {
    const state = initialMapping(inspection)
    expect(state.choice).toEqual({ name: "2", start_time: "1", shift_type: "skip" })
    state.choice.shift_type = "value"
    state.fixed.shift_type = " Fixed "
    expect(toPayload(state, inspection.fields)).toEqual({ name: 2, start_time: 1, shift_type: { value: "Fixed" } })
    expect(unusedColumns(state, inspection.columns).map((c) => c.index)).toEqual([3])
  })

  it("prefers a remembered mapping and drops columns the file does not have", () => {
    const state = initialMapping(inspection, { name: 9, start_time: 1, shift_type: { value: "Fixed" } })
    expect(state.choice).toEqual({ name: "skip", start_time: "1", shift_type: "value" })
    expect(missingFields(state, inspection.fields).map((f) => f.key)).toEqual(["name"])
  })

  it("finds the note of a field", () => {
    expect(noteFor(["Start: «9.30» → 09:30"], "Start")).toBe("Start: «9.30» → 09:30")
    expect(noteFor(["Start: «9.30» → 09:30"], "End")).toBeUndefined()
  })
})
