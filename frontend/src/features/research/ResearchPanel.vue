<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { currentUser } from '../../lib/session'
import { useTaskPolling } from '../../lib/useTaskPolling'
import StatusBadge from '../../components/StatusBadge.vue'
import { listKnowledgeBases } from '../knowledge/api'
import type { KnowledgeBase } from '../knowledge/types'
import { createResearch, listResearchRuns } from './api'
import type { ResearchRun } from './types'

const props = defineProps<{ productId: number }>()
const router = useRouter()
const items = ref<ResearchRun[]>([])
const bases = ref<KnowledgeBase[]>([])
const basePage = ref(0)
const baseTotal = ref(0)
const loadingBases = ref(false)
const total = ref(0)
const page = ref(1)
const goal = ref('')
const selectedIds = ref<number[]>([])
const busy = ref(false)
const error = ref('')
const canStart = computed(() => currentUser.value?.role === 'admin' || currentUser.value?.role === 'operator')
const polling = useTaskPolling(async () => {
  const result = await listResearchRuns(props.productId, page.value)
  items.value = result.items; total.value = result.total
  return result.items.some((item) => item.status === 'pending' || item.status === 'running')
}, 3000, (cause) => { error.value = cause instanceof Error ? cause.message : '研究状态读取失败，请重试' })
async function load() {
  try {
    const result = await listResearchRuns(props.productId, page.value)
    items.value = result.items; total.value = result.total
    if (result.items.some((item) => item.status === 'pending' || item.status === 'running')) polling.start()
    else polling.stop()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '研究历史读取失败'; polling.stop() }
}
async function start() {
  if (!canStart.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const created = await createResearch(props.productId, goal.value, selectedIds.value)
    await router.push(`/products/${props.productId}/research-runs/${created.run_id}`)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '研究发起失败' }
  finally { busy.value = false }
}
async function loadMoreBases() {
  if (loadingBases.value || (basePage.value > 0 && bases.value.length >= baseTotal.value)) return
  loadingBases.value = true
  try {
    const result = await listKnowledgeBases(basePage.value + 1)
    bases.value.push(...result.items)
    basePage.value = result.page; baseTotal.value = result.total
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '知识库读取失败' }
  finally { loadingBases.value = false }
}
onMounted(async () => {
  await load()
  if (canStart.value) await loadMoreBases()
})
</script>
<template><section class="panel"><div class="panel-heading"><div><p class="eyebrow">CONTROLLED RESEARCH</p><h2>受控研究</h2></div><span class="count-pill">{{ total }} 次研究</span></div><p class="muted">研究记录、证据与人工审核均从服务端读取，不在页面生成结论。</p><p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="load">重新读取</button></p>
  <form v-if="canStart" class="form-stack" @submit.prevent="start"><label>研究目标<textarea v-model="goal" required maxlength="500" placeholder="例如：分析该商品的定位及证据充分性" /></label><fieldset class="source-card"><legend>选择 1–3 个知识库</legend><p v-if="!bases.length" class="muted">暂无可选知识库，请先准备资料。</p><label v-for="base in bases" :key="base.id" style="display:block;margin:8px 0"><input v-model="selectedIds" type="checkbox" :value="base.id" :disabled="!selectedIds.includes(base.id) && selectedIds.length >= 3" /> {{ base.name }}</label><button v-if="bases.length < baseTotal" data-test="more-bases" type="button" class="button ghost" :disabled="loadingBases" @click="loadMoreBases">{{ loadingBases ? '读取中…' : '加载更多知识库' }}</button></fieldset><button type="submit" class="button primary" :disabled="busy || !bases.length">{{ busy ? '正在提交…' : '发起研究' }}</button></form>
  <h3 style="margin-top:26px">研究历史</h3><p v-if="!items.length" class="empty">暂无研究记录</p><div v-else class="table-wrap"><table><thead><tr><th>ID</th><th>目标</th><th>状态</th><th>审核</th><th>操作</th></tr></thead><tbody><tr v-for="run in items" :key="run.id"><td>#{{ run.id }}</td><td>{{ run.goal }}</td><td><StatusBadge :status="run.status" /></td><td><StatusBadge :status="run.review_status" /></td><td><RouterLink :to="`/products/${productId}/research-runs/${run.id}`" class="text-button">查看证据 →</RouterLink></td></tr></tbody></table></div><div class="pager"><button type="button" class="button ghost" :disabled="page <= 1" @click="page--; load()">上一页</button><span>第 {{ page }} 页</span><button type="button" class="button ghost" :disabled="page * 20 >= total" @click="page++; load()">下一页</button></div></section></template>
