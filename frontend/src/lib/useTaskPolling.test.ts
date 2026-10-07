import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { useTaskPolling } from './useTaskPolling'

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('stops polling when hidden, terminal or unmounted', async () => {
  vi.useFakeTimers()
  let hidden = false
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => hidden ? 'hidden' : 'visible')
  const load = vi.fn().mockResolvedValue(true)
  const wrapper = mount(defineComponent({ setup() { const polling = useTaskPolling(load, 1000); polling.start(); return () => null } }))
  await vi.advanceTimersByTimeAsync(1000)
  expect(load).toHaveBeenCalledTimes(1)
  hidden = true; document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(4000)
  expect(load).toHaveBeenCalledTimes(1)
  hidden = false; document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(1000)
  expect(load).toHaveBeenCalledTimes(2)
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(4000)
  expect(load).toHaveBeenCalledTimes(2)
})

it('stops after terminal state or failed load until restarted', async () => {
  vi.useFakeTimers()
  const load = vi.fn().mockResolvedValueOnce(false).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(true)
  let start!: () => void
  const wrapper = mount(defineComponent({ setup() { start = useTaskPolling(load, 1000).start; return () => null } }))
  start(); await vi.advanceTimersByTimeAsync(3000)
  expect(load).toHaveBeenCalledTimes(1)
  start(); await vi.advanceTimersByTimeAsync(3000)
  expect(load).toHaveBeenCalledTimes(2)
  start(); await vi.advanceTimersByTimeAsync(1000)
  expect(load).toHaveBeenCalledTimes(3)
  wrapper.unmount()
})
