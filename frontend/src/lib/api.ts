/** One small client for Frappe's /api/method endpoints, with Frappe's error messages. */

export class ApiError extends Error {
  constructor(message: string, public status: number, public excType?: string) {
    super(message)
  }
}

function stripHtml(text: string): string {
  const el = document.createElement("div")
  el.innerHTML = text
  return el.textContent?.trim() || text
}

function serverMessages(data: Record<string, unknown>): string[] {
  try {
    const raw = data._server_messages
    if (typeof raw !== "string") return []
    return (JSON.parse(raw) as string[]).map((m) => {
      try {
        const parsed = JSON.parse(m)
        return stripHtml(parsed.message ?? m)
      } catch {
        return stripHtml(m)
      }
    })
  } catch {
    return []
  }
}

export async function call<T = unknown>(method: string, args: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch(`/api/method/${method}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json; charset=utf-8",
      "X-Frappe-CSRF-Token": window.csrf_token ?? "",
    },
    credentials: "same-origin",
    body: JSON.stringify(args),
  })
  let data: Record<string, unknown> = {}
  try {
    data = await response.json()
  } catch {
    // non-JSON error page
  }
  if (!response.ok || data.exc || data.exc_type) {
    if (response.status === 403 && data.exc_type === "SessionExpired") {
      window.location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname)
    }
    const messages = serverMessages(data)
    const message =
      messages.join("\n") ||
      (data.exception as string | undefined)?.split(":").slice(1).join(":").trim() ||
      response.statusText
    throw new ApiError(message || "Error", response.status, data.exc_type as string | undefined)
  }
  return data.message as T
}

/** Upload a private file through Frappe's standard endpoint; returns its file_url. */
export async function uploadFile(file: File): Promise<string> {
  const form = new FormData()
  form.append("file", file, file.name)
  form.append("is_private", "1")
  form.append("folder", "Home")
  const response = await fetch("/api/method/upload_file", {
    method: "POST",
    headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token ?? "" },
    credentials: "same-origin",
    body: form,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok || data.exc) {
    throw new ApiError(serverMessages(data).join("\n") || response.statusText, response.status)
  }
  return data.message.file_url as string
}
