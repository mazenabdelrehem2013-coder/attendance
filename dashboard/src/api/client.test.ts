import { afterEach, describe, expect, it, vi } from 'vitest'

import { fakeServer, tokens } from '../test/fakeServer'
import { apiGet, ApiError, setAccessToken, setSessionExpiredHandler } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
  setSessionExpiredHandler(null)
})

describe('api client', () => {
  it('sends the access token', async () => {
    const calls = fakeServer({ 'GET /x': { status: 200, body: { ok: true } } })
    setAccessToken('abc')
    await apiGet('/x')
    expect(new Headers(calls[0].init.headers).get('Authorization')).toBe('Bearer abc')
  })

  it('renews an expired token once and repeats the request', async () => {
    let first = true
    const calls = fakeServer({
      'GET /x': () => (first ? ((first = false), { status: 401 }) : { status: 200, body: { ok: 1 } }),
      'POST /auth/refresh': { status: 200, body: tokens() },
    })
    expect(await apiGet('/x')).toEqual({ ok: 1 })
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(['GET /x', 'POST /auth/refresh', 'GET /x'])
  })

  it('only one renewal for several requests at once', async () => {
    const seen = new Set<string>()
    const calls = fakeServer({
      'GET /a': () => (seen.has('a') ? { status: 200 } : (seen.add('a'), { status: 401 })),
      'GET /b': () => (seen.has('b') ? { status: 200 } : (seen.add('b'), { status: 401 })),
      'POST /auth/refresh': { status: 200, body: tokens() },
    })
    await Promise.all([apiGet('/a'), apiGet('/b')])
    expect(calls.filter((c) => c.path === '/auth/refresh')).toHaveLength(1)
  })

  it('ends the session when renewal fails', async () => {
    const expired = vi.fn()
    setSessionExpiredHandler(expired)
    fakeServer({ 'GET /x': { status: 401 }, 'POST /auth/refresh': { status: 401 } })
    await expect(apiGet('/x')).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
    expect(expired).toHaveBeenCalledOnce()
  })

  it('passes the server error message through', async () => {
    fakeServer({ 'GET /x': { status: 403, body: { error: { code: 'FORBIDDEN', message: 'You do not have permission to do this.' } } } })
    await expect(apiGet('/x')).rejects.toEqual(new ApiError(403, 'FORBIDDEN', 'You do not have permission to do this.'))
  })

  it('network failure gives a clear message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(apiGet('/x')).rejects.toMatchObject({ code: 'NETWORK' })
  })
})
