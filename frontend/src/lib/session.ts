import { reactive } from "vue"
import { api } from "./api"

export interface MeEmployee {
  id: number
  code: string
  full_name: string
  department_id: number | null
  branch_id: number | null
}

export interface Me {
  user: { id: number; username: string; full_name: string; language: string } | null
  roles: string[]
  employee: MeEmployee | null
  organization: string
  today: string
  is_operator: boolean
  is_admin: boolean
  is_manager: boolean
  warnings: string[]
}

const empty: Me = {
  user: null,
  roles: [],
  employee: null,
  organization: "",
  today: "",
  is_operator: false,
  is_admin: false,
  is_manager: false,
  warnings: [],
}

export const session = reactive<Me>({ ...empty })

/** Load who is logged in; false when nobody is. */
export async function refreshSession(): Promise<boolean> {
  try {
    Object.assign(session, await api.get<Me>("/me"))
    return true
  } catch {
    Object.assign(session, empty)
    return false
  }
}

export async function login(username: string, password: string): Promise<void> {
  await api.post("/auth/login", { username, password })
  await refreshSession()
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout").catch(() => undefined)
  Object.assign(session, empty)
  window.location.href = "/login"
}
