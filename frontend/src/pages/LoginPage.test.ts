import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage.vue'

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear() })

it('submits the OAuth form and disables duplicate submissions', async () => {
  let release!: (response: Response) => void
  const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { release = resolve }))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(LoginPage)
  await wrapper.get('input[type="email"]').setValue('admin@example.com')
  await wrapper.get('input[type="password"]').setValue('secret123456')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  expect(url).toBe('/api/v1/auth/token')
  expect(init.body).toBeInstanceOf(URLSearchParams)
  expect((init.body as URLSearchParams).get('username')).toBe('admin@example.com')
  expect((init.body as URLSearchParams).get('password')).toBe('secret123456')
  release(new Response('{}', { status: 401 }))
  await vi.waitFor(() => expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined())
})
