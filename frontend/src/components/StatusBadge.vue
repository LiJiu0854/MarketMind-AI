<script setup lang="ts">
defineProps<{ status: string }>()
</script>
<template><span class="status-badge" :class="`status-${status}`">{{ status }}</span></template>
