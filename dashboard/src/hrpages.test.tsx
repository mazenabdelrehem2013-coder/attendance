/** Phase 17: the HR pages that had no tests yet (found with the coverage report). */
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
const employee = {
  id: 'e1', user_id: 'u1', employee_code: 'EMP-0101', full_name: 'Chinedu Eze', email: 'chinedu@example.com', phone: null,
  role: 'EMPLOYEE', is_active: true, employment_status: 'ACTIVE', hire_date: null, department: { id: 'd1', name: 'Sales' },
  manager: null, work_schedule_id: null, locations: [{ location_id: 'l1', name: 'Lagos Office', is_primary: true }],
}
const lagos = { id: 'l1', branch_id: 'b1', name: 'Lagos Office', code: 'LOS', address: null, latitude: '6.428100',
  longitude: '3.421900', radius_m: 200, timezone: 'Africa/Lagos', work_schedule_id: null, is_active: true }

function routes(extra: Record<string, unknown> = {}, user: object = hrUser) {
  return {
    'POST /auth/refresh': { status: 200, body: tokens(user as never) },
    'GET /auth/me': { status: 200, body: user },
    'GET /hr/review': { status: 200, body: { items: [], total: 0 } },
    'GET /devices': { status: 200, body: { items: [], total: 0, page: 1, page_size: 1 } },
    'GET /notifications': { status: 200, body: { items: [], unread: 0 } },
    'GET /security/alerts': { status: 200, body: { items: [], total: 0 } },
    'GET /employees': { status: 200, body: { items: [employee], total: 1, page: 1, page_size: 200 } },
    'GET /departments': { status: 200, body: [{ id: 'd1', name: 'Sales', code: 'SAL', is_active: true }] },
    'GET /locations': { status: 200, body: [lagos] },
    'GET /managers': { status: 200, body: [] },
    'GET /branches': { status: 200, body: [{ id: 'b1', name: 'Main', code: 'MAIN', is_active: true }] },
    'GET /work-schedules': { status: 200, body: [] },
    'GET /holidays': { status: 200, body: [] },
    'GET /leave': { status: 200, body: [] },
    'GET /qr-displays': { status: 200, body: [] },
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

const body = (calls: { method: string; path: string; init: RequestInit }[], method: string, path: string) =>
  JSON.parse(calls.find((c) => c.method === method && c.path === path)!.init.body as string)

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  setAccessToken(null)
})

describe('Employees', () => {
  it('lists employees and resets a password (shown once)', async () => {
    fakeServer(routes({ 'POST /employees/e1/reset-password': { status: 200, body: { temporary_password: 'Temp-Pass-12345' } } }))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderAt('/employees')
    expect(await screen.findByText('Chinedu Eze', {}, { timeout: 5000 })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(await screen.findByLabelText('temporary password')).toHaveTextContent('Temp-Pass-12345')
  })

  it('a new employee needs a check-in location', async () => {
    const calls = fakeServer(routes())
    renderAt('/employees')
    await userEvent.click(await screen.findByRole('button', { name: 'Add employee' }))
    await userEvent.type(screen.getByLabelText(/Full name/), 'Ada Obi')
    await userEvent.type(screen.getByLabelText(/Employee ID/), 'EMP-0200')
    await userEvent.type(screen.getByLabelText(/^Email/), 'ada@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText(/Choose at least one location/)).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/employees')).toBe(false)
  })

  it('edits an employee', async () => {
    const calls = fakeServer(routes({ 'PUT /employees/e1': { status: 200, body: employee } }))
    renderAt('/employees')
    await userEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const name = screen.getByLabelText(/Full name/)
    await userEvent.clear(name)
    await userEvent.type(name, 'Chinedu A. Eze')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
    expect(body(calls, 'PUT', '/employees/e1')).toMatchObject({ full_name: 'Chinedu A. Eze', department_id: 'd1' })
  })
})

describe('Locations & departments', () => {
  it('adds a location with numbers for the coordinates', async () => {
    const calls = fakeServer(routes({ 'POST /locations': { status: 201, body: lagos } }))
    renderAt('/organization')
    await userEvent.click(await screen.findByRole('button', { name: 'Add location' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/^Name/), 'Abuja Office')
    await userEvent.type(within(dialog).getByLabelText(/^Code/), 'ABV')
    await userEvent.click(within(dialog).getByRole('combobox', { name: /Branch/ }))
    await userEvent.click(await screen.findByRole('option', { name: 'Main' }))
    await userEvent.type(within(dialog).getByLabelText(/^Latitude/), '9.056300')
    await userEvent.type(within(dialog).getByLabelText(/^Longitude/), '7.498500')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/locations')).toBe(true))
    expect(body(calls, 'POST', '/locations')).toMatchObject({
      name: 'Abuja Office', code: 'ABV', branch_id: 'b1', latitude: 9.0563, longitude: 7.4985, radius_m: 200,
    })
  })

  it('splits a pasted Google Maps "lat, lng" pair into both boxes', async () => {
    fakeServer(routes({}))
    renderAt('/organization')
    await userEvent.click(await screen.findByRole('button', { name: 'Add location' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByLabelText(/^Latitude/))
    await userEvent.paste('30.044420193553, 31.235711842')
    expect(within(dialog).getByLabelText(/^Latitude/)).toHaveValue('30.044420193553')
    expect(within(dialog).getByLabelText(/^Longitude/)).toHaveValue('31.235711842')
  })

  it('adds a department', async () => {
    const calls = fakeServer(routes({ 'POST /departments': { status: 201, body: {} } }))
    renderAt('/organization')
    await userEvent.click(await screen.findByRole('tab', { name: 'Departments' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Add department' }))
    await userEvent.type(screen.getByLabelText(/^Name/), 'Finance')
    await userEvent.type(screen.getByLabelText(/^Code/), 'FIN')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/departments')).toBe(true))
    expect(body(calls, 'POST', '/departments')).toEqual({ name: 'Finance', code: 'FIN' })
  })
})

describe('Holidays', () => {
  it('adds a company holiday', async () => {
    const calls = fakeServer(routes({ 'POST /holidays': { status: 201, body: {} } }))
    renderAt('/calendar')
    await userEvent.click(await screen.findByRole('button', { name: 'Add holiday' }))
    await userEvent.type(screen.getByLabelText(/^Date/), '2026-10-01')
    await userEvent.type(screen.getByLabelText(/^Name/), 'Independence Day')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/holidays')).toBe(true))
    expect(body(calls, 'POST', '/holidays')).toEqual({ holiday_date: '2026-10-01', name: 'Independence Day', location_id: null })
  })
})

describe('QR screens', () => {
  it('adds a screen and shows its key once', async () => {
    const calls = fakeServer(routes({
      'POST /qr-displays': { status: 201, body: { id: 'q1', location_id: 'l1', location_name: 'Lagos Office',
        display_label: 'Reception', rotation_seconds: 30, is_active: true, last_heartbeat_at: null, display_key: 'KEY-abc-123' } },
    }))
    renderAt('/qr-screens')
    await userEvent.click(await screen.findByRole('button', { name: 'Add screen' }))
    await userEvent.click(screen.getByRole('combobox', { name: /Location/ }))
    await userEvent.click(await screen.findByRole('option', { name: 'Lagos Office' }))
    await userEvent.clear(screen.getByLabelText(/Screen name/))
    await userEvent.type(screen.getByLabelText(/Screen name/), 'Reception')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByLabelText('display key')).toHaveTextContent('KEY-abc-123')
    expect(body(calls, 'POST', '/qr-displays')).toEqual({ location_id: 'l1', display_label: 'Reception' })
  })
})

describe('Phones', () => {
  it('approves a waiting phone', async () => {
    const device = { id: 'p1', employee_id: 'e1', employee_name: 'Chinedu Eze', employee_code: 'EMP-0101',
      status: 'PENDING_APPROVAL', device_model: 'Pixel 8', os_version: 'Android 15', app_version: '1.0.0',
      requested_at: '2026-10-05T07:00:00Z', approved_at: null, decision_note: null, last_seen_at: null }
    const calls = fakeServer(routes({
      'GET /devices': { status: 200, body: { items: [device], total: 1, page: 1, page_size: 200 } },
      'POST /devices/p1/approve': { status: 200, body: { ...device, status: 'ACTIVE' } },
    }))
    renderAt('/phones')
    expect(await screen.findByText('Pixel 8')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/devices/p1/approve')).toBe(true))
  })
})

describe('Change password', () => {
  it('checks the new password before sending it', async () => {
    const calls = fakeServer(routes({}, { ...hrUser, must_change_password: true }))
    renderAt('/')
    await userEvent.type(await screen.findByLabelText(/Temporary password/), 'Temp-Pass-12345')
    await userEvent.type(screen.getByLabelText(/^New password/), 'Short1')
    await userEvent.type(screen.getByLabelText(/Repeat new password/), 'Short1')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByText(/at least 10 characters/)).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/auth/change-password')).toBe(false)
  })

  it('saves a matching new password', async () => {
    const calls = fakeServer(routes({
      'POST /auth/change-password': { status: 200, body: tokens(hrUser as never) },
    }, { ...hrUser, must_change_password: true }))
    renderAt('/')
    await userEvent.type(await screen.findByLabelText(/Temporary password/), 'Temp-Pass-12345')
    await userEvent.type(screen.getByLabelText(/^New password/), 'My-Own-Password-9')
    await userEvent.type(screen.getByLabelText(/Repeat new password/), 'My-Own-Password-9')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    await waitFor(() => expect(calls.some((c) => c.path === '/auth/change-password')).toBe(true))
    expect(body(calls, 'POST', '/auth/change-password')).toEqual({
      current_password: 'Temp-Pass-12345', new_password: 'My-Own-Password-9', client_type: 'WEB',
    })
  })
})
