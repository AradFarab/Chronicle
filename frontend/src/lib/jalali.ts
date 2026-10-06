// Jalali helpers for the UI. Dates travel as "1405/07/14" (ASCII), exactly as stored on the
// server; Persian digits are only for display.
import { isValidJalaaliDate, jalaaliMonthLength, toGregorian, toJalaali } from "jalaali-js"

export const MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
]
export const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
export const WEEKDAYS_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"]

const PERSIAN = "۰۱۲۳۴۵۶۷۸۹"

export function fa(value: unknown): string {
  return String(value ?? "").replace(/[0-9]/g, (d) => PERSIAN[Number(d)])
}

export function ascii(value: string): string {
  return value
    .replace(/[۰-۹]/g, (d) => String(PERSIAN.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
}

export interface JDate {
  jy: number
  jm: number
  jd: number
}

export function format(d: JDate): string {
  return `${d.jy}/${String(d.jm).padStart(2, "0")}/${String(d.jd).padStart(2, "0")}`
}

export function parse(value: string): JDate | null {
  const m = /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(ascii(value.trim()))
  if (!m) return null
  const d = { jy: +m[1], jm: +m[2], jd: +m[3] }
  return isValidJalaaliDate(d.jy, d.jm, d.jd) ? d : null
}

export function today(): JDate {
  return toJalaali(new Date())
}

export function monthLength(jy: number, jm: number): number {
  return jalaaliMonthLength(jy, jm)
}

/** 0 = Saturday ... 6 = Friday */
export function weekday(d: JDate): number {
  const g = toGregorian(d.jy, d.jm, d.jd)
  return (new Date(g.gy, g.gm - 1, g.gd).getDay() + 1) % 7
}

export function addMonths(jy: number, jm: number, delta: number): { jy: number; jm: number } {
  const index = jy * 12 + (jm - 1) + delta
  return { jy: Math.floor(index / 12), jm: (index % 12) + 1 }
}

export function display(value: string | null | undefined): string {
  return value ? fa(value) : ""
}

export function displayLong(value: string): string {
  const d = parse(value)
  if (!d) return fa(value)
  return `${WEEKDAYS[weekday(d)]} ${fa(d.jd)} ${MONTHS[d.jm - 1]} ${fa(d.jy)}`
}

/** 470 -> "۷:۵۰" */
export function hm(minutes: number | null | undefined): string {
  const m = Math.max(0, Math.round(minutes || 0))
  return fa(`${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`)
}
