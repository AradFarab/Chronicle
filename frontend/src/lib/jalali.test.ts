import { describe, expect, it } from "vitest"
import { addMonths, ascii, displayLong, fa, format, hm, monthLength, parse, weekday } from "./jalali"

describe("jalali", () => {
  it("formats and parses the stored form", () => {
    expect(format({ jy: 1405, jm: 7, jd: 4 })).toBe("1405/07/04")
    expect(parse("۱۴۰۵/۰۷/۱۴")).toEqual({ jy: 1405, jm: 7, jd: 14 })
    expect(parse("1405/12/30")).toBeNull() // 1405 is not a leap year
  })
  it("knows weekdays and month lengths", () => {
    expect(weekday({ jy: 1405, jm: 1, jd: 1 })).toBe(0) // Saturday
    expect(weekday({ jy: 1405, jm: 7, jd: 14 })).toBe(3) // Tuesday
    expect(monthLength(1403, 12)).toBe(30)
    expect(addMonths(1405, 12, 1)).toEqual({ jy: 1406, jm: 1 })
    expect(addMonths(1405, 1, -1)).toEqual({ jy: 1404, jm: 12 })
  })
  it("shows Persian digits", () => {
    expect(fa("1405/07/14")).toBe("۱۴۰۵/۰۷/۱۴")
    expect(ascii("۱۴۰۵")).toBe("1405")
    expect(hm(470)).toBe("۷:۵۰")
    expect(displayLong("1405/07/14")).toBe("سه‌شنبه ۱۴ مهر ۱۴۰۵")
  })
})
