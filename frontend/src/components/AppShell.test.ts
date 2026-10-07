import { mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import { currentUser } from '../lib/session'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppShell from './AppShell.vue'

afterEach(() => { currentUser.value = null })

it.each(['analyst', 'operator'] as const)('hides user management from %s navigation', (role) => {
  currentUser.value = { id: 2, email: 'member@example.com', full_name: '成员', role, is_active: true, created_at: '', updated_at: '' }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  const wrapper = mount(AppShell, { global: { plugins: [router], stubs: ['RouterView'] } })
  expect(wrapper.text()).not.toContain('用户管理')
  expect(wrapper.text()).toContain('商品运营')
})
