/**
 * Talks to the API (same domain: /api/v1).
 *
 * - The access token is kept ONLY in memory (never in localStorage, where any injected
 *   script could read it).
 * - The refresh token lives in an HttpOnly cookie set by the server; JavaScript can't read it.
 *   When the access token expires, it is renewed once and the request repeated.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

const BASE = '/api/v1'

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
let onSessionExpired: (() => void) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler
}

async function toError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    if (body?.error) {
      // Validation errors list each wrong field: show them so the user knows what to fix.
      const details = Array.isArray(body.error.details)
        ? body.error.details.map((d: { field?: string; issue?: string }) => `${d.field ?? ''}: ${d.issue ?? ''}`).join('; ')
        : ''
      return new ApiError(response.status, body.error.code, details ? `${body.error.message} ${details}` : body.error.message)
    }
  } catch {
    // not JSON
  }
  return new ApiError(response.status, 'UNKNOWN', 'Something went wrong. Please try again.')
}

/** Renews the session using the refresh cookie. Only one renewal runs at a time. */
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const r = await fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'same-origin' })
        if (!r.ok) return false
        accessToken = (await r.json()).access_token
        return true
      } catch {
        return false
      } finally {
        refreshing = null
      }
    })()
  }
  return refreshing
}

async function send(path: string, init: RequestInit, retried = false): Promise<Response> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'NETWORK', "Can't reach the server. Check your connection and try again.")
  }
  if (response.status === 401 && !retried && !path.startsWith('/auth/login')) {
    if (await refreshSession()) return send(path, init, true)
    accessToken = null
    onSessionExpired?.()
    throw new ApiError(401, 'SESSION_EXPIRED', 'Your session has expired. Please log in again.')
  }
  if (!response.ok) throw await toError(response)
  return response
}

export async function apiGet<T>(path: string, params?: Record<string, string | string[] | undefined>): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === '') continue
    for (const v of Array.isArray(value) ? value : [value]) query.append(key, v)
  }
  const qs = query.toString()
  return (await send(qs ? `${path}?${qs}` : path, { method: 'GET' })).json()
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await send(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
  return response.status === 204 ? (undefined as T) : response.json()
}

/** Downloads a file (e.g. CSV export) with the current login. */
export async function apiDownload(path: string, params: Record<string, string | string[] | undefined>, filename: string) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    for (const v of Array.isArray(value) ? value : [value]) query.append(key, v)
  }
  const blob = await (await send(`${path}?${query}`, { method: 'GET' })).blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return (await send(path, { method: 'PUT', body: JSON.stringify(body) })).json()
}

export async function apiDelete(path: string): Promise<void> {
  await send(path, { method: 'DELETE' })
}

/** POSTs a request and saves the returned file (Excel/PDF exports). */
export async function apiDownloadPost(path: string, body: unknown): Promise<void> {
  const response = await send(path, { method: 'POST', body: JSON.stringify(body) })
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'report'
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
