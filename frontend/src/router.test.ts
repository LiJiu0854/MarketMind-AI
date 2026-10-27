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

it('does not replace the current user with an older session response', async () => {
  sessionStorage.setItem('marketmind_access_token', 'old-token')
  let respond!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { respond = resolve })))
  const pending = restoreSession()
  sessionStorage.setItem('marketmind_access_token', 'new-token')
  currentUser.value = {
    id: 2, email: 'new@example.com', full_name: 'New User', role: 'admin', is_active: true,
    created_at: '', updated_at: '',
  }
  respond(new Response(JSON.stringify({
    id: 1, email: 'old@example.com', full_name: 'Old User', role: 'analyst', is_active: true,
    created_at: '', updated_at: '',
  }), { status: 200 }))
  expect(await pending).toBe(false)
  expect(currentUser.value?.id).toBe(2)
})
