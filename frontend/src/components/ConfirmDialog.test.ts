import { mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import ConfirmDialog from './ConfirmDialog.vue'

it('moves focus into the dialog, closes on Escape and restores focus', async () => {
  const previous = document.createElement('button')
  document.body.appendChild(previous)
  previous.focus()
  const wrapper = mount(ConfirmDialog, { props: { open: false, title: '停用', message: '确认吗？' }, attachTo: document.body })
  await wrapper.setProps({ open: true })
  await vi.waitFor(() => expect(document.activeElement).toBe(wrapper.get('[role="alertdialog"] .button.ghost').element))
  await wrapper.get('[role="alertdialog"]').trigger('keydown', { key: 'Escape' })
  expect(wrapper.emitted('cancel')).toHaveLength(1)
  await wrapper.setProps({ open: false })
  expect(document.activeElement).toBe(previous)
  wrapper.unmount(); previous.remove()
})
