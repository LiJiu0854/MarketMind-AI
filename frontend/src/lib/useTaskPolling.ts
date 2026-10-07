import { onMounted, onUnmounted } from 'vue'

export function useTaskPolling(load: () => Promise<boolean>, intervalMs = 3000, onError?: (error: unknown) => void) {
  let active = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let inFlight = false
  let disposed = false
  function clearTimer() { if (timer) clearTimeout(timer); timer = undefined }
  function stop() { active = false; clearTimer() }
  function schedule() {
    clearTimer()
    if (!active || disposed || document.visibilityState === 'hidden' || inFlight) return
    timer = setTimeout(async () => {
      timer = undefined
      if (!active || disposed || document.visibilityState === 'hidden') return
      inFlight = true
      try { if (!await load()) stop() }
      catch (error) { onError?.(error); stop() }
      finally { inFlight = false; schedule() }
    }, intervalMs)
  }
  function start() { if (disposed) return; active = true; schedule() }
  function visibilityChanged() { if (document.visibilityState === 'hidden') clearTimer(); else schedule() }
  onMounted(() => document.addEventListener('visibilitychange', visibilityChanged))
  onUnmounted(() => { disposed = true; stop(); document.removeEventListener('visibilitychange', visibilityChanged) })
  return { start, stop }
}
