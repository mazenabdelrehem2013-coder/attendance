import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { setAccessToken } from './api/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { fakeServer, manager, team, tokens } from './test/fakeServer'

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

const monthly = {
  title: 'Monthly attendance report', date_from: '2026-10-01', date_to: '2026-10-31', generated_at: '2026-10-12T09:00:00Z',
  rows: [{
    employee_id: 'a', employee: 'Chinedu Eze', employee_code: 'EMP-0101', department: 'Sales', manager: 'Tunde Bakare',
    location: 'Lagos Office', working_days: 4, present_days: 3, late_days: 1, absent_days: 1, pending_review_days: 0,
    leave_days: 1, holiday_days: 1, early_departure_days: 1, missing_checkout_days: 1, average_check_in: '09:12',
    average_check_out: '17:30', average_worked_minutes: 492, total_worked_minutes: 985, attendance_rate: 0.75,
  }],
  totals: { employees: 1, working_days: 4, present_days: 3, late_days: 1, absent_days: 1, attendance_rate: 0.75 },
  by_location: [], by_department: [], by_manager: [],
}

it('a manager can run the monthly report for their team', async () => {
  const calls = fakeServer({
    'POST /auth/refresh': { status: 200, body: tokens() },
    'GET /auth/me': { status: 200, body: manager },
    'GET /manager/attendance': { status: 200, body: team },
    'GET /departments': { status: 200, body: [] },
    'GET /locations': { status: 200, body: [] },
    'GET /reports/daily': { status: 200, body: { title: 'Daily', rows: [], totals: {} } },
    'GET /reports/monthly': { status: 200, body: monthly },
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/reports']}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText(/Reports contain only your own team/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Download Excel/ })).toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('Report'))
  await userEvent.click(await screen.findByRole('option', { name: 'Monthly report' }))
  expect(await screen.findByText('Chinedu Eze')).toBeInTheDocument()
  expect(screen.getAllByText('75%').length).toBeGreaterThan(0)
  expect(screen.getByText('09:12')).toBeInTheDocument()
  await waitFor(() => expect(calls.some((c) => c.path === '/reports/monthly' && c.url.searchParams.get('month'))).toBe(true))
})


it('Download Excel sends the chosen report and filters', async () => {
  const calls = fakeServer({
    'POST /auth/refresh': { status: 200, body: tokens() },
    'GET /auth/me': { status: 200, body: manager },
    'GET /manager/attendance': { status: 200, body: team },
    'GET /departments': { status: 200, body: [] },
    'GET /locations': { status: 200, body: [] },
    'GET /reports/daily': { status: 200, body: { title: 'Daily', rows: [], totals: {} } },
    'POST /reports/export/excel': { status: 200, body: {} },
  })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/reports']}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  )
  await userEvent.click(await screen.findByRole('button', { name: /Download Excel/ }))
  await waitFor(() => {
    const post = calls.find((c) => c.path === '/reports/export/excel')
    expect(JSON.parse(post!.init.body as string)).toMatchObject({ report: 'daily' })
  })
})
