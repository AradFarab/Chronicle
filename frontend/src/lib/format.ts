import { __ } from "./i18n"
import { fa } from "./jalali"

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

export type Tone = "gray" | "blue" | "green" | "amber" | "red" | "violet"

const STATUS_TONE: Record<string, Tone> = {
  Present: "green",
  Incomplete: "amber",
  Absent: "red",
  Leave: "violet",
  Mission: "blue",
  Holiday: "red",
  "Rest Day": "gray",
  "Not Employed": "gray",
  Draft: "gray",
  Pending: "amber",
  Approved: "green",
  Rejected: "red",
  Cancelled: "gray",
  OK: "green",
  Error: "red",
}

export function tone(status: string | null | undefined): Tone {
  return (status && STATUS_TONE[status]) || "gray"
}

export function statusLabel(status: string | null | undefined): string {
  return status ? __(status) : ""
}

export function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    Device: __("Device"),
    "File Import": __("File Import"),
    Manual: __("Manual"),
  }
  return labels[source] ?? source
}
