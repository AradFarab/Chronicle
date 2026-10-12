/**
 * The configuration tables edited in the PWA, described once: the generic list and form
 * (pages/ResourceList.vue, components/ResourceForm.vue) render them. The server
 * (backend/chronicle/services/resources.py) validates everything again.
 */
import { __ } from "./i18n"
import { WEEKDAYS } from "./jalali"

export interface Option {
  value: string | number
  label: string
}

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "bool"
  | "jdate"
  | "time"
  | "select"
  | "ref"
  | "children"
  | "params"
  | "color"
  | "badge" // a read-only flag shown as a badge (never sent back)
  | "editor" // a custom editor (`editor`) that edits the record keys listed in `keys`

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  options?: () => Option[]
  ref?: string // admin resource the value points to (its rows become the options)
  required?: boolean
  list?: boolean // shown as a column in the list
  help?: string
  children?: FieldDef[]
  show?: (values: Record<string, unknown>) => boolean
  dir?: "ltr"
  // type "editor": which component edits the record (see EDITORS in components/ResourceForm.vue)
  // and the keys of the record it owns, which are sent with the form
  editor?: "shift-timeline" | "pattern-grid"
  keys?: string[]
}

export interface ResourceDef {
  name: string // URL segment under /api/admin
  title: string
  singular: string
  icon: string
  fields: FieldDef[]
  reasonOnChange?: boolean
  canDelete?: boolean
  defaults?: Record<string, unknown>
  size?: "2xl" | "3xl" | "4xl" | "5xl" // the form dialog (default 2xl)
  columns?: 2 | 3 // short fields side by side on wider screens
}

/** The text shown for a row of a resource (in lists of options and references). */
export function rowLabel(row: Record<string, unknown>): string {
  if (row.full_name) return `${row.full_name}${row.code ? ` (${row.code})` : ""}`
  return String(row.name ?? row.title ?? row.id)
}

const opts = (pairs: [string | number, string][]) => () => pairs.map(([value, label]) => ({ value, label }))

export const weekdayOptions = () => WEEKDAYS.map((label, value) => ({ value, label }))

export const requestTypeOptions = opts([
  ["daily_leave", __("Daily leave")],
  ["hourly_leave", __("Hourly leave")],
  ["mission", __("Mission")],
  ["overtime", __("Overtime")],
  ["attendance_correction", __("Manual time entry")],
])

export const RESOURCES: ResourceDef[] = [
  {
    name: "work-locations",
    title: __("Work locations"),
    singular: __("Work location"),
    icon: "lucide-building-2",
    canDelete: true,
    defaults: { is_active: true },
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      { key: "province_id", label: __("Province"), type: "ref", ref: "provinces", required: true, list: true },
      { key: "city", label: __("City"), type: "text", list: true },
      { key: "address", label: __("Address"), type: "textarea" },
      { key: "is_active", label: __("Active"), type: "bool", list: true },
    ],
  },
  {
    name: "departments",
    title: __("Departments"),
    singular: __("Department"),
    icon: "lucide-network",
    canDelete: true,
    fields: [{ key: "name", label: __("Name"), type: "text", required: true, list: true }],
  },
  {
    name: "designations",
    title: __("Designations"),
    singular: __("Designation"),
    icon: "lucide-briefcase",
    canDelete: true,
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      { key: "is_ceo", label: __("CEO"), type: "badge", list: true },
      {
        key: "parent_id",
        label: __("Designation above"),
        type: "ref",
        ref: "designations",
        list: true,
        help: __("Whoever holds the designation above approves the requests of the people below"),
        show: (v) => !v.is_ceo,
      },
      {
        key: "hard_and_harmful",
        label: __("Hard and harmful work"),
        type: "bool",
        list: true,
        help: __("Articles 52 and 61: shorter hours, no overtime"),
      },
      { key: "committee_ruling_no", label: __("Committee ruling number"), type: "text" },
      { key: "committee_ruling_date", label: __("Committee ruling date"), type: "jdate" },
      { key: "description", label: __("Description"), type: "textarea" },
    ],
  },
  {
    name: "designation-assignments",
    title: __("Designations held"),
    singular: __("Designation held"),
    icon: "lucide-user-check",
    canDelete: true,
    fields: [
      { key: "employee_id", label: __("Employee"), type: "ref", ref: "employees", required: true, list: true },
      { key: "designation_id", label: __("Designation"), type: "ref", ref: "designations", required: true, list: true },
      { key: "valid_from", label: __("From"), type: "jdate", required: true, list: true },
      { key: "valid_to", label: __("Until"), type: "jdate", list: true },
      { key: "note", label: __("Note"), type: "textarea" },
    ],
  },
  {
    name: "shifts",
    title: __("Shifts"),
    singular: __("Shift"),
    icon: "lucide-clock",
    canDelete: true,
    size: "5xl",
    columns: 3,
    defaults: {
      shift_type: "fixed",
      segments: [],
      break_minutes: 0,
      grace_late_minutes: 0,
      grace_early_minutes: 0,
      overtime_after_minutes: 0,
    },
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      {
        key: "shift_type",
        label: __("Type"),
        type: "select",
        required: true,
        list: true,
        options: opts([
          ["fixed", __("Fixed")],
          ["flexible", __("Flexible")],
        ]),
      },
      { key: "color", label: __("Colour"), type: "color" },
      {
        key: "drawing",
        label: __("Working hours, breaks and overtime windows"),
        type: "editor",
        editor: "shift-timeline",
        keys: ["start_time", "end_time", "segments"],
      },
      // drawn on the timeline above; listed as columns
      { key: "start_time", label: __("Start"), type: "time", list: true, show: () => false },
      { key: "end_time", label: __("End"), type: "time", list: true, show: () => false },
      {
        key: "latest_start_time",
        label: __("Latest start"),
        type: "time",
        show: (v) => v.shift_type === "flexible",
      },
      {
        key: "required_minutes",
        label: __("Required minutes"),
        type: "number",
        required: true,
        show: (v) => v.shift_type === "flexible",
      },
      {
        key: "break_minutes",
        label: __("Break minutes without punching"),
        type: "number",
        help: __("Deducted when no break is drawn"),
        show: (v) => v.shift_type === "flexible",
      },
      {
        key: "grace_late_minutes",
        label: __("Grace for late arrival (minutes)"),
        type: "number",
        help: __("Up to this late is forgiven; beyond it the whole time counts"),
      },
      {
        key: "grace_early_minutes",
        label: __("Grace for early leave (minutes)"),
        type: "number",
        help: __("Up to this early is forgiven; beyond it the whole time counts"),
      },
      {
        key: "overtime_after_minutes",
        label: __("Extra work counts after (minutes)"),
        type: "number",
        help: __("Staying up to this long after the end is ignored; beyond it all of it is extra work"),
      },
    ],
  },
  {
    name: "work-patterns",
    title: __("Work patterns"),
    singular: __("Work pattern"),
    icon: "lucide-calendar-range",
    canDelete: true,
    size: "5xl",
    columns: 2,
    defaults: { pattern_type: "weekly", weekly_rest_day: 6, days: [] },
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      {
        key: "pattern_type",
        label: __("Type"),
        type: "select",
        required: true,
        list: true,
        options: opts([
          ["weekly", __("Weekly")],
          ["rotating", __("Rotating")],
        ]),
      },
      {
        key: "weekly_rest_day",
        label: __("Weekly rest day"),
        type: "select",
        options: weekdayOptions,
        show: (v) => v.pattern_type !== "rotating",
      },
      {
        key: "cycle_start_date",
        label: __("First day of the cycle"),
        type: "jdate",
        show: (v) => v.pattern_type === "rotating",
      },
      { key: "days", label: __("Days"), type: "editor", editor: "pattern-grid", keys: ["days"] },
      { key: "description", label: __("Description"), type: "textarea" },
      { key: "change_reason", label: __("Reason for the change"), type: "textarea" },
    ],
  },
  {
    name: "work-pattern-assignments",
    title: __("Pattern assignments"),
    singular: __("Pattern assignment"),
    icon: "lucide-calendar-check",
    canDelete: true,
    defaults: { target_type: "employee", cycle_offset_days: 0 },
    fields: [
      {
        key: "target_type",
        label: __("Applies to"),
        type: "select",
        required: true,
        list: true,
        options: opts([
          ["employee", __("One employee")],
          ["designation", __("A designation")],
          ["department", __("A department")],
          ["company", __("The whole company")],
        ]),
      },
      {
        key: "employee_id",
        label: __("Employee"),
        type: "ref",
        ref: "employees",
        list: true,
        show: (v) => v.target_type === "employee",
      },
      {
        key: "designation_id",
        label: __("Designation"),
        type: "ref",
        ref: "designations",
        list: true,
        show: (v) => v.target_type === "designation",
      },
      {
        key: "department_id",
        label: __("Department"),
        type: "ref",
        ref: "departments",
        list: true,
        show: (v) => v.target_type === "department",
      },
      { key: "work_pattern_id", label: __("Work pattern"), type: "ref", ref: "work-patterns", required: true, list: true },
      {
        key: "cycle_offset_days",
        label: __("Start the cycle later by (days)"),
        type: "number",
        help: __(
          "For a rotating pattern: moves this group along the cycle by this many days, so two groups can follow one pattern half a cycle apart"
        ),
      },
      { key: "valid_from", label: __("From"), type: "jdate", required: true, list: true },
      { key: "valid_to", label: __("Until"), type: "jdate", list: true },
      { key: "note", label: __("Note"), type: "textarea" },
    ],
  },
  {
    name: "shift-overrides",
    title: __("One-day shift changes"),
    singular: __("Shift change"),
    icon: "lucide-calendar-x",
    canDelete: true,
    fields: [
      { key: "employee_id", label: __("Employee"), type: "ref", ref: "employees", required: true, list: true },
      { key: "jdate", label: __("Date"), type: "jdate", required: true, list: true },
      { key: "shift_id", label: __("Shift (empty = day off)"), type: "ref", ref: "shifts", list: true },
      { key: "reason", label: __("Reason"), type: "textarea", required: true, list: true },
    ],
  },
  {
    name: "rule-sets",
    title: __("Labor rule sets"),
    singular: __("Labor rule set"),
    icon: "lucide-scale",
    reasonOnChange: true,
    canDelete: true,
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      { key: "effective_from", label: __("Effective from"), type: "jdate", required: true, list: true },
      { key: "is_legal_baseline", label: __("Legal baseline"), type: "bool", list: true, show: () => false },
      { key: "parameters", label: __("Parameters"), type: "params", required: true },
      { key: "description", label: __("Description"), type: "textarea" },
    ],
  },
  {
    name: "leave-types",
    title: __("Leave types"),
    singular: __("Leave type"),
    icon: "lucide-tree-palm",
    canDelete: true,
    defaults: { category: "other" },
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      {
        key: "category",
        label: __("Category"),
        type: "select",
        required: true,
        list: true,
        options: opts([
          ["earned", __("Earned")],
          ["sick", __("Sick")],
          ["unpaid", __("Unpaid")],
          ["marriage_bereavement", __("Marriage or bereavement")],
          ["hajj", __("Hajj")],
          ["maternity", __("Maternity")],
          ["paternity", __("Paternity")],
          ["other", __("Other")],
        ]),
      },
      { key: "is_paid", label: __("Paid"), type: "bool", list: true },
      { key: "deducts_from_balance", label: __("Deducted from the leave balance"), type: "bool", list: true },
      { key: "allow_hourly", label: __("Can be hourly"), type: "bool" },
      { key: "max_days_per_request", label: __("Most days in one request"), type: "number" },
      { key: "once_in_service", label: __("Once in the whole service"), type: "bool" },
      { key: "rule_limit", label: __("Limit from the rule set (parameter)"), type: "text", dir: "ltr" },
      { key: "description", label: __("Description"), type: "textarea" },
    ],
  },
  {
    name: "approval-processes",
    title: __("Approval processes"),
    singular: __("Approval process"),
    icon: "lucide-git-branch",
    canDelete: true,
    defaults: { steps: [] },
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      { key: "description", label: __("Description"), type: "textarea", list: true },
      {
        key: "steps",
        label: __("Steps"),
        type: "children",
        children: [
          { key: "position", label: __("Step"), type: "number" },
          {
            key: "approver_type",
            label: __("Approver"),
            type: "select",
            options: opts([
              ["parent", __("Parent in the chart")],
              ["ceo", __("CEO")],
              ["specific_person", __("A specific person")],
            ]),
          },
          { key: "approver_id", label: __("Person"), type: "ref", ref: "employees" },
        ],
      },
    ],
  },
  {
    name: "approval-overrides",
    title: __("Approval exceptions"),
    singular: __("Approval exception"),
    icon: "lucide-user-cog",
    canDelete: true,
    fields: [
      { key: "employee_id", label: __("Employee"), type: "ref", ref: "employees", required: true, list: true },
      {
        key: "request_type",
        label: __("Request type"),
        type: "select",
        required: true,
        list: true,
        options: requestTypeOptions,
      },
      { key: "process_id", label: __("Approval process"), type: "ref", ref: "approval-processes", required: true, list: true },
    ],
  },
]

export function resourceDef(name: string): ResourceDef | undefined {
  return RESOURCES.find((r) => r.name === name)
}

/** Labels of the labor-law parameters (backend/chronicle/engine/rules.py PARAMETERS). */
export const PARAMETER_LABELS: Record<string, string> = {
  max_daily_minutes: __("Most work per day (minutes)"),
  max_weekly_minutes: __("Most work per week (minutes)"),
  hard_harmful_daily_minutes: __("Hard and harmful work per day (minutes)"),
  hard_harmful_weekly_minutes: __("Hard and harmful work per week (minutes)"),
  intermittent_span_minutes: __("Longest span of split shifts (minutes)"),
  rotating_four_week_minutes: __("Rotating shifts: most work in four weeks (minutes)"),
  night_start_minute: __("Night work starts (minute of the day)"),
  night_end_minute: __("Night work ends (minute of the day)"),
  overtime_daily_cap_minutes: __("Overtime cap per day (minutes)"),
  emergency_overtime_cap_minutes: __("Emergency overtime cap (minutes)"),
  overtime_premium_percent: __("Overtime premium (percent)"),
  night_premium_percent: __("Night work premium (percent)"),
  rest_day_premium_percent: __("Rest day work premium (percent)"),
  shift_premium_two_percent: __("Two-shift premium (percent)"),
  shift_premium_three_percent: __("Three-shift premium (percent)"),
  shift_premium_night_percent: __("Night-shift premium (percent)"),
  annual_leave_days: __("Annual leave (working days)"),
  hard_harmful_annual_leave_weeks: __("Annual leave for hard and harmful work (weeks)"),
  leave_carry_over_days: __("Leave carried to the next year (days)"),
  hajj_leave_days: __("Hajj leave (days)"),
  hourly_leave_minutes_per_day: __("Hourly leave that makes one day (minutes)"),
  marriage_bereavement_leave_days: __("Marriage or bereavement leave (days)"),
  maternity_leave_days: __("Maternity leave (days)"),
  maternity_multiple_birth_extra_days: __("Extra maternity leave for twins or more (days)"),
  paternity_leave_days: __("Paternity leave (days)"),
  nursing_break_minutes: __("Nursing break (minutes)"),
  nursing_every_minutes: __("One nursing break every (minutes)"),
  nursing_child_max_months: __("Nursing breaks until the child is (months)"),
  juvenile_daily_reduction_minutes: __("Young workers: shorter day (minutes)"),
  juvenile_max_age_years: __("Young worker age limit (years)"),
}
