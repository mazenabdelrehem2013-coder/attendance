import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from './api/client'
import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { fakeServer, manager, team, tokens } from './test/fakeServer'

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const loggedInManager = {
  'POST /auth/refresh': { status: 200, body: tokens() },
  'GET /auth/me': { status: 200, body: manager },
  'GET /manager/attendance': { status: 200, body: team },
  'GET /departments': { status: 200, body: [{ id: 'd1', name: 'Sales', is_active: true }] },
  'GET /locations': { status: 200, body: [{ id: 'l1', name: 'Lagos Office', is_active: true }] },
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
})

describe('login', () => {
  it('shows the login page when there is no session', async () => {
    fakeServer({ 'POST /auth/refresh': { status: 401, body: { error: { code: 'INVALID_SESSION', message: 'x' } } } })
    renderApp()
    expect(await screen.findByText('Attendance Dashboard')).toBeInTheDocument()
  })

  it('shows the server message for a wrong password', async () => {
    fakeServer({
      'POST /auth/refresh': { status: 401 },
      'POST /auth/login': { status: 401, body: { error: { code: 'INVALID_CREDENTIALS', message: 'Invalid login details.' } } },
    })
    renderApp()
    await userEvent.type(await screen.findByLabelText(/Email or employee ID/), 'manager.lagos@example.com')
    await userEvent.type(screen.getByLabelText(/^Password/), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('Invalid login details.')).toBeInTheDocument()
  })

  it('logs in as WEB so the refresh token stays in an HttpOnly cookie', async () => {
    const calls = fakeServer({ ...loggedInManager, 'POST /auth/refresh': { status: 401 }, 'POST /auth/login': { status: 200, body: tokens() } })
    renderApp()
    await userEvent.type(await screen.findByLabelText(/Email or employee ID/), 'manager.lagos@example.com')
    await userEvent.type(screen.getByLabelText(/^Password/), 'pw')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('Your team')).toBeInTheDocument()
    const login = calls.find((c) => c.path === '/auth/login')!
    expect(JSON.parse(login.init.body as string).client_type).toBe('WEB')
  })

  it('employees are sent to the mobile app', async () => {
    fakeServer({
      'POST /auth/refresh': { status: 200, body: tokens() },
      'GET /auth/me': { status: 200, body: { ...manager, role: 'EMPLOYEE' } },
    })
    renderApp()
    expect(await screen.findByText(/Please use the mobile app/)).toBeInTheDocument()
  })
})

describe('manager dashboard', () => {
  it('shows the summary and the team table', async () => {
    fakeServer(loggedInManager)
    renderApp()
    expect(await screen.findByText('Chinedu Eze')).toBeInTheDocument()
    expect(screen.getByTestId('card-total_employees')).toHaveTextContent('3')
    expect(screen.getByTestId('card-present')).toHaveTextContent('2')
    expect(screen.getByTestId('card-absent')).toHaveTextContent('1')
    expect(screen.getByTestId('card-suspicious')).toHaveTextContent('1')

    const funmi = screen.getByText('Funmi Adeyemi').closest('tr')!
    expect(within(funmi).getByText('Late')).toBeInTheDocument()
    expect(within(funmi).getByText('Pending review')).toBeInTheDocument()
    expect(within(funmi).getByText('09:40')).toBeInTheDocument() // 08:40 UTC = 09:40 Lagos

    const bisi = screen.getByText('Bisi Ogunleye').closest('tr')!
    expect(within(bisi).getByText('Absent')).toBeInTheDocument()
  })

  it('clicking a summary card filters by that status', async () => {
    const calls = fakeServer(loggedInManager)
    renderApp()
    await screen.findByText('Chinedu Eze')
    await userEvent.click(screen.getByText('Absent', { selector: 'p' }))
    await waitFor(() => {
      const last = calls.filter((c) => c.path === '/manager/attendance').at(-1)!
      expect(last.url.searchParams.getAll('status')).toEqual(['ABSENT'])
    })
  })

  it('an expired session returns to the login page with an explanation', async () => {
    let refreshes = 0
    fakeServer({
      ...loggedInManager,
      'POST /auth/refresh': () => (refreshes++ === 0 ? { status: 200, body: tokens() } : { status: 401 }),
      'GET /manager/attendance': { status: 401, body: { error: { code: 'INVALID_TOKEN', message: 'x' } } },
    })
    renderApp()
    expect(await screen.findByText('Your session has expired. Please log in again.')).toBeInTheDocument()
  })
})
