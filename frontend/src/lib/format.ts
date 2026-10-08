import { __ } from "./i18n"
import { fa } from "./jalali"
import type { DayDetails, Punch, RequestView } from "./types"

/** 135 -> "۲:۱۵" (hours:minutes); 0 -> "—" unless zero is asked for. */
export function duration(minutes: number | null | undefined, showZero = false): string {
  const m = Math.round(minutes ?? 0)
  if (!m && !showZero) return "—"
  const sign = m < 0 ? "-" : ""
  const abs = Math.abs(m)
  return fa(`${sign}${Math.floor(abs / 60)}:${String(abs % 60).padStart(2, "0")}`)
}

/** "08:05:00" -> "۰۸:۰۵" */
export function clock(time: string | null | undefined): string {
  return time ? fa(time.slice(0, 5)) : "—"
}

/** "1405/07/14" or "1405/07/14 – 1405/07/16" in Persian digits. */
export function dateRange(from: string | null | undefined, to: string | null | undefined): string {
  if (!from) return ""
  return !to || to === from ? fa(from) : fa(__("{0} to {1}", [from, to]))
}

export type Tone = "gray" | "blue" | "green" | "amber" | "red" | "violet"

// day statuses, request / approval-step statuses and device sync statuses (API codes)
const STATUS_TONE: Record<string, Tone> = {
  present: "green",
  incomplete: "amber",
  absent: "red",
  leave: "violet",
  mission: "blue",
  holiday: "red",
  rest_day: "gray",
  not_scheduled: "gray",
  pending: "amber",
  approved: "green",
  rejected: "red",
  cancelled: "gray",
  skipped: "gray",
  ok: "green",
  error: "red",
}

export function tone(status: string | null | undefined): Tone {
  return (status && STATUS_TONE[status]) || "gray"
}

function lookup(labels: Record<string, string>, code: string | null | undefined): string {
  return code ? labels[code] ?? code : ""
}

export function statusLabel(status: string | null | undefined): string {
  return lookup(
    {
      present: __("Present"),
      incomplete: __("Incomplete"),
      absent: __("Absent"),
      leave: __("Leave"),
      mission: __("Mission"),
      holiday: __("Holiday"),
      rest_day: __("Rest Day"),
      not_scheduled: __("Not Scheduled"),
      pending: __("Pending"),
      approved: __("Approved"),
      rejected: __("Rejected"),
      cancelled: __("Cancelled"),
      skipped: __("Skipped"),
      ok: __("OK"),
      error: __("Error"),
    },
    status
  )
}

export function sourceLabel(source: string | null | undefined): string {
  return lookup({ device: __("Device"), file_import: __("File Import"), manual: __("Manual") }, source)
}

export function directionLabel(direction: string | null | undefined): string {
  return lookup({ in: __("In"), out: __("Out"), unknown: __("Unknown") }, direction || "unknown")
}

export function directionModeLabel(mode: string | null | undefined): string {
  return lookup(
    {
      from_device: __("From Device"),
      always_in: __("Always In"),
      always_out: __("Always Out"),
      pair_by_order: __("Pair by order"),
    },
    mode
  )
}

export function requestKindLabel(kind: string | null | undefined): string {
  return lookup(
    { leave: __("Leave"), mission: __("Mission"), overtime: __("Overtime"), correction: __("Manual entry") },
    kind
  )
}

export function requestTypeLabel(type: string | null | undefined): string {
  return lookup(
    {
      daily_leave: __("Daily Leave"),
      hourly_leave: __("Hourly Leave"),
      mission: __("Mission"),
      overtime: __("Overtime"),
      attendance_correction: __("Manual entry"),
    },
    type
  )
}

export function unitLabel(unit: string | null | undefined): string {
  return lookup({ daily: __("Daily"), hourly: __("Hourly") }, unit)
}

export function overtimeKindLabel(kind: string | null | undefined): string {
  return lookup({ normal: __("Normal"), exceptional: __("Exceptional"), emergency: __("Emergency") }, kind)
}

/** One line about a request: what, when, how long. Leave type names come from GET /leave-types. */
export function requestSummary(r: RequestView, leaveTypes: Record<number, string> = {}): string {
  const parts: string[] = []
  const times = (from: string | null, to: string | null) => (from && to ? `${clock(from)}–${clock(to)}` : "")
  if (r.leave) {
    parts.push(leaveTypes[r.leave.leave_type_id] || requestTypeLabel(r.request_type))
    parts.push(dateRange(r.start_jdate, r.end_jdate))
    if (r.leave.unit === "hourly") parts.push(times(r.leave.from_time, r.leave.to_time))
    else parts.push(fa(__("{0} days", [Number(r.leave.total_days.toFixed(2))])))
  } else if (r.mission) {
    if (r.mission.destination) parts.push(r.mission.destination)
    parts.push(dateRange(r.start_jdate, r.end_jdate))
    if (r.mission.unit === "hourly") parts.push(times(r.mission.from_time, r.mission.to_time))
  } else if (r.overtime) {
    parts.push(fa(r.start_jdate))
    parts.push(times(r.overtime.from_time, r.overtime.to_time))
    parts.push(duration(r.overtime.minutes))
    if (r.overtime.overtime_kind !== "normal") parts.push(overtimeKindLabel(r.overtime.overtime_kind))
  } else {
    parts.push(fa(r.start_jdate))
    for (const item of r.items ?? []) {
      parts.push(
        item.action === "ignore_punch"
          ? __("Ignore a punch")
          : `${clock(item.time)} ${directionLabel(item.direction)}`
      )
    }
  }
  return parts.filter(Boolean).join(" · ")
}

/** The punches of one day in time order: device / file punches and approved manual ones. */
export function dayPunches(day: DayDetails | null | undefined): Punch[] {
  if (!day) return []
  const manual = day.manual_punches.map((p) => ({ ...p, source: "manual" }))
  return [...day.punches, ...manual].sort((a, b) => a.time.localeCompare(b.time))
}

/** The punches that count (not duplicates, not set aside by a manual entry). */
export function countedPunches(day: DayDetails | null | undefined): Punch[] {
  return dayPunches(day).filter((p) => !p.is_duplicate && !p.ignored)
}
