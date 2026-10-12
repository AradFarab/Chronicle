import { describe, expect, it } from "vitest"
import {
  autoName,
  barsFromShift,
  clipToDay,
  clock,
  clockAfter,
  clockToShiftMinute,
  dragTo,
  findIdentical,
  hitTest,
  hourTicks,
  minuteToFraction,
  parseClock,
  positionToMinute,
  pressAction,
  removeBar,
  setWork,
  shapeKey,
  shiftFromBars,
  snap,
  spanOf,
  spill,
  timelineEnd,
  validateBars,
  workMinutes,
  type Bar,
} from "./timeline"

const work = (start: number, end: number): Bar => ({ kind: "work", start, end })
const brk = (start: number, end: number): Bar => ({ kind: "break", start, end })
const ot = (start: number, end: number): Bar => ({ kind: "overtime", start, end })
const DAY_VIEW = { step: 15, from: 0, to: 1440 }

describe("timeline", () => {
  it("reads and writes clock times", () => {
    expect(parseClock("09:30")).toBe(570)
    expect(parseClock("18:00:00")).toBe(1080)
    expect(parseClock("۰۹:۳۰")).toBe(570)
    expect(parseClock("25:00")).toBeNull()
    expect(parseClock(null)).toBeNull()
    expect(clock(1500)).toBe("01:00")
    expect(clock(1440)).toBe("00:00")
  })

  it("knows when a shift ends the next day", () => {
    expect(spanOf("09:00", "17:00")).toEqual(work(540, 1020))
    expect(spanOf("18:00", "06:00")).toEqual(work(1080, 1800))
    expect(spanOf("08:00", "08:00")).toEqual(work(480, 1920)) // a 24-hour shift
    expect(spanOf(null, "06:00")).toBeNull()
  })

  it("puts typed times of a night shift on the right day", () => {
    const night = work(1080, 1800)
    expect(clockToShiftMinute("01:00", night)).toBe(1500)
    expect(clockToShiftMinute("17:00", night)).toBe(1020) // an overtime window before the shift
    expect(clockToShiftMinute("12:30", work(540, 1020))).toBe(750)
    expect(clockAfter("01:30", 1500)).toBe(1530)
    expect(clockAfter("00:30", 1410)).toBe(1470)
  })

  it("converts positions right-to-left and snaps", () => {
    // offset is measured from the right edge, where 00:00 is
    expect(positionToMinute(0, 960, 0, 1440)).toBe(0)
    expect(positionToMinute(480, 960, 0, 1440)).toBe(720)
    expect(positionToMinute(2000, 960, 0, 1440)).toBe(1440)
    expect(minuteToFraction(1500, 0, 1800)).toBeCloseTo(1500 / 1800)
    expect(snap(752, 5)).toBe(750)
    expect(snap(752, 15)).toBe(750)
    expect(snap(760, 30)).toBe(750)
    expect(snap(766, 30)).toBe(780)
  })

  it("extends the view into the next morning", () => {
    expect(timelineEnd([work(540, 1020)])).toBe(1440)
    expect(timelineEnd([work(1080, 1440)])).toBe(1800)
    expect(timelineEnd([work(1080, 1800)])).toBe(1980)
    expect(timelineEnd([work(540, 1020)], true)).toBe(1800)
    expect(timelineEnd([work(480, 1920), ot(1920, 2880)])).toBe(2880)
    expect(hourTicks(0, 1440, 3).filter((t) => t.label).map((t) => t.label)).toEqual([
      "00", "03", "06", "09", "12", "15", "18", "21", "00",
    ])
  })

  it("turns a shift into bars and back", () => {
    const shift = {
      shift_type: "fixed",
      start_time: "18:00",
      end_time: "06:00",
      segments: [{ kind: "break" as const, start_minute: 1500, end_minute: 1530 }],
    }
    const bars = barsFromShift(shift)
    expect(bars).toEqual([work(1080, 1800), brk(1500, 1530)])
    expect(shiftFromBars(bars)).toEqual({
      start_time: "18:00",
      end_time: "06:00",
      segments: [{ kind: "break", start_minute: 1500, end_minute: 1530 }],
    })
    expect(shiftFromBars([])).toEqual({ start_time: null, end_time: null, segments: [] })
  })

  it("counts scheduled work without the breaks (Article 51)", () => {
    expect(workMinutes([work(540, 1020), brk(750, 795), ot(1020, 1140)])).toBe(435)
    expect(workMinutes([brk(750, 795)])).toBe(0)
  })

  it("validates like the server", () => {
    expect(validateBars([work(540, 1020), brk(750, 795), ot(1020, 1140)])).toEqual([])
    expect(validateBars([])).toEqual(["Draw the working hours"])
    expect(validateBars([work(540, 1020), brk(1000, 1050)])).toEqual(["The break must be inside the shift"])
    expect(validateBars([work(540, 1020), ot(960, 1080)])).toEqual([
      "An overtime window must be before the start or after the end of the shift",
    ])
    // a flexible shift may have an overtime window inside its span
    expect(validateBars([work(420, 1140), ot(960, 1080)], "flexible")).toEqual([])
    expect(validateBars([work(540, 1020), brk(700, 760), brk(750, 800)])).toEqual(["Breaks overlap each other"])
    expect(validateBars([work(540, 1020), ot(1020, 1100), ot(1080, 1140)])).toEqual([
      "Overtime windows overlap each other",
    ])
    // a night shift with a break after midnight
    expect(validateBars([work(1080, 1800), brk(1500, 1530)])).toEqual([])
  })

  it("finds the edge or body under the pointer", () => {
    const bars = [work(540, 1020), brk(750, 795), ot(1020, 1140)]
    expect(hitTest(bars, 600, 10)).toEqual({ index: 0, part: "body" })
    expect(hitTest(bars, 770, 5)).toEqual({ index: 1, part: "body" }) // the break lies on top
    expect(hitTest(bars, 544, 10)).toEqual({ index: 0, part: "start" })
    // at the shared 17:00 edge the bar the pointer is inside wins
    expect(hitTest(bars, 1018, 10)).toEqual({ index: 0, part: "end" })
    expect(hitTest(bars, 1022, 10)).toEqual({ index: 2, part: "start" })
    expect(hitTest(bars, 300, 10)).toBeNull()
  })

  it("decides what a press starts", () => {
    const bars = [work(540, 1020), brk(750, 795)]
    // the work tool moves the working hours; the break tool draws a break on them
    expect(pressAction(bars, 600, 10, "work")).toMatchObject({ type: "move", index: 0 })
    expect(pressAction(bars, 600, 10, "break")).toMatchObject({ type: "draw", kind: "break", anchor: 600 })
    // an existing break is moved, an edge of the working hours resized, whatever the tool
    expect(pressAction(bars, 770, 5, "break")).toMatchObject({ type: "move", index: 1 })
    expect(pressAction(bars, 1018, 10, "break")).toMatchObject({ type: "resize", index: 0, edge: "end" })
    // overtime windows go over the working hours of a flexible shift only
    expect(pressAction(bars, 600, 10, "overtime")).toMatchObject({ type: "move", index: 0 })
    expect(pressAction(bars, 600, 10, "overtime", "flexible")).toMatchObject({ type: "draw", kind: "overtime" })
    // empty space draws; without a tool (the pattern grid's palette) nothing happens
    expect(pressAction(bars, 1200, 10, "overtime")).toMatchObject({ type: "draw", kind: "overtime" })
    expect(pressAction(bars, 1200, 10, null)).toBeNull()
  })

  it("draws, moves and resizes bars", () => {
    const empty: Bar[] = []
    const drawn = dragTo({ type: "draw", kind: "work", anchor: 1022, original: empty }, 538, DAY_VIEW)
    expect(drawn).toEqual([work(540, 1020)])
    const lunch = dragTo({ type: "draw", kind: "break", anchor: 748, original: drawn }, 797, DAY_VIEW)
    expect(lunch).toEqual([work(540, 1020), brk(750, 795)])
    // a click without a drag draws nothing
    expect(dragTo({ type: "draw", kind: "break", anchor: 750, original: drawn }, 752, DAY_VIEW)).toBe(drawn)
    // moving the working hours carries their breaks
    expect(dragTo({ type: "move", index: 0, grab: 600, original: lunch }, 660, DAY_VIEW)).toEqual([
      work(600, 1080),
      brk(810, 855),
    ])
    // a bar stays inside the view
    expect(dragTo({ type: "move", index: 1, grab: 760, original: lunch }, 0, DAY_VIEW)).toEqual([
      work(540, 1020),
      brk(0, 45),
    ])
    expect(dragTo({ type: "resize", index: 0, edge: "end", original: lunch }, 1082, DAY_VIEW)).toEqual([
      work(540, 1080),
      brk(750, 795),
    ])
    // an edge cannot pass the other edge
    expect(dragTo({ type: "resize", index: 1, edge: "start", original: lunch }, 900, DAY_VIEW)).toEqual([
      work(540, 1020),
      brk(780, 795),
    ])
  })

  it("draws a night shift into the next morning", () => {
    const view = { step: 30, from: 0, to: 1800 }
    const night = dragTo({ type: "draw", kind: "work", anchor: 1080, original: [] }, 1800, view)
    expect(shiftFromBars(night)).toMatchObject({ start_time: "18:00", end_time: "06:00" })
    // a night shift on a 24-hour pattern row keeps its morning when moved
    const row = { step: 30, from: 0, to: 1440 }
    expect(dragTo({ type: "move", index: 0, grab: 1200, original: night }, 1140, row)).toEqual([work(1020, 1740)])
  })

  it("redraws the working hours and drops what no longer fits", () => {
    const bars = [work(540, 1020), brk(750, 795), ot(1020, 1140)]
    expect(setWork(bars, 480, 720)).toEqual([work(480, 720), ot(1020, 1140)])
    expect(setWork(bars, 540, 1080)).toEqual([work(540, 1080), brk(750, 795)])
    expect(setWork(bars, 540, 1080, "flexible")).toEqual([work(540, 1080), brk(750, 795), ot(1020, 1140)])
    expect(removeBar(bars, 0)).toEqual([ot(1020, 1140)])
    expect(removeBar(bars, 1)).toEqual([work(540, 1020), ot(1020, 1140)])
  })

  it("splits a night shift over two pattern rows", () => {
    const bars = [work(1080, 1800), brk(1500, 1530), ot(1800, 1920)]
    expect(clipToDay(bars)).toEqual([work(1080, 1440)])
    expect(spill(bars)).toEqual([work(0, 360), brk(60, 90), ot(360, 480)])
  })

  it("finds an identical shift and names a new one", () => {
    const shifts = [
      { id: 1, name: "Office", shift_type: "fixed", start_time: "09:00:00", end_time: "17:00", segments: [] },
      {
        id: 2,
        name: "۰۹:۰۰–۱۷:۰۰",
        shift_type: "fixed",
        start_time: "09:00",
        end_time: "17:00",
        segments: [
          { kind: "overtime" as const, start_minute: 1020, end_minute: 1140 },
          { kind: "break" as const, start_minute: 750, end_minute: 795 },
        ],
      },
      { id: 3, name: "Flex", shift_type: "flexible", start_time: "09:00", end_time: "17:00", segments: [] },
    ]
    const drawn = {
      shift_type: "fixed",
      ...shiftFromBars([work(540, 1020), brk(750, 795), ot(1020, 1140)]),
    }
    expect(findIdentical(shifts, drawn)?.id).toBe(2) // segment order does not matter
    expect(findIdentical(shifts, { ...drawn, segments: [] })?.id).toBe(1)
    expect(findIdentical(shifts, { ...drawn, segments: [] }, 3)?.id).toBe(1) // the type must match
    expect(findIdentical(shifts, { ...drawn, shift_type: "flexible", segments: [] })?.id).toBe(3)
    expect(findIdentical(shifts, { ...drawn, end_time: "17:30" })).toBeUndefined()
    expect(shapeKey(shifts[0])).toBe("fixed|09:00|17:00|")
    expect(autoName(drawn, ["Office"])).toBe("۰۹:۰۰–۱۷:۰۰")
    expect(autoName(drawn, shifts.map((s) => s.name))).toBe("۰۹:۰۰–۱۷:۰۰ (۲)")
    expect(autoName({ start_time: "18:00", end_time: "06:00" }, [])).toBe("۱۸:۰۰–۰۶:۰۰")
  })
})
