import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from './api/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { fakeServer, manager, team, tokens } from './test/fakeServer'

const hrUser = {
  id: 'u-hr', email: 'hr@example.com', role: 'HR', must_change_password: false,
  employee: { id: 'e-hr', employee_code: 'EMP-0001', full_name: 'Ngozi Okafor' },
}

const schedule = {
  id: 's1', name: 'Weekly for managers', report: 'weekly', frequency: 'weekly', time: '08:00', days: [0, 1, 2, 3, 4, 5],
  weekday: 0, day_of_month: 1, daily_period: 'previous', formats: ['EXCEL', 'PDF'], recipient_roles: ['HR', 'MANAGER'],
  location_id: null, department_id: null, is_enabled: true, description: 'Every Monday at 08:00',
  next_run_at: '2026-10-12T07:00:00Z', last_run_at: null, timezone: 'Africa/Lagos',
}

const lateAlert = {
  event: 'LATE_EMPLOYEE', label: 'Late arrival', description: 'An employee checked in late.',
  enabled: true, roles: ['MANAGER'], thresholds: {},
}

const readyFile = {
  id: 'f1', title: 'Weekly attendance report', period: '28 September 2026 – 04 October 2026', scope: 'Your team',
  schedule_name: 'Weekly for managers', format: 'EXCEL', filename: 'attendance-weekly-2026-09-28-to-2026-10-04.xlsx',
  size_bytes: 20480, rows: 7, created_at: '2026-10-05T07:00:00Z',
}

function routes(user: typeof hrUser | typeof manager, extra: Record<string, unknown> = {}) {
  return {
    'POST /auth/refresh': { status: 200, body: tokens(user as never) },
    'GET /auth/me': { status: 200, body: user },
    'GET /hr/overview': { status: 200, body: { date: '2026-10-05', summary: team.summary, suspicious_attempts: 0, rejected_attempts: 0, pending_reviews_total: 0, by_location: [], by_department: [] } },
    'GET /hr/trend': { status: 200, body: [] },
    'GET /hr/review': { status: 200, body: { items: [], total: 0 } },
    'GET /devices': { status: 200, body: { items: [], total: 0, page: 1, page_size: 1 } },
    'GET /manager/attendance': { status: 200, body: team },
    'GET /notifications': { status: 200, body: { items: [], unread: 0 } },
    'GET /locations': { status: 200, body: [] },
    'GET /departments': { status: 200, body: [] },
    'GET /reports/daily': { status: 200, body: { title: 'Daily attendance report', rows: [], totals: {} } },
    'GET /reports/ready': { status: 200, body: { items: [readyFile], total: 1, keep_days: 90 } },
    'GET /hr/report-schedules': { status: 200, body: [schedule] },
    'GET /hr/alert-settings': { status: 200, body: [lateAlert] },
    ...extra,
  } as never
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider><App /></AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

describe('Alerts bell', () => {
  it('shows unread alerts and opens the linked page', async () => {
    const calls = fakeServer(routes(hrUser, {
      'GET /notifications': { status: 200, body: { unread: 1, items: [{
        id: 'n1', event: 'DEVICE_APPROVAL_REQUESTED', title: 'New phone to approve: Ada', body: 'Ada registered a phone.',
        link: '/phones', created_at: new Date().toISOString(), read: false }] } },
      'POST /notifications/n1/read': { status: 204 },
    }))
    renderAt('/')
    const bell = await screen.findByRole('button', { name: 'Alerts' })
    await waitFor(() => expect(within(bell).getByText('1')).toBeInTheDocument())
    await userEvent.click(bell)
    await userEvent.click(await screen.findByText('New phone to approve: Ada'))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/notifications/n1/read')).toBe(true))
    expect(await screen.findByRole('heading', { name: /Phones/ }, { timeout: 4000 })).toBeInTheDocument()
  })
})

describe('Ready reports', () => {
  it('a manager downloads a ready team report', async () => {
    const calls = fakeServer(routes(manager, {
      'GET /reports/ready/f1/download': { status: 200, body: {} },
    }))
    renderAt('/reports?tab=ready')
    expect(await screen.findByText('28 September 2026 – 04 October 2026')).toBeInTheDocument()
    expect(screen.getByText('Your team')).toBeInTheDocument()
    expect(screen.getByText(/kept for 90 days/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: `Download ${readyFile.filename}` }))
    await waitFor(() => expect(calls.some((c) => c.path === '/reports/ready/f1/download')).toBe(true))
  })
})

describe('Scheduled reports page', () => {
  it('lists schedules and creates one now', async () => {
    const calls = fakeServer(routes(hrUser, {
      'POST /hr/report-schedules/s1/run-now': { status: 200, body: { files_created: 6, message: '6 file(s) created. See Ready reports.' } },
    }))
    renderAt('/scheduled-reports')
    expect(await screen.findByText('Weekly for managers')).toBeInTheDocument()
    expect(screen.getByText('Every Monday at 08:00')).toBeInTheDocument()
    expect(screen.getByText('HR, Managers (own team)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Create now' }))
    expect(await screen.findByText('Weekly for managers: 6 file(s) created. See Ready reports.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/hr/report-schedules/s1/run-now')).toBe(true)
  })

  it('creates a scheduled report', async () => {
    const calls = fakeServer(routes(hrUser, { 'POST /hr/report-schedules': { status: 201, body: schedule } }))
    renderAt('/scheduled-reports')
    await userEvent.click(await screen.findByRole('button', { name: 'New scheduled report' }))
    await userEvent.type(screen.getByLabelText(/Name/), 'Monday report')
    await userEvent.click(screen.getByLabelText('Every manager (own team only)'))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/hr/report-schedules')).toBe(true))
    const body = JSON.parse(calls.find((c) => c.method === 'POST' && c.path === '/hr/report-schedules')!.init.body as string)
    expect(body).toMatchObject({ name: 'Monday report', report: 'weekly', frequency: 'weekly', recipient_roles: ['HR', 'MANAGER'] })
    expect(body).not.toHaveProperty('extra_recipients')
  })

  it('turns an alert off', async () => {
    const calls = fakeServer(routes(hrUser, { 'PUT /hr/alert-settings/LATE_EMPLOYEE': { status: 200, body: lateAlert } }))
    renderAt('/scheduled-reports')
    await userEvent.click(await screen.findByRole('tab', { name: 'Alerts' }))
    await userEvent.click(await screen.findByRole('switch', { name: 'Late arrival on' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(JSON.parse(calls.find((c) => c.method === 'PUT')!.init.body as string)).toMatchObject({ enabled: false, roles: ['MANAGER'] })
  })
})
