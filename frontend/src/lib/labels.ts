/** Persian labels for the codes the admin pages show (the API always sends codes). */
import { __ } from "./i18n"
import type { Option } from "./resources"

export const holidayTypeOptions = (): Option[] => [
  { value: "official_solar", label: __("Official (solar)") },
  { value: "official_lunar", label: __("Official (lunar)") },
  { value: "official_occasional", label: __("Official (announced)") },
  { value: "office_closure", label: __("Office closure") },
  { value: "company_internal", label: __("Company holiday") },
]

export const holidayScopeOptions = (): Option[] => [
  { value: "country", label: __("Whole country") },
  { value: "province", label: __("One province") },
  { value: "branch", label: __("One branch") },
  { value: "company", label: __("Whole company") },
]

export const closurePayOptions = (): Option[] => [
  { value: "paid_holiday", label: __("Paid holiday") },
  { value: "employer_paid", label: __("Paid by the employer, counted as work") },
  { value: "workday", label: __("Normal workday (make up later)") },
]

export const holidayStatusOptions = (): Option[] => [
  { value: "confirmed", label: __("Confirmed") },
  { value: "predicted", label: __("Predicted") },
]

export const calendarSourceOptions = (): Option[] => [
  { value: "time_ir", label: __("time.ir (official calendar)") },
  { value: "bundled", label: __("Holidays shipped with the app") },
  { value: "file", label: __("A holiday file (JSON or CSV)") },
]

export function label(options: () => Option[], value: unknown): string {
  return options().find((o) => o.value === value)?.label ?? String(value ?? "")
}
