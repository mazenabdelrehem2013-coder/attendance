import { vi } from 'vitest'

type Handler = (url: URL, init: RequestInit) => { status: number; body?: unknown }

/** Replaces window.fetch with canned answers per "METHOD /path". Returns the request log. */
export function fakeServer(routes: Record<string, Handler | { status: number; body?: unknown }>) {
  const calls: { method: string; path: string; url: URL; init: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit = {}) => {
    const url = new URL(input, 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    const path = url.pathname.replace('/api/v1', '')
    calls.push({ method, path, url, init })
    const route = routes[`${method} ${path}`]
    if (!route) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: `no fake for ${method} ${path}` } }), { status: 404 })
    const { status, body } = typeof route === 'function' ? route(url, init) : route
    return new Response(status === 204 ? null : JSON.stringify(body ?? {}), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }))
  return calls
}

export const manager = {
  id: 'u1', email: 'manager.lagos@example.com', role: 'MANAGER', must_change_password: false,
  employee: { id: 'e1', employee_code: 'EMP-0002', full_name: 'Tunde Bakare' },
}

export const tokens = (user = manager) => ({ access_token: 'access-1', expires_in: 900, refresh_token: null, user })

export const team = {
  date: '2026-10-05',
  generated_at: '2026-10-05T09:00:00Z',
  summary: {
    total_employees: 3, present: 2, late: 1, absent: 1, not_checked_in: 0,
    checked_in_now: 2, missing_checkout: 0, suspicious: 1, on_leave: 0,
  },
  rows: [
    { employee_id: 'a', employee_code: 'EMP-0101', full_name: 'Chinedu Eze', department: 'Sales', location: 'Lagos Office',
      check_in: '2026-10-05T08:05:00Z', check_out: null, worked_minutes: 0, status: 'PRESENT', arrival_status: 'PRESENT',
      departure_status: null, checked_in_now: true, verification_status: 'VERIFIED', note: null },
    { employee_id: 'b', employee_code: 'EMP-0102', full_name: 'Funmi Adeyemi', department: 'Finance', location: 'Lagos Office',
      check_in: '2026-10-05T08:40:00Z', check_out: null, worked_minutes: 0, status: 'LATE', arrival_status: 'LATE',
      departure_status: null, checked_in_now: true, verification_status: 'PENDING_REVIEW', note: null },
    { employee_id: 'c', employee_code: 'EMP-0104', full_name: 'Bisi Ogunleye', department: 'Operations', location: 'Lagos Office',
      check_in: null, check_out: null, worked_minutes: 0, status: 'ABSENT', arrival_status: null,
      departure_status: null, checked_in_now: false, verification_status: null, note: null },
  ],
}
