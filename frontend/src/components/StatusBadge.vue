<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = {
  pending: '待处理', processing: '处理中', running: '运行中', ready: '已就绪',
  success: '已完成', failure: '失败', refused: '拒答',
  not_ready: '未就绪', not_reviewable: '不可审核', pending_review: '待审核',
  approved: '已批准', rejected: '已驳回',
}
</script>
<template><span class="status-badge" :class="`status-${status}`">{{ labels[status] || status }}</span></template>
