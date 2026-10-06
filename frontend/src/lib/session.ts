import { reactive } from "vue"
import { call } from "./api"

export interface BootEmployee {
  name: string
  full_name: string
  department: string | null
  designation: string | null
  branch: string | null
}

export interface Boot {
  user: string
  full_name: string
  employee: BootEmployee | null
  organization: string
  today: string
  is_operator: boolean
  is_system_manager: boolean
  is_ceo: boolean
  is_manager: boolean
}

const empty: Boot = {
  user: "Guest",
  full_name: "",
  employee: null,
  organization: "",
  today: "",
  is_operator: false,
  is_system_manager: false,
  is_ceo: false,
  is_manager: false,
}

/** Rendered into the page by hozur/www/hozur.py; refreshed from the API when missing. */
export const session = reactive<Boot>({ ...empty, ...(window.hozur_boot ?? {}) })

export async function refreshSession(): Promise<void> {
  Object.assign(session, await call<Boot>("hozur.api.pwa.boot"))
}

export async function logout(): Promise<void> {
  await call("logout")
  window.location.href = "/login?redirect-to=/hozur"
}
