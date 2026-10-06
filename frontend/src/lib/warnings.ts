import { __ } from "./i18n"

/** Daily Attendance.warnings holds comma-separated codes from the engine (same list as the desk form). */
export function warningMessages(codes: string | null | undefined): string[] {
  const messages: Record<string, string> = {
    MISSING_PUNCH: __("A punch has no pair: correct the day"),
    ARTICLE_54_SPAN_EXCEEDED: __("More than 15 hours from first to last punch (Article 54)"),
    ARTICLE_51_SCHEDULE_OVER_DAILY_LIMIT: __("The shift is longer than the daily limit (Article 51)"),
    ARTICLE_52_SCHEDULE_OVER_HARD_HARMFUL_LIMIT: __(
      "The shift is longer than 6 hours for hard and harmful work (Article 52)"
    ),
    ARTICLE_59_OVERTIME_CAP: __("Overtime above the daily cap was not counted (Article 59)"),
    ARTICLE_60_EMERGENCY_CAP: __("Emergency overtime above 8 hours was not counted (Article 60)"),
    ARTICLE_61_NO_OVERTIME_HARD_HARMFUL: __("No overtime in hard and harmful work (Article 61)"),
    ARTICLE_84_NO_OVERTIME_JUVENILE: __("No overtime for young workers (Article 84)"),
    ARTICLE_84_NO_NIGHT_WORK_JUVENILE: __("No night work for young workers (Article 84)"),
    UNAPPROVED_EXTRA_WORK: __("Extra work without an approved overtime request"),
  }
  return (codes || "")
    .split(/[,\n]/)
    .map((c) => c.trim())
    .filter(Boolean)
    .map((c) => messages[c] || c)
}
