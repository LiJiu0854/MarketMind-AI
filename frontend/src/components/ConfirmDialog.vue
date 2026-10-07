<script setup lang="ts">
defineProps<{ open: boolean; title: string; message: string; busy?: boolean }>()
const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>
<template>
  <div v-if="open" class="dialog-backdrop" @click.self="emit('cancel')">
    <section class="dialog-card" role="alertdialog" aria-modal="true" :aria-label="title" @keydown.esc="emit('cancel')">
      <h2>{{ title }}</h2><p>{{ message }}</p>
      <div class="dialog-actions"><button type="button" class="button ghost" @click="emit('cancel')">取消</button><button type="button" class="button danger" :disabled="busy" @click="emit('confirm')">{{ busy ? '处理中…' : '确认' }}</button></div>
    </section>
  </div>
</template>
