/**
 * The client for the Hozur JSON API (/api). Every unsafe request carries the X-Hozur header
 * (the server's CSRF guard); errors come back as {message} already translated to Persian.
 */

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown
  ) {
    super(message)
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

function url(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value))
  }
  const qs = params.toString()
  return `/api${path}${qs ? `?${qs}` : ""}`
}

let onUnauthorized: () => void = () => {}

/** Called when the session has expired (the app shows the login page). */
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "X-Hozur": "1" }
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json; charset=utf-8"
    payload = JSON.stringify(body)
  }
  const response = await fetch(url(path, query), { method, headers, body: payload, credentials: "same-origin" })
  if (response.status === 401 && !path.startsWith("/auth/")) onUnauthorized()
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(data.message || response.statusText || "Error", response.status, data.detail)
  }
  const type = response.headers.get("content-type") ?? ""
  return (type.includes("application/json") ? response.json() : response.blob()) as Promise<T>
}

export const api = {
  get: <T = unknown>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T = unknown>(path: string, body: unknown = {}) => request<T>("POST", path, body),
  put: <T = unknown>(path: string, body: unknown = {}) => request<T>("PUT", path, body),
  patch: <T = unknown>(path: string, body: unknown = {}) => request<T>("PATCH", path, body),
  del: <T = unknown>(path: string, body?: unknown) => request<T>("DELETE", path, body),
  upload: <T = unknown>(path: string, form: FormData) => request<T>("POST", path, form),
}

/** Saves a file response under the server's filename (Content-Disposition). */
async function saveResponse(response: Response, fallbackName: string): Promise<void> {
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(data.message || response.statusText, response.status)
  }
  const disposition = response.headers.get("content-disposition") ?? ""
  const match = /filename\*=UTF-8''([^;]+)/.exec(disposition)
  const name = match ? decodeURIComponent(match[1]) : fallbackName
  const link = document.createElement("a")
  link.href = URL.createObjectURL(await response.blob())
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 10_000)
}

/** POST that returns a file (report export): saves it under the server's filename. */
export async function download(path: string, body: unknown): Promise<void> {
  const response = await fetch(url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8", "X-Hozur": "1" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  })
  await saveResponse(response, "report")
}

/** GET that returns a file (the sample workbook of an Excel import). */
export async function downloadGet(path: string, query?: Query): Promise<void> {
  const response = await fetch(url(path, query), {
    headers: { "X-Hozur": "1" },
    credentials: "same-origin",
  })
  if (response.status === 401) onUnauthorized()
  await saveResponse(response, "sample.xlsx")
}
