import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from './api/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { fakeServer, team, tokens } from './test/fakeServer'

const hrUser = {
  id: 'u-hr', email: 'hr@example.com', role: 'HR', must_change_password: false,
  employee: { id: 'e-hr', employee_code: 'EMP-0001', full_name: 'Ngozi Okafor' },
}

const overview = {
  date: '2026-10-05', summary: team.summary, suspicious_attempts: 2, rejected_attempts: 1, pending_reviews_total: 3,
  by_location: [{ name: 'Lagos Office', employees: 3, present: 2, late: 1, absent: 1, pending_review: 0, on_leave: 0 }],
  by_department: [{ name: 'Sales', employees: 3, present: 2, late: 1, absent: 1, pending_review: 0, on_leave: 0 }],
}

const reviewItem = {
  event_id: 'ev1', employee_id: 'e1', employee_code: 'EMP-0101', employee_name: 'Chinedu Eze', event_type: 'CHECK_IN',
  server_time: '2026-10-05T08:00:00Z', result: 'FLAGGED', reason_code: 'OUTSIDE_LOCATION', location: 'Lagos Office',
  distance_m: 1323, accuracy_m: 5, risk_score: 30, failed_checks: ['geofence'], review_decision: null,
  reviewed_by: null, reviewed_at: null, review_note: null,
}

const policy = {
  location_id: null, location_name: null, verification_mode: 'GPS_ONLY', on_mock_location: 'FLAG', on_integrity_fail: 'FLAG',
  on_poor_accuracy: 'FLAG', on_stale_location: 'FLAG', on_outside_geofence: 'FLAG', on_impossible_travel: 'FLAG',
  on_clock_skew: 'FLAG', on_qr_fail: 'FLAG', max_accuracy_m: 100, max_fix_age_s: 60, challenge_ttl_s: 90,
  max_travel_speed_kmh: 200, max_clock_skew_s: 300, flagged_counts_before_review: false,
}

function hrRoutes(extra: Record<string, unknown> = {}) {
  return {
    'POST /auth/refresh': { status: 200, body: tokens(hrUser as never) },
    'GET /auth/me': { status: 200, body: hrUser },
    'GET /hr/overview': { status: 200, body: overview },
    'GET /hr/trend': { status: 200, body: [] },
    'GET /hr/review': { status: 200, body: { items: [reviewItem], total: 1 } },
    'GET /devices': { status: 200, body: { items: [], total: 2, page: 1, page_size: 1 } },
    'GET /locations': { status: 200, body: [{ id: 'l1', name: 'Lagos Office', is_active: true }] },
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

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

describe('HR dashboard', () => {
  it('shows company numbers, security counts and the HR menu', async () => {
    fakeServer(hrRoutes())
    renderAt('/')
    expect(await screen.findByText('Company overview')).toBeInTheDocument()
    expect(await screen.findByText('Suspicious attempts')).toBeInTheDocument()
    expect(screen.getByText('Waiting for review').previousSibling).toHaveTextContent('3')
    for (const item of ['Attendance', 'Suspicious activity', 'Employees', 'Phones', 'QR screens', 'Security settings']) {
      expect(screen.getByRole('link', { name: new RegExp(item) })).toBeInTheDocument()
    }
  })

  it('managers do not get the HR menu', async () => {
    fakeServer({
      'POST /auth/refresh': { status: 200, body: tokens() },
      'GET /auth/me': { status: 200, body: { ...hrUser, role: 'MANAGER' } },
      'GET /manager/attendance': { status: 200, body: team },
      'GET /departments': { status: 200, body: [] },
      'GET /locations': { status: 200, body: [] },
    })
    renderAt('/settings')
    expect(await screen.findByText('Your team')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Security settings/ })).not.toBeInTheDocument()
  })
})

describe('review', () => {
  it('HR sees the real reason and can approve', async () => {
    const calls = fakeServer(hrRoutes({
      'GET /hr/review/ev1': { status: 200, body: { ...reviewItem, latitude: 6.44, longitude: 3.422, fix_age_ms: 2000,
        device_reported_at: null, app_version: '0.10.0', device_model: 'Pixel 8', device_status: 'ACTIVE',
        checks: { geofence: 'FAIL', device_check: 'PASS' }, details: { geofence: { distance_m: 1323, radius_m: 200 } },
        policy: {}, security_events: [] } },
      'POST /hr/review/ev1': { status: 200, body: {} },
    }))
    renderAt('/review')
    const row = (await screen.findByText('Chinedu Eze')).closest('tr')!
    expect(within(row).getByText('Outside the office radius')).toBeInTheDocument()
    await userEvent.click(row)
    expect(await screen.findByText('Distance to office')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled() // needs a reason first
    await userEvent.click(screen.getByRole('button', { name: /Approve/ }))
    await waitFor(() => {
      const post = calls.find((c) => c.method === 'POST' && c.path === '/hr/review/ev1')
      expect(JSON.parse(post!.init.body as string).decision).toBe('APPROVED')
    })
  })
})

describe('settings', () => {
  it('saves only what changed', async () => {
    const calls = fakeServer(hrRoutes({
      'GET /settings/attendance-policies': { status: 200, body: { default: policy, locations: [] } },
      'PUT /settings/attendance-policies/default': { status: 200, body: policy },
    }))
    renderAt('/settings')
    const field = await screen.findByLabelText(/Worst accepted GPS accuracy/)
    await userEvent.clear(field)
    await userEvent.type(field, '80')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const put = calls.find((c) => c.method === 'PUT')
      expect(JSON.parse(put!.init.body as string)).toEqual({ max_accuracy_m: 80 })
    })
    expect(await screen.findByText(/Saved/)).toBeInTheDocument()
  })
})

describe('office QR screen', () => {
  it('asks for the screen key, then shows the code for the location', async () => {
    const calls = fakeServer({
      'POST /auth/refresh': { status: 401 },
      'GET /qr/current': { status: 200, body: { location_name: 'Lagos Office', token: 'Q1.abc.1.sig', expires_at: new Date(Date.now() + 20000).toISOString(), rotation_seconds: 30 } },
    })
    renderAt('/qr-display')
    await userEvent.type(screen.getByLabelText(/Screen key/), 'qrd_test-key')
    await userEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByText('Lagos Office')).toBeInTheDocument()
    expect(await screen.findByAltText('Attendance QR code')).toBeInTheDocument()
    const call = calls.find((c) => c.path === '/qr/current')!
    expect(new Headers(call.init.headers).get('X-Display-Key')).toBe('qrd_test-key')
    localStorage.clear()
  })
})
