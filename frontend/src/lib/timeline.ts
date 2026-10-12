/**
 * The pure logic behind the graphical shift and work-pattern editors (components/ShiftTimeline.vue,
 * components/PatternGrid.vue): minutes <-> positions, snapping, drawing / moving / resizing bars,
 * the server's rules for breaks and overtime windows, and finding an identical shift.
 *
 * Minutes count from the shift day's 00:00 and run into the next day (0..2880), exactly like
 * shift_segment on the server (backend/chronicle/db/models/schedules.py): 01:00 the next morning is
 * 1500. The working hours of a shift are one "work" bar from its start to its end; an end earlier
 * than the start means the shift ends the next day.
 */
import { __ } from "./i18n"
import { ascii, fa } from "./jalali"

export const DAY = 1440
export const TWO_DAYS = 2880

export type SegmentKind = "break" | "overtime"
export type BarKind = "work" | SegmentKind

export interface Segment {
  kind: SegmentKind
  start_minute: number
  end_minute: number
}

export interface Bar {
  kind: BarKind
  start: number
  end: number
}

/** The drawn part of a shift: what makes two shifts identical in the editors. */
export interface ShiftShape {
  shift_type?: string | null
  start_time: string | null
  end_time: string | null
  segments?: Segment[] | null
}

/** Colours of the bars (the work bar takes the shift's own colour when it has one). */
export const BAR_COLORS: Record<BarKind, string> = {
  work: "#0d9488",
  break: "#f59e0b",
  overtime: "#6366f1",
}

// clock times --------------------------------------------------------------------------------------

/** "09:30" (or "09:30:00", Persian digits allowed) -> 570; null when it is not a time. */
export function parseClock(value: string | null | undefined): number | null {
  if (!value) return null
  const m = /^(\d{1,2}):(\d{2})/.exec(ascii(String(value)).trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

/** 1500 -> "01:00": the wall-clock time of a minute of the shift day (ASCII, as stored). */
export function clock(minute: number): string {
  const m = ((Math.round(minute) % DAY) + DAY) % DAY
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
}

/** The span of a shift in minutes: an end at or before the start is the next day. */
export function spanOf(startTime: string | null | undefined, endTime: string | null | undefined): Bar | null {
  const start = parseClock(startTime)
  let end = parseClock(endTime)
  if (start === null || end === null) return null
  if (end <= start) end += DAY
  return { kind: "work", start, end }
}

/**
 * A clock time typed for a break or overtime window -> minutes of the shift day: today or
 * tomorrow, whichever is nearer to the shift (a 01:00 break of an 18:00-06:00 shift is 1500).
 * Same rule as the server's Excel import.
 */
export function clockToShiftMinute(value: string, span: Bar | null): number | null {
  const t = parseClock(value)
  if (t === null) return null
  if (!span) return t
  const distance = (x: number) => (span.start <= x && x <= span.end ? 0 : Math.min(Math.abs(x - span.start), Math.abs(x - span.end)))
  return distance(t + DAY) < distance(t) ? t + DAY : t
}

/** The end of a part that starts at `start` and ends at the clock time `value` (maybe the next day). */
export function clockAfter(value: string, start: number): number | null {
  const t = parseClock(value)
  if (t === null) return null
  const diff = (((t - start) % DAY) + DAY) % DAY
  return start + (diff === 0 ? DAY : diff)
}

// positions ----------------------------------------------------------------------------------------

export function snap(minute: number, step: number): number {
  return step > 0 ? Math.round(minute / step) * step : Math.round(minute)
}

const clamp = (value: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, value))

/** Where a minute sits on a timeline from `from` to `to`, as a fraction of its length (0..1). */
export function minuteToFraction(minute: number, from: number, to: number): number {
  return (minute - from) / (to - from)
}

/**
 * The minute under the pointer. `offset` is measured from the edge where the timeline starts;
 * time runs right-to-left in the PWA, so that is the right edge (rect.right - clientX).
 */
export function positionToMinute(offset: number, width: number, from: number, to: number): number {
  if (width <= 0) return from
  return clamp(from + (offset / width) * (to - from), from, to)
}

/** The end of the timeline: the day, or into the next morning when a bar reaches midnight. */
export function timelineEnd(bars: Bar[], extend = false): number {
  const last = Math.max(0, ...bars.map((b) => b.end))
  if (!extend && last < DAY) return DAY
  return Math.min(TWO_DAYS, Math.max(DAY + 360, Math.ceil(last / 60) * 60 + 180))
}

/** Hour ticks of a timeline; `every` hours get a label. */
export function hourTicks(from: number, to: number, every = 1): { minute: number; label: string | null }[] {
  const ticks = []
  for (let m = Math.ceil(from / 60) * 60; m <= to; m += 60) {
    const hour = (m / 60) % 24
    ticks.push({ minute: m, label: (m / 60) % every === 0 ? String(hour).padStart(2, "0") : null })
  }
  return ticks
}

// shift <-> bars -----------------------------------------------------------------------------------

/** The bars of a shift: its working hours first, then its breaks and overtime windows. */
export function barsFromShift(shape: ShiftShape | null | undefined): Bar[] {
  if (!shape) return []
  const bars: Bar[] = []
  const span = spanOf(shape.start_time, shape.end_time)
  if (span) bars.push(span)
  for (const s of shape.segments ?? []) bars.push({ kind: s.kind, start: s.start_minute, end: s.end_minute })
  return bars
}

/** The shift fields of drawn bars (bar order is kept, so a selected bar stays selected). */
export function shiftFromBars(bars: Bar[]): { start_time: string | null; end_time: string | null; segments: Segment[] } {
  const work = bars.find((b) => b.kind === "work")
  return {
    start_time: work ? clock(work.start) : null,
    end_time: work ? clock(work.end) : null,
    segments: bars
      .filter((b) => b.kind !== "work")
      .map((b) => ({ kind: b.kind as SegmentKind, start_minute: b.start, end_minute: b.end })),
  }
}

/** Segments as the server takes them (no ids), in order. */
export function cleanSegments(segments: Segment[] | null | undefined): Segment[] {
  return [...(segments ?? [])]
    .map((s) => ({ kind: s.kind, start_minute: s.start_minute, end_minute: s.end_minute }))
    .sort((a, b) => a.start_minute - b.start_minute || a.kind.localeCompare(b.kind))
}

const length = (b: Bar) => Math.max(0, b.end - b.start)
const overlaps = (a: Bar, b: Bar) => a.start < b.end && b.start < a.end
const inside = (b: Bar, span: Bar) => span.start <= b.start && b.end <= span.end

// totals -------------------------------------------------------------------------------------------

/** Scheduled work: the span minus the breaks inside it (breaks are never working time, Article 51). */
export function workMinutes(bars: Bar[]): number {
  const work = bars.find((b) => b.kind === "work")
  if (!work) return 0
  const breaks = bars.filter((b) => b.kind === "break").reduce((sum, b) => {
    const overlap = Math.min(b.end, work.end) - Math.max(b.start, work.start)
    return sum + Math.max(0, overlap)
  }, 0)
  return Math.max(0, length(work) - breaks)
}

export function kindMinutes(bars: Bar[], kind: BarKind): number {
  return bars.filter((b) => b.kind === kind).reduce((sum, b) => sum + length(b), 0)
}

// validation ---------------------------------------------------------------------------------------

/** The server's rules for a drawn shift (services/resources.py `_shift`), as messages. */
export function validateBars(bars: Bar[], shiftType: string | null | undefined = "fixed"): string[] {
  const problems = new Set<string>()
  const work = bars.find((b) => b.kind === "work")
  if (!work) problems.add(__("Draw the working hours"))
  else if (length(work) <= 0 || length(work) > DAY || work.start < 0 || work.start >= DAY)
    problems.add(__("A shift is at most 24 hours and starts on its own day"))
  for (const b of bars) {
    if (b.kind !== "work" && !(0 <= b.start && b.start < b.end && b.end <= TWO_DAYS))
      problems.add(__("A part of the shift must end after it starts"))
  }
  for (const [kind, message] of [
    ["break", __("Breaks overlap each other")],
    ["overtime", __("Overtime windows overlap each other")],
  ] as const) {
    const same = bars.filter((b) => b.kind === kind).sort((a, b) => a.start - b.start)
    for (let i = 1; i < same.length; i++) if (same[i].start < same[i - 1].end) problems.add(message)
  }
  if (work) {
    if (bars.some((b) => b.kind === "break" && !inside(b, work))) problems.add(__("The break must be inside the shift"))
    if (shiftType !== "flexible" && bars.some((b) => b.kind === "overtime" && overlaps(b, work)))
      problems.add(__("An overtime window must be before the start or after the end of the shift"))
  }
  return [...problems]
}

// editing ------------------------------------------------------------------------------------------

export type Hit = { index: number; part: "body" | "start" | "end" }

const LAYER: Record<BarKind, number> = { break: 0, overtime: 1, work: 2 }

/**
 * What the pointer is on: an edge of a bar (to resize it) or its body (to move it). Breaks lie on
 * top of the working hours, so they win; at a shared edge (the end of work = the start of an
 * overtime window) the bar the pointer is inside wins. `tolerance` is in minutes.
 */
export function hitTest(bars: Bar[], minute: number, tolerance: number): Hit | null {
  let best: Hit | null = null
  let bestScore = Infinity
  bars.forEach((b, index) => {
    const tol = Math.min(tolerance, length(b) / 4)
    const within = b.start <= minute && minute <= b.end
    for (const part of ["start", "end"] as const) {
      const d = Math.abs(minute - b[part])
      if (d > tol) continue
      const score = (within ? 0 : 10_000) + d * 10 + LAYER[b.kind]
      if (score < bestScore) {
        bestScore = score
        best = { index, part }
      }
    }
  })
  if (best) return best
  const order = bars.map((_, i) => i).sort((a, b) => LAYER[bars[a].kind] - LAYER[bars[b].kind])
  const index = order.find((i) => bars[i].start <= minute && minute <= bars[i].end)
  return index === undefined ? null : { index, part: "body" }
}

/** Puts the working hours at [start, end], dropping breaks that no longer fit and (fixed) overtime windows on top of it. */
export function setWork(bars: Bar[], start: number, end: number, shiftType: string | null | undefined = "fixed"): Bar[] {
  const work: Bar = { kind: "work", start, end }
  const rest = bars.filter((b) => {
    if (b.kind === "work") return false
    if (b.kind === "break") return inside(b, work)
    return shiftType === "flexible" || !overlaps(b, work)
  })
  return [work, ...rest]
}

/** Removes a bar; without working hours the breaks go too. */
export function removeBar(bars: Bar[], index: number): Bar[] {
  const removed = bars[index]
  if (!removed) return bars
  return bars.filter((b, i) => i !== index && !(removed.kind === "work" && b.kind === "break"))
}

export type Drag =
  | { type: "draw"; kind: BarKind; anchor: number; original: Bar[] }
  | { type: "move"; index: number; grab: number; original: Bar[] }
  | { type: "resize"; index: number; edge: "start" | "end"; original: Bar[] }

export interface DragOptions {
  step: number
  from: number // the visible timeline
  to: number
  shiftType?: string | null
}

/** The bars while the pointer is at `minute` during a drag (always computed from the bars at its start). */
export function dragTo(drag: Drag, minute: number, o: DragOptions): Bar[] {
  const bars = drag.original
  if (drag.type === "draw") {
    let lo = clamp(snap(Math.min(drag.anchor, minute), o.step), o.from, o.to)
    let hi = clamp(snap(Math.max(drag.anchor, minute), o.step), o.from, o.to)
    if (drag.kind === "work") {
      lo = Math.min(lo, DAY - o.step)
      hi = Math.min(hi, lo + DAY)
    }
    if (hi <= lo) return bars
    return drag.kind === "work" ? setWork(bars, lo, hi, o.shiftType) : [...bars, { kind: drag.kind, start: lo, end: hi }]
  }
  const bar = bars[drag.index]
  if (!bar) return bars
  // a bar already wider than the view (a night shift on a pattern row) may keep its size
  const from = Math.min(o.from, bar.start)
  const to = Math.max(o.to, bar.end)
  const step = Math.max(1, o.step)
  if (drag.type === "move") {
    let start = snap(bar.start + (minute - drag.grab), step)
    start = clamp(start, from, to - length(bar))
    if (bar.kind === "work") start = Math.min(start, DAY - step)
    const delta = start - bar.start
    if (!delta) return bars
    return bars.map((b, i) => {
      // the breaks move with the working hours they belong to
      if (i === drag.index || (bar.kind === "work" && b.kind === "break" && inside(b, bar)))
        return { ...b, start: b.start + delta, end: b.end + delta }
      return b
    })
  }
  let { start, end } = bar
  if (drag.edge === "start") {
    start = clamp(snap(minute, step), from, end - step)
    if (bar.kind === "work") start = Math.max(Math.min(start, DAY - step), end - DAY)
  } else {
    end = clamp(snap(minute, step), start + step, to)
    if (bar.kind === "work") end = Math.min(end, start + DAY)
  }
  return bars.map((b, i) => (i === drag.index ? { ...b, start, end } : b))
}

/**
 * What pressing the pointer at `minute` starts: resizing or moving the bar under it, or drawing
 * with the tool on empty space. Breaks are drawn on top of the working hours (and, in a flexible
 * shift, overtime windows too), so with those tools the body of the work bar counts as empty.
 */
export function pressAction(
  bars: Bar[],
  minute: number,
  tolerance: number,
  tool: BarKind | null,
  shiftType: string | null | undefined = "fixed"
): Drag | null {
  const hit = hitTest(bars, minute, tolerance)
  const drawsOverWork = tool === "break" || (tool === "overtime" && shiftType === "flexible")
  if (hit && !(hit.part === "body" && bars[hit.index].kind === "work" && drawsOverWork)) {
    return hit.part === "body"
      ? { type: "move", index: hit.index, grab: minute, original: bars }
      : { type: "resize", index: hit.index, edge: hit.part, original: bars }
  }
  return tool ? { type: "draw", kind: tool, anchor: minute, original: bars } : null
}

/** Moves a bar by whole steps (the arrow keys). */
export function nudge(bars: Bar[], index: number, delta: number, o: DragOptions): Bar[] {
  const bar = bars[index]
  if (!bar) return bars
  return dragTo({ type: "move", index, grab: bar.start, original: bars }, bar.start + delta, o)
}

// pattern rows -------------------------------------------------------------------------------------

/** The part of a day's bars that lies on the day itself (0..24). */
export function clipToDay(bars: Bar[]): Bar[] {
  return bars.filter((b) => b.start < DAY).map((b) => ({ ...b, end: Math.min(b.end, DAY) }))
}

/** The part of a day's bars after midnight, moved onto the next day (a night shift's morning). */
export function spill(bars: Bar[]): Bar[] {
  return bars.filter((b) => b.end > DAY).map((b) => ({ ...b, start: Math.max(b.start, DAY) - DAY, end: b.end - DAY }))
}

/** A key that is equal for two shifts drawn the same way (type, start, end, breaks, windows). */
export function shapeKey(shape: ShiftShape): string {
  const start = parseClock(shape.start_time)
  const end = parseClock(shape.end_time)
  const segments = cleanSegments(shape.segments)
    .map((s) => `${s.kind}:${s.start_minute}-${s.end_minute}`)
    .join(",")
  return `${shape.shift_type || "fixed"}|${start === null ? "" : clock(start)}|${end === null ? "" : clock(end)}|${segments}`
}

/** An existing shift drawn exactly like `shape` (the preferred one first, e.g. the row's shift). */
export function findIdentical<T extends ShiftShape & { id: number }>(
  shifts: T[],
  shape: ShiftShape,
  prefer?: number | null
): T | undefined {
  const key = shapeKey(shape)
  const same = shifts.filter((s) => shapeKey(s) === key)
  return same.find((s) => s.id === prefer) ?? same[0]
}

/** The automatic name of a drawn shift: "۰۹:۰۰–۱۷:۰۰", with a number when the name is taken. */
export function autoName(shape: ShiftShape, taken: string[]): string {
  const start = clock(parseClock(shape.start_time) ?? 0)
  const end = clock(parseClock(shape.end_time) ?? 0)
  const base = fa(`${start}–${end}`)
  const names = new Set(taken)
  let name = base
  for (let n = 2; names.has(name); n++) name = `${base} (${fa(n)})`
  return name
}
