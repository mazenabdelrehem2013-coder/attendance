import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from './api/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { fakeServer, tokens } from './test/fakeServer'

const hrUser = {
  id: 'u-hr', email: 'hr@example.com', role: 'HR', must_change_password: false,
  employee: { id: 'e-hr', employee_code: 'EMP-0001', full_name: 'Ngozi Okafor' },
}
const adminUser = { ...hrUser, id: 'u-admin', email: 'admin@example.com', role: 'ADMIN', employee: null }

const chain = { ok: true, rows_checked: 1234, last_seq: 1234, problem: null, problem_seq: null, checked_at: '2026-10-05T01:00:00Z' }
const overview = {
  date_from: '2026-09-06', date_to: '2026-10-05', total_events: 12,
  by_severity: { LOW: 7, MEDIUM: 1, HIGH: 4, CRITICAL: 0 },
  by_type: [{ key: 'MOCK_LOCATION', label: null, count: 4 }, { key: 'LOGIN_FAILED', label: null, count: 8 }],
  per_day: [{ date: '2026-10-05', low: 7, medium: 1, high: 4, critical: 0 }],
  top_employees: [{ key: 'EMP-0101', label: 'Chinedu Eze', count: 4 }],
  failed_logins: 8, locked_accounts: 1, top_ips: [{ key: '203.0.113.9', label: null, count: 8 }],
  open_alerts: { LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 0 }, chain,
}
const alert = {
  id: 'a1', rule: 'REPEATED_SPOOFING', rule_label: 'Repeated fake location or tampering', severity: 'HIGH',
  title: 'Chinedu Eze: 3 serious check-in problems in 24 hours', details: {}, employee_id: 'e1', employee_name: 'Chinedu Eze',
  count: 3, first_seen_at: '2026-10-05T07:00:00Z', last_seen_at: '2026-10-05T08:00:00Z', status: 'OPEN',
  handled_by: null, handled_at: null, note: null,
}
const entry = {
  id: 'l1', seq: 42, created_at: '2026-10-05T09:00:00Z', actor: 'hr@example.com', actor_name: 'Ngozi Okafor', actor_role: 'HR',
  action: 'LOCATION_UPDATED', object_type: 'location', object_id: 'loc-1', changed: ['radius_m'], ip_address: '10.0.0.5',
}

function routes(user: typeof hrUser | typeof adminUser, extra: Record<string, unknown> = {}) {
  return {
    'POST /auth/refresh': { status: 200, body: tokens(user as never) },
    'GET /auth/me': { status: 200, body: user },
    'GET /hr/review': { status: 200, body: { items: [], total: 0 } },
    'GET /devices': { status: 200, body: { items: [], total: 0, page: 1, page_size: 1 } },
    'GET /notifications': { status: 200, body: { items: [], unread: 0 } },
    'GET /security/alerts': { status: 200, body: { items: [alert], total: 1 } },
    'GET /security/overview': { status: 200, body: overview },
    'GET /security/rules': { status: 200, body: [] },
    'GET /retention': { status: 200, body: [{ category: 'RAW_LOCATION', label: 'GPS coordinates', description: 'x', retain_days: 365, min_days: 30, automatic: true }] },
    'GET /retention/last-run': { status: 200, body: null },
    'GET /audit-logs/actions': { status: 200, body: ['LOCATION_UPDATED'] },
    'GET /audit-logs/chain': { status: 200, body: chain },
    'GET /audit-logs': { status: 200, body: { items: [entry], total: 1 } },
    'GET /audit-logs/l1': { status: 200, body: { ...entry, old_value: { radius_m: 150, name: 'Lagos' }, new_value: { radius_m: 400, name: 'Lagos' }, user_agent: 'Chrome', request_id: 'r1', row_hash: 'a'.repeat(64), prev_hash: null } },
    ...extra,
  } as never
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

describe('Security monitoring', () => {
  it('shows the overview, the tamper-check result and the open-alert badge', async () => {
    fakeServer(routes(hrUser))
    renderAt('/security')
    expect(await screen.findByText(/Audit log intact: 1,234 entries checked/)).toBeInTheDocument()
    expect(screen.getByText('Failed logins').previousSibling).toHaveTextContent('8')
    expect(screen.getByText('Chinedu Eze (EMP-0101)')).toBeInTheDocument()
    expect(screen.getByText('Fake-GPS app')).toBeInTheDocument()
    const nav = screen.getByRole('link', { name: /Security monitoring/ })
    await waitFor(() => expect(within(nav).getByText('1')).toBeInTheDocument())
  })

  it('shows tampering in red', async () => {
    fakeServer(routes(hrUser, { 'GET /security/overview': { status: 200, body: { ...overview, chain: { ...chain, ok: false, problem: 'Entries before #77 were deleted.' } } } }))
    renderAt('/security')
    expect(await screen.findByText(/Audit log tampering detected: Entries before #77 were deleted/)).toBeInTheDocument()
  })

  it('resolves an alert with a note', async () => {
    const calls = fakeServer(routes(hrUser, { 'POST /security/alerts/a1': { status: 200, body: { ...alert, status: 'RESOLVED' } } }))
    renderAt('/security')
    await userEvent.click(await screen.findByRole('tab', { name: 'Alerts' }))
    expect(await screen.findByText(alert.title)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Resolve' }))
    await userEvent.type(screen.getByLabelText(/What did you find/), 'Spoke to Chinedu; app removed')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Resolve' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/security/alerts/a1')).toBe(true))
    const body = JSON.parse(calls.find((c) => c.method === 'POST' && c.path === '/security/alerts/a1')!.init.body as string)
    expect(body).toEqual({ status: 'RESOLVED', note: 'Spoke to Chinedu; app removed' })
  })

  it('only an admin can edit retention periods', async () => {
    fakeServer(routes(hrUser))
    renderAt('/security')
    await userEvent.click(await screen.findByRole('tab', { name: 'Data retention' }))
    expect(await screen.findByText('1 year')).toBeInTheDocument()
    expect(screen.queryByLabelText('GPS coordinates days')).not.toBeInTheDocument()
    expect(screen.getByText(/Only an Admin can change/)).toBeInTheDocument()
  })

  it('an admin changes a retention period', async () => {
    const calls = fakeServer(routes(adminUser, { 'PUT /retention/RAW_LOCATION': { status: 200, body: {} } }))
    renderAt('/security')
    await userEvent.click(await screen.findByRole('tab', { name: 'Data retention' }))
    const input = await screen.findByLabelText('GPS coordinates days')
    await userEvent.clear(input)
    await userEvent.type(input, '180')
    await userEvent.tab()
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.init.body as string)).toEqual({ retain_days: 180 })
  })
})

describe('Audit log', () => {
  it('lists entries and shows before / after', async () => {
    fakeServer(routes(hrUser))
    renderAt('/audit-log')
    expect(await screen.findByText('Location updated')).toBeInTheDocument()
    expect(screen.getByText('radius_m')).toBeInTheDocument()
    await userEvent.click(screen.getByText('Location updated'))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('150')).toBeInTheDocument()
    expect(within(dialog).getByText('400')).toBeInTheDocument()
  })

  it('exports with the chosen filters', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const calls = fakeServer(routes(hrUser, { 'POST /audit-logs/export': { status: 200, body: {} } }))
    renderAt('/audit-log')
    await userEvent.click(await screen.findByRole('button', { name: 'Export Excel' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/audit-logs/export')).toBe(true))
    const body = JSON.parse(calls.find((c) => c.path === '/audit-logs/export')!.init.body as string)
    expect(body.date_from).toMatch(/^\d{4}-\d{2}-01$/)
  })
})

