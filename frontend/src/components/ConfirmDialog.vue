<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
const props = defineProps<{ open: boolean; title: string; message: string; busy?: boolean }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
const cancelButton = ref<HTMLButtonElement | null>(null)
const confirmButton = ref<HTMLButtonElement | null>(null)
let previousFocus: HTMLElement | null = null
watch(() => props.open, async (open) => {
  if (open) { previousFocus = document.activeElement as HTMLElement | null; await nextTick(); cancelButton.value?.focus() }
  else { previousFocus?.focus(); previousFocus = null }
})
onUnmounted(() => previousFocus?.focus())
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('cancel')
  if (event.key !== 'Tab') return
  const first = cancelButton.value
  const last = confirmButton.value
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
</script>
<template>
  <div v-if="open" class="dialog-backdrop" @click.self="emit('cancel')">
    <section class="dialog-card" role="alertdialog" aria-modal="true" :aria-label="title" @keydown="onKeydown">
      <h2>{{ title }}</h2><p>{{ message }}</p>
      <div class="dialog-actions"><button ref="cancelButton" type="button" class="button ghost" @click="emit('cancel')">取消</button><button ref="confirmButton" type="button" class="button danger" :disabled="busy" @click="emit('confirm')">{{ busy ? '处理中…' : '确认' }}</button></div>
    </section>
  </div>
</template>
