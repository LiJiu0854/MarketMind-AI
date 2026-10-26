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

it('keeps a pending action open and traps focus while busy', async () => {
  const previous = document.createElement('button')
  document.body.appendChild(previous)
  previous.focus()
  const wrapper = mount(ConfirmDialog, { props: { open: false, title: '停用', message: '确认吗？' }, attachTo: document.body })
  await wrapper.setProps({ open: true })
  const cancel = wrapper.get('[role="alertdialog"] .button.ghost')
  await vi.waitFor(() => expect(document.activeElement).toBe(cancel.element))
  const confirm = wrapper.get('[role="alertdialog"] .button.danger').element as HTMLButtonElement
  confirm.focus()
  await wrapper.setProps({ busy: true })
  await vi.waitFor(() => expect(document.activeElement).toBe(cancel.element))
  expect(cancel.attributes('aria-disabled')).toBe('true')
  await wrapper.get('[role="alertdialog"]').trigger('keydown', { key: 'Escape' })
  await wrapper.get('.dialog-backdrop').trigger('click')
  await cancel.trigger('click')
  expect(wrapper.emitted('cancel')).toBeUndefined()
  const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
  wrapper.get('[role="alertdialog"]').element.dispatchEvent(tab)
  expect(tab.defaultPrevented).toBe(true)
  expect(document.activeElement).toBe(cancel.element)
  await wrapper.setProps({ busy: false })
  await wrapper.get('[role="alertdialog"]').trigger('keydown', { key: 'Escape' })
  expect(wrapper.emitted('cancel')).toHaveLength(1)
  wrapper.unmount(); previous.remove()
})
