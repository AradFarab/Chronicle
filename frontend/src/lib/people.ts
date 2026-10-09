/** Shapes and option lists shared by the people screens (employees, org chart, delegation). */
import { __ } from "./i18n"
import type { Employee } from "./types"

/** A designation held by someone, as GET /admin/employees lists it. */
export interface HeldDesignation {
  assignment_id: number
  designation_id: number
  valid_from: string
  valid_to: string | null
  current: boolean
}

/** A row of GET /admin/employees/{id}: the employee, their login and the designations they held. */
export interface EmployeeRow extends Employee {
  detail_code: string | null
  first_name: string
  last_name: string
  national_id: string | null
  gender: string | null
  mobile: string | null
  email: string | null
  contract_type: string
  start_date: string
  end_date: string | null
  overtime_consent_on_file: boolean
  overtime_consent_date: string | null
  birth_date: string | null
  biometric_consent_date: string | null
  uses_card_instead_of_biometrics: boolean
  nursing_until: string | null
  username: string
  is_admin: boolean
  is_active_user: boolean
  designations: HeldDesignation[]
}

export const employeeStatusOptions = () => [
  { value: "active", label: __("Active") },
  { value: "suspended", label: __("Suspended") },
  { value: "left", label: __("Left") },
]
