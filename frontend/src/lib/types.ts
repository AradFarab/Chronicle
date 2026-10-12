/** A punch of one day as the day view shows it: raw device / file punches plus manual ones. */
export interface Punch {
  id?: number | null
  time: string // 'HH:MM:SS'
  direction: string | null // in | out | unknown
  source: string // device | file_import | manual
  device_id?: number | null
  is_duplicate?: boolean
  ignored?: boolean // set aside by an approved manual entry
  request_id?: number | null
}

/** One calculated day (GET /attendance). Codes stay codes; labels come from lib/format. */
export interface Attendance {
  id?: number
  employee_id?: number
  jdate: string
  status: string // present | absent | incomplete | leave | mission | holiday | rest_day | not_scheduled
  day_type?: string | null // workday | friday | official_holiday | company_holiday
  holiday_title?: string | null
  shift_id?: number | null
  rest_day?: boolean
  first_in?: string | null // 'HH:MM'
  last_out?: string | null
  punch_count?: number
  required_minutes?: number
  worked_minutes?: number
  credited_minutes?: number
  late_minutes?: number
  early_leave_minutes?: number
  absence_minutes?: number
  absent_day?: boolean
  leave_minutes?: number
  leave_days?: number
  mission_minutes?: number
  extra_minutes?: number
  overtime_normal_minutes?: number
  overtime_exceptional_minutes?: number
  overtime_emergency_minutes?: number
  unapproved_extra_minutes?: number
  night_work_minutes?: number
  warnings?: string[] | null
  calculated_at?: string | null
}

/** GET /attendance/day */
export interface DayDetails {
  attendance: Attendance | null
  punches: Punch[]
  manual_punches: { time: string; direction: string | null; request_id: number | null }[]
  schedule: {
    shift_id: number | null
    shift: string | null
    work_pattern_id: number | null
    rest_day: boolean
    source: string | null
  }
  period_closed: boolean
}

/** A row of GET /admin/employees (only the people the user may see). */
export interface Employee {
  id: number
  code: string
  full_name: string
  department_id: number | null
  work_location_id: number | null
  status: string // active | suspended | left
}

export interface LeaveType {
  id: number
  name: string
  category: string
  allow_hourly: boolean
  is_paid: boolean
}

export interface ApprovalStep {
  step: number
  approver_type: string
  approver_names: string[]
  status: string
  acted_at: string | null
  comment: string | null
}

/** A request as the API returns it (views.request_view). */
export interface RequestView {
  id: number
  number: string
  kind: string // leave | mission | overtime | correction
  request_type: string // daily_leave | hourly_leave | mission | overtime | attendance_correction
  status: string // pending | approved | rejected | cancelled
  employee_id: number
  employee_name: string | null
  start_jdate: string
  end_jdate: string
  reason: string | null
  entered_by_admin: boolean
  created_at: string | null
  waiting_for: string[]
  approvals: ApprovalStep[]
  can_act?: boolean
  is_acceptance?: boolean
  leave?: {
    leave_type_id: number
    unit: string
    from_time: string | null
    to_time: string | null
    total_days: number
    total_minutes: number | null
  }
  mission?: { unit: string; destination: string | null; from_time: string | null; to_time: string | null }
  overtime?: {
    overtime_kind: string
    minutes: number
    from_time: string | null
    to_time: string | null
    assigned_by_manager: boolean
  }
  items?: {
    action: string
    time: string | null
    direction: string | null
    raw_punch_id: number | null
    note: string | null
  }[]
}

export interface Option {
  value: string
  label: string
}

/** A field of an Excel import (POST /import/{name}/inspect). */
export interface ImportField {
  key: string
  label: string
  kind: "text" | "number" | "bool" | "jdate" | "time" | "choice" | "ref"
  required: boolean
  help: string
  example: string
  choices: string[]
}

/** A column of the uploaded file: 1-based index, its header and a few values under it. */
export interface ImportColumn {
  index: number
  header: string
  samples: string[]
}

/** POST /import/{name}/inspect: what the column-mapping panel needs. */
export interface ImportInspection {
  sheets: string[]
  sheet: string
  header_row: number
  row_count: number
  columns: ImportColumn[]
  fields: ImportField[]
  suggested: Record<string, number | null>
}

/** What the server receives as `mapping`: field -> column index, or one value for every row. */
export type ImportMapping = Record<string, number | { value: string }>

/** POST /import/{name}: a dry run (check) or the real import. */
export interface ImportResult {
  imported: boolean
  dry_run: boolean
  created: number
  checked: number
  errors: { row: number; message: string }[]
  rows: { row: number; values: Record<string, unknown>; notes: string[]; errors: string[] }[]
}

/** A backup file on the server (GET /admin/backups). */
export interface Backup {
  name: string
  size: number // bytes
  automatic: boolean
  jdate: string
  time: string // 'HH:MM'
  created_at: string
}

export interface BackupSchedule {
  enabled: boolean
  hour: number // 0-23
  keep: number // automatic backups kept
}

/** A request the calculation proposes from a day (GET /suggestions). */
export interface Suggestion {
  id: number
  employee_id: number
  jdate: string
  request_type: "overtime" | "hourly_leave" | "attendance_correction"
  from_time: string | null // 'HH:MM'
  to_time: string | null
  minutes: number
  status: string
  request_id: number | null
}
