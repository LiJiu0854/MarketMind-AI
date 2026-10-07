<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { useTaskPolling } from '../../lib/useTaskPolling'
import StatusBadge from '../../components/StatusBadge.vue'
import { listSemanticReviews, startSemanticReview } from './api'
import type { SemanticReview } from './types'

const props = defineProps<{ productId: number }>()
const items = ref<SemanticReview[]>([])
const page = ref(1)
const total = ref(0)
const selected = ref<SemanticReview | null>(null)
const busy = ref(false)
const error = ref('')
const canStart = computed(() => currentUser.value?.role === 'admin' || currentUser.value?.role === 'operator')
const polling = useTaskPolling(async () => {
  const result = await listSemanticReviews(props.productId, page.value)
  items.value = result.items; total.value = result.total
  if (selected.value) selected.value = result.items.find((item) => item.id === selected.value?.id) || selected.value
  return result.items.some((item) => item.status === 'pending' || item.status === 'running')
}, 3000, (cause) => { error.value = cause instanceof Error ? cause.message : '审核状态读取失败，请重试' })
async function load() {
  error.value = ''
  try {
    const result = await listSemanticReviews(props.productId, page.value)
    items.value = result.items; total.value = result.total
    selected.value = null
    if (result.items.some((item) => item.status === 'pending' || item.status === 'running')) polling.start()
    else polling.stop()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '语义审核读取失败'; polling.stop() }
}
async function start() {
  if (!canStart.value || busy.value) return
  busy.value = true; error.value = ''
  try { await startSemanticReview(props.productId); await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '审核发起失败；请检查模型配置与服务状态' }
  finally { busy.value = false }
}
onMounted(() => { void load() })
</script>
<template><section class="panel"><div class="panel-heading"><div><p class="eyebrow">AI LISTING REVIEW</p><h2>语义审核</h2></div><button v-if="canStart" type="button" class="button primary" :disabled="busy" @click="start">{{ busy ? '正在提交…' : '发起语义审核' }}</button></div><p class="muted">审核使用后端配置的模型异步生成，结果与发起时的商品快照分开保存。</p><p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="load">重试读取</button></p><p v-if="!items.length" class="empty">暂无语义审核</p><div v-else class="table-wrap"><table><thead><tr><th>审核 ID</th><th>状态</th><th>分数</th><th>模型</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td>#{{ item.id }}</td><td><StatusBadge :status="item.status" /></td><td>{{ item.score ?? '—' }}</td><td>{{ item.model }}</td><td><button type="button" class="text-button" @click="selected = item">查看结果</button></td></tr></tbody></table></div><div class="pager"><button type="button" class="button ghost" :disabled="page <= 1" @click="page--; load()">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 条</span><button data-test="next-review-page" type="button" class="button ghost" :disabled="page * 20 >= total" @click="page++; load()">下一页</button></div><div v-if="selected" class="source-card"><div class="panel-heading"><h3>审核 #{{ selected.id }}</h3><button type="button" class="text-button" @click="selected = null">收起</button></div><StatusBadge :status="selected.status" /><p v-if="selected.error_message" class="error">{{ selected.error_message }}</p><p v-if="selected.summary" class="pre-wrap">{{ selected.summary }}</p><p class="muted">审核快照：{{ selected.product_snapshot.title }}（{{ selected.product_snapshot.sku }}）</p><dl v-if="selected.dimension_scores" class="detail-grid"><div v-for="[key, value] in Object.entries(selected.dimension_scores)" :key="key" class="kv"><dt>{{ key }}</dt><dd>{{ value }}</dd></div></dl><div v-for="issue in selected.issues || []" :key="`${issue.field}-${issue.message}`" class="source-card"><strong>{{ issue.field }} · {{ issue.message }}</strong><p>{{ issue.suggestion }}</p></div><div v-if="selected.rewrite"><h3>建议改写</h3><p>{{ selected.rewrite.title }}</p><p class="pre-wrap">{{ selected.rewrite.description }}</p><ol><li v-for="(bullet, index) in selected.rewrite.bullet_points" :key="index">{{ bullet }}</li></ol></div><small v-if="selected.total_tokens !== null">模型用量：{{ selected.total_tokens }} tokens</small></div></section></template>
