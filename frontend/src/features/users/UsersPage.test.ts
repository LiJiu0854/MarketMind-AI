import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { currentUser } from '../../lib/session'
import UsersPage from './UsersPage.vue'

afterEach(() => { vi.unstubAllGlobals(); currentUser.value = null })

it('reuses key for same create attempt and rotates it when input changes', async () => {
  currentUser.value = { id: 1, email: 'admin@example.com', full_name: 'Admin', role: 'admin', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (url: string) => url.includes('/users?')
    ? new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }))
    : Promise.reject(new TypeError('network timeout')))
  vi.stubGlobal('fetch', fetchMock)
  const createCalls = () => fetchMock.mock.calls.filter((call) => String(call[0]).endsWith('/users'))
  const wrapper = mount(UsersPage)
  await vi.waitFor(() => expect(wrapper.text()).toContain('暂无用户'))
  await wrapper.get('input[name="email"]').setValue('new@example.com')
  await wrapper.get('input[name="full_name"]').setValue('新人')
  await wrapper.get('input[name="password"]').setValue('secure-password')
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(createCalls().length).toBe(1))
  await vi.waitFor(() => expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined())
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(createCalls().length).toBe(2))
  await vi.waitFor(() => expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined())
  await wrapper.get('input[name="email"]').setValue('changed@example.com')
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(createCalls().length).toBe(3))
  const keys = createCalls().map((call) => new Headers((call[1] as RequestInit).headers).get('Idempotency-Key'))
  expect(keys[0]).toBe(keys[1])
  expect(keys[2]).not.toBe(keys[1])
})

it('edits user name and email through the existing PATCH endpoint', async () => {
  currentUser.value = { id: 1, email: 'admin@example.com', full_name: 'Admin', role: 'admin', is_active: true, created_at: '', updated_at: '' }
  const member = { id: 2, email: 'old@example.com', full_name: '旧姓名', role: 'operator', is_active: true, created_at: '', updated_at: '' }
  const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => new Response(JSON.stringify(
    init?.method === 'PATCH' ? member : { items: [member], total: 1, page: 1, page_size: 20 },
  )))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(UsersPage)
  await vi.waitFor(() => expect(wrapper.text()).toContain('旧姓名'))
  await wrapper.get('button[data-test="edit-user"]').trigger('click')
  await wrapper.get('input[name="edit_full_name"]').setValue('新姓名')
  await wrapper.get('input[name="edit_email"]').setValue('new@example.com')
  await wrapper.get('form[data-test="edit-form"]').trigger('submit')
  await vi.waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true))
  const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
  expect(patch?.[0]).toBe('/api/v1/users/2')
  expect(JSON.parse(String(patch?.[1].body))).toMatchObject({ full_name: '新姓名', email: 'new@example.com' })
})
