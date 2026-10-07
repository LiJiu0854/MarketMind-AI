<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { useTaskPolling } from '../../lib/useTaskPolling'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { downloadResearchRun, getResearchRun, reviewResearchRun } from './api'
import type { ResearchRun } from './types'

const props = defineProps<{ productId: string; runId: string }>()
const productId = Number(props.productId)
const runId = Number(props.runId)
const run = ref<ResearchRun | null>(null)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const comment = ref('')
const pendingDecision = ref<'approved' | 'rejected' | null>(null)
const canReview = computed(() => currentUser.value?.role === 'admin' && run.value?.review_status === 'pending_review')
const canDownload = computed(() => run.value?.review_status === 'approved')
const sourceMap = computed(() => new Map((run.value?.evidence || []).map((source) => [source.source_id, source])))
const actionLabels = { read_product: '读取商品快照', search_knowledge: '检索知识库', finish: '结束检索' }
const polling = useTaskPolling(async () => {
  run.value = await getResearchRun(productId, runId)
  return run.value.status === 'pending' || run.value.status === 'running'
}, 3000, (cause) => { error.value = cause instanceof Error ? cause.message : '研究状态读取失败，请重试' })
async function load() {
  error.value = ''
  try {
    run.value = await getResearchRun(productId, runId)
    if (run.value.status === 'pending' || run.value.status === 'running') polling.start()
    else polling.stop()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '研究读取失败'; polling.stop() }
}
async function review() {
  if (!canReview.value || !pendingDecision.value || busy.value) return
  if (pendingDecision.value === 'rejected' && !comment.value.trim()) { error.value = '驳回时必须填写意见'; pendingDecision.value = null; return }
  busy.value = true; error.value = ''
  try {
    await reviewResearchRun(productId, runId, pendingDecision.value, comment.value)
    pendingDecision.value = null; comment.value = ''; notice.value = '审核已记录'
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '审核失败，请重新读取后重试'; pendingDecision.value = null }
  finally { busy.value = false }
}
async function download() {
  if (!canDownload.value || busy.value) return
  busy.value = true; error.value = ''
  try { await downloadResearchRun(productId, runId) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '下载失败，请重新读取' }
  finally { busy.value = false }
}
onMounted(() => { void load() })
</script>
<template><div class="page-stack"><div class="page-heading"><div><p class="eyebrow">RESEARCH / #{{ runId }}</p><h1>研究详情</h1><p class="muted">{{ run?.goal || '正在读取研究记录…' }}</p></div><RouterLink :to="`/products/${productId}`" class="button ghost">返回商品</RouterLink></div><p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="load">重新读取</button></p><p v-if="notice" class="notice success" role="status">{{ notice }}</p><template v-if="run"><section class="panel"><div class="panel-heading"><h2>当前状态</h2><div class="actions"><StatusBadge :status="run.status" /><StatusBadge :status="run.review_status" /></div></div><p v-if="run.error_message" class="error">{{ run.error_message }}</p><dl class="detail-grid"><div class="kv"><dt>模型</dt><dd>{{ run.provider }} / {{ run.model }}</dd></div><div class="kv"><dt>Token 用量</dt><dd>{{ run.total_tokens ?? '未记录' }}</dd></div><div class="kv"><dt>知识库</dt><dd>{{ run.knowledge_base_ids.join('、') }}</dd></div><div class="kv"><dt>研究 ID</dt><dd>#{{ run.id }}</dd></div></dl><p v-if="run.status === 'pending' || run.status === 'running'" class="muted">研究任务仍在运行；页面可见时自动读取最新业务状态。</p></section>
  <section v-if="run.steps.length" class="panel"><p class="eyebrow">AUDIT TRAIL</p><h2>研究步骤</h2><div v-for="step in run.steps" :key="step.number" class="source-card"><strong>步骤 {{ step.number }} · {{ actionLabels[step.action.action] }}</strong><p v-if="step.action.query">检索词：{{ step.action.query }}</p><p v-if="step.action.knowledge_base_id">知识库 #{{ step.action.knowledge_base_id }}</p><p v-if="step.source_ids.length">新增来源：{{ step.source_ids.join('、') }}</p><small>{{ step.at }} · 提示 {{ step.prompt_tokens ?? '未记录' }} / 生成 {{ step.completion_tokens ?? '未记录' }} / 向量 {{ step.embedding_tokens ?? '未记录' }} tokens</small></div></section>
  <section v-if="run.report" class="panel"><p class="eyebrow">EVIDENCE-BOUND REPORT</p><h2>{{ run.report.outcome === 'insufficient_evidence' ? '证据不足' : '研究报告' }}</h2><p class="pre-wrap">{{ run.report.summary }}</p><div v-if="run.report.evidence_gaps.length"><h3>证据缺口</h3><ul class="list-clean"><li v-for="(gap, index) in run.report.evidence_gaps" :key="index">{{ gap }}</li></ul></div><div v-for="(finding, index) in run.report.findings" :key="`finding-${index}`" class="source-card"><p class="eyebrow">发现 {{ index + 1 }}</p><strong>{{ finding.claim }}</strong><div v-for="sourceId in finding.source_ids" :key="sourceId" class="source-card"><strong>{{ sourceMap.get(sourceId)?.original_name || (sourceMap.get(sourceId)?.source_type === 'product' ? '商品快照' : '来源待核对') }}</strong><small>{{ sourceMap.get(sourceId)?.page_number ? `第 ${sourceMap.get(sourceId)?.page_number} 页` : '' }} · {{ sourceId }}</small><p class="pre-wrap">{{ sourceMap.get(sourceId)?.text || '对应证据未找到' }}</p></div></div><div v-for="(recommendation, index) in run.report.recommendations" :key="`recommendation-${index}`" class="source-card"><p class="eyebrow">建议 {{ index + 1 }}</p><strong>{{ recommendation.action }}</strong><p>{{ recommendation.reason }}</p><div v-for="sourceId in recommendation.source_ids" :key="sourceId" class="muted">来源：{{ sourceMap.get(sourceId)?.original_name || sourceId }}{{ sourceMap.get(sourceId)?.page_number ? ` · 第 ${sourceMap.get(sourceId)?.page_number} 页` : '' }} · {{ sourceMap.get(sourceId)?.text }}</div></div></section>
  <section v-if="run.evidence.length" class="panel"><h2>已登记证据</h2><div v-for="source in run.evidence" :key="source.source_id" class="source-card"><strong>{{ source.original_name || (source.source_type === 'product' ? '商品快照' : '知识资料') }}</strong><small>{{ source.source_id }}{{ source.page_number ? ` · 第 ${source.page_number} 页` : '' }}</small><p class="pre-wrap">{{ source.text }}</p></div></section>
  <section class="panel"><p class="eyebrow">HUMAN GATE</p><h2>人工审核与交付</h2><p v-if="run.review_status === 'not_reviewable'" class="error">证据不足，不可审核，也不可导出。</p><p v-else-if="run.review_status === 'not_ready'" class="muted">研究尚未完成，暂不能审核。</p><p v-else-if="run.review_status === 'pending_review'" class="muted">等待管理员一次性决定；批准或驳回后不可再次审核。</p><div v-if="run.review" class="source-card"><strong>{{ run.review.decision === 'approved' ? '已批准' : '已驳回' }}</strong><p>{{ run.review.comment || '无审核意见' }}</p><small>审核人 #{{ run.review.reviewed_by_id }} · {{ run.review.reviewed_at }}</small></div><div v-if="canReview" class="form-stack"><label>审核意见（驳回必填）<textarea v-model="comment" maxlength="500" /></label><div class="actions"><button data-test="approve" type="button" class="button primary" :disabled="busy" @click="pendingDecision = 'approved'">批准报告</button><button type="button" class="button ghost danger-text" :disabled="busy" @click="pendingDecision = 'rejected'">驳回报告</button></div></div><button v-if="canDownload" type="button" class="button primary" :disabled="busy" @click="download">{{ busy ? '下载中…' : '下载 Excel' }}</button></section></template>
  <ConfirmDialog :open="!!pendingDecision" :title="pendingDecision === 'approved' ? '批准报告' : '驳回报告'" message="该审核决定将永久记录且不能重复提交。确认继续？" :busy="busy" @confirm="review" @cancel="pendingDecision = null" /></div></template>
