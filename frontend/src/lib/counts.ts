import { reactive } from "vue"
import { call } from "./api"
import { session } from "./session"

/** Badges in the navigation: requests waiting for me, device users without an employee. */
export const counts = reactive({ approvals: 0, unmappedUsers: 0 })

let last = 0

export async function refreshCounts(force = false): Promise<void> {
  if (!force && Date.now() - last < 20_000) return
  last = Date.now()
  try {
    const inbox = await call<unknown[]>("hozur.approvals.my_approvals")
    counts.approvals = inbox.length
    if (session.is_operator) {
      const unmapped = await call<unknown[]>("hozur.devices.service.unmapped_device_users")
      counts.unmappedUsers = unmapped.length
    }
  } catch {
    // badges are a convenience; the pages show the errors
  }
}
