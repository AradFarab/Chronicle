import { reactive } from "vue"
import { api } from "./api"
import { session } from "./session"

/** Badges in the navigation: requests waiting for me, device users without an employee. */
export const counts = reactive({ approvals: 0, unmappedUsers: 0 })

let last = 0

export async function refreshCounts(force = false): Promise<void> {
  if (!session.user || (!force && Date.now() - last < 20_000)) return
  last = Date.now()
  try {
    counts.approvals = (await api.get<unknown[]>("/inbox")).length
    if (session.is_operator) counts.unmappedUsers = (await api.get<unknown[]>("/devices/users/unmapped")).length
  } catch {
    // badges are a convenience; the pages show the errors
  }
}
