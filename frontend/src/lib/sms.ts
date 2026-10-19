import { __ } from "./i18n"
import type { SmsStatus } from "./types"

export function smsStatusLabel(status: SmsStatus | null): string {
  switch (status) {
    case "queued":
      return __("Queued")
    case "sending":
      return __("Sending")
    case "sent":
      return __("Sent")
    case "delivered":
      return __("Delivered")
    case "failed":
      return __("Failed")
    case "skipped":
      return __("Skipped")
    case "unknown":
      return __("Unknown: check the panel")
    default:
      return ""
  }
}

/** The tailwind text colour of a status. */
export function smsStatusClass(status: SmsStatus | null): string {
  switch (status) {
    case "sent":
    case "delivered":
      return "text-ink-green-3"
    case "failed":
      return "text-ink-red-3"
    case "unknown":
      return "text-ink-amber-7"
    default:
      return "text-ink-gray-5"
  }
}
