export interface Punch {
  jdate: string
  time: string
  direction: string | null
  source: string
  ref: string
}

export interface Attendance {
  jdate: string
  status: string
  shift?: string | null
  day_type?: string | null
  holiday_title?: string | null
  first_in?: string | null
  last_out?: string | null
  required_minutes?: number
  worked_minutes?: number
  credited_minutes?: number
  late_minutes?: number
  early_leave_minutes?: number
  absence_minutes?: number
  leave_minutes?: number
  mission_minutes?: number
  overtime_normal_minutes?: number
  unapproved_extra_minutes?: number
  warnings?: string | null
}

export interface Option {
  value: string
  label: string
}
