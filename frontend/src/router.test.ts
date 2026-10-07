import { afterEach, expect, it, vi } from 'vitest'
import { currentUser, restoreSession } from './lib/session'

afterEach(() => {
  sessionStorage.clear()
  currentUser.value = null
  vi.unstubAllGlobals()
})

it('restores only a valid session and removes an expired token', async () => {
  sessionStorage.setItem('marketmind_access_token', 'expired')
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }))
  vi.stubGlobal('fetch', fetchMock)
  expect(await restoreSession()).toBe(false)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/auth/me')
  expect(sessionStorage.getItem('marketmind_access_token')).toBeNull()
  expect(currentUser.value).toBeNull()
})

it('does not treat 403 as an expired token', async () => {
  sessionStorage.setItem('marketmind_access_token', 'valid')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })))
  await expect(restoreSession()).rejects.toMatchObject({ status: 403 })
  expect(sessionStorage.getItem('marketmind_access_token')).toBe('valid')
})
