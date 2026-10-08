/**
 * The configuration tables edited in the PWA, described once: the generic list and form
 * (pages/ResourceList.vue, components/ResourceForm.vue) render them. The server
 * (backend/hozur/services/resources.py) validates everything again.
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
}

export interface ResourceDef {
  name: string // URL segment under /api/admin
  title: string
  singular: string
  group: string
  icon: string
  fields: FieldDef[]
  admin?: boolean // only admins may change it
  reasonOnChange?: boolean
  canDelete?: boolean
  defaults?: Record<string, unknown>
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
    name: "branches",
    title: __("Branches"),
    singular: __("Branch"),
    group: __("Organization"),
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
    group: __("Organization"),
    icon: "lucide-network",
    canDelete: true,
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
      { key: "parent_id", label: __("Parent department"), type: "ref", ref: "departments", list: true },
      { key: "is_group", label: __("Has sub-departments"), type: "bool" },
      { key: "manager_id", label: __("Manager"), type: "ref", ref: "employees", list: true },
      {
        key: "default_approver_id",
        label: __("Default approver"),
        type: "ref",
        ref: "employees",
        help: __("When set, approves instead of the manager"),
      },
      { key: "deputy_id", label: __("Deputy"), type: "ref", ref: "employees" },
      { key: "deputy_from", label: __("Deputy from"), type: "jdate" },
      { key: "deputy_to", label: __("Deputy until"), type: "jdate" },
    ],
  },
  {
    name: "designations",
    title: __("Designations"),
    singular: __("Designation"),
    group: __("Organization"),
    icon: "lucide-briefcase",
    canDelete: true,
    fields: [
      { key: "name", label: __("Name"), type: "text", required: true, list: true },
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
    name: "employees",
    title: __("Employees"),
    singular: __("Employee"),
    group: __("Organization"),
    icon: "lucide-users",
    defaults: { status: "active", contract_type: "full_time" },
    fields: [
      { key: "code", label: __("Personnel code"), type: "text", required: true, list: true, dir: "ltr" },
      { key: "first_name", label: __("First name"), type: "text", required: true },
      { key: "last_name", label: __("Last name"), type: "text", required: true },
      { key: "full_name", label: __("Full name"), type: "text", list: true, show: () => false },
      { key: "national_id", label: __("National code"), type: "text", dir: "ltr" },
      {
        key: "gender",
        label: __("Gender"),
        type: "select",
        options: opts([
          ["male", __("Male")],
          ["female", __("Female")],
        ]),
      },
      { key: "mobile", label: __("Mobile"), type: "text", dir: "ltr" },
      { key: "email", label: __("Email"), type: "text", dir: "ltr" },
      {
        key: "status",
        label: __("Status"),
        type: "select",
        required: true,
        list: true,
        options: opts([
          ["active", __("Active")],
          ["suspended", __("Suspended")],
          ["left", __("Left")],
        ]),
      },
      {
        key: "contract_type",
        label: __("Contract"),
        type: "select",
        required: true,
        options: opts([
          ["full_time", __("Full time")],
          ["part_time", __("Part time")],
          ["hourly", __("Hourly")],
        ]),
      },
      { key: "start_date", label: __("Start date"), type: "jdate", required: true },
      { key: "end_date", label: __("End date"), type: "jdate" },
      { key: "branch_id", label: __("Branch"), type: "ref", ref: "branches" },
      { key: "department_id", label: __("Department"), type: "ref", ref: "departments", list: true },
      { key: "designation_id", label: __("Designation"), type: "ref", ref: "designations" },
      { key: "reports_to_id", label: __("Reports to"), type: "ref", ref: "employees" },
      {
        key: "overtime_consent_on_file",
        label: __("Written overtime consent on file"),
        type: "bool",
        help: __("Article 59"),
      },
      { key: "overtime_consent_date", label: __("Overtime consent date"), type: "jdate" },
      { key: "birth_date", label: __("Birth date"), type: "jdate", help: __("Only for young-worker rules") },
      {
        key: "biometric_consent_date",
        label: __("Biometric consent date"),
        type: "jdate",
        help: __("Written consent is needed before enrolling face or fingerprint"),
      },
      { key: "uses_card_instead_of_biometrics", label: __("Uses a card instead of biometrics"), type: "bool" },
      { key: "nursing_until", label: __("Nursing breaks until"), type: "jdate", help: __("Article 78") },
    ],
  },
  {
    name: "shifts",
    title: __("Shifts"),
    singular: __("Shift"),
    group: __("Work schedules"),
    icon: "lucide-clock",
    canDelete: true,
    defaults: { shift_type: "fixed", break_minutes: 0, grace_late_minutes: 0, grace_early_minutes: 0, overtime_after_minutes: 0 },
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
      { key: "start_time", label: __("Start"), type: "time", required: true, list: true },
      { key: "end_time", label: __("End"), type: "time", required: true, list: true },
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
        show: (v) => v.shift_type === "flexible",
      },
      { key: "break_start_time", label: __("Break start"), type: "time" },
      { key: "break_end_time", label: __("Break end"), type: "time" },
      { key: "break_minutes", label: __("Break minutes without punching"), type: "number" },
      { key: "grace_late_minutes", label: __("Grace for late arrival (minutes)"), type: "number" },
      { key: "grace_early_minutes", label: __("Grace for early leave (minutes)"), type: "number" },
      { key: "overtime_after_minutes", label: __("Extra work counts after (minutes)"), type: "number" },
      { key: "color", label: __("Colour"), type: "text", dir: "ltr" },
    ],
  },
  {
    name: "work-patterns",
    title: __("Work patterns"),
    singular: __("Work pattern"),
    group: __("Work schedules"),
    icon: "lucide-calendar-range",
    canDelete: true,
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
      {
        key: "days",
        label: __("Days"),
        type: "children",
        children: [
          {
            key: "weekday",
            label: __("Weekday"),
            type: "select",
            options: weekdayOptions,
            show: (v) => v.pattern_type !== "rotating",
          },
          {
            key: "cycle_day",
            label: __("Day of the cycle"),
            type: "number",
            show: (v) => v.pattern_type === "rotating",
          },
          { key: "shift_id", label: __("Shift (empty = day off)"), type: "ref", ref: "shifts" },
        ],
      },
      { key: "description", label: __("Description"), type: "textarea" },
      { key: "change_reason", label: __("Reason for the change"), type: "textarea" },
    ],
  },
  {
    name: "work-pattern-assignments",
    title: __("Pattern assignments"),
    singular: __("Pattern assignment"),
    group: __("Work schedules"),
    icon: "lucide-calendar-check",
    canDelete: true,
    defaults: { target_type: "employee" },
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
          ["department", __("A department and its sub-departments")],
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
      { key: "valid_from", label: __("From"), type: "jdate", required: true, list: true },
      { key: "valid_to", label: __("Until"), type: "jdate", list: true },
      { key: "note", label: __("Note"), type: "textarea" },
    ],
  },
  {
    name: "shift-overrides",
    title: __("One-day shift changes"),
    singular: __("Shift change"),
    group: __("Work schedules"),
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
    group: __("Rules"),
    icon: "lucide-scale",
    admin: true,
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
    group: __("Rules"),
    icon: "lucide-tree-palm",
    admin: true,
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
    group: __("Approvals"),
    icon: "lucide-git-branch",
    admin: true,
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
              ["direct_manager", __("Direct manager")],
              ["parent_department_manager", __("Manager of the parent department")],
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
    group: __("Approvals"),
    icon: "lucide-user-cog",
    admin: true,
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

/** Labels of the labor-law parameters (backend/hozur/engine/rules.py PARAMETERS). */
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
