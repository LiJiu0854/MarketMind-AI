<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { useTaskPolling } from '../../lib/useTaskPolling'
import StatusBadge from '../../components/StatusBadge.vue'
import { askKnowledge, getKnowledgeBase, listDocuments, listQuestions, uploadDocument } from './api'
import type { KnowledgeBase, KnowledgeDocument, KnowledgeQuery } from './types'

const props = defineProps<{ id: string }>()
const baseId = Number(props.id)
const base = ref<KnowledgeBase | null>(null)
const documents = ref<KnowledgeDocument[]>([])
const queries = ref<KnowledgeQuery[]>([])
const answer = ref<KnowledgeQuery | null>(null)
const question = ref('')
const docPage = ref(1)
const queryPage = ref(1)
const docTotal = ref(0)
const queryTotal = ref(0)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const polling = useTaskPolling(async () => {
  const result = await listDocuments(baseId, docPage.value)
  documents.value = result.items; docTotal.value = result.total
  return result.items.some((item) => item.status === 'pending' || item.status === 'processing')
})
async function loadDocuments() {
  try {
    const result = await listDocuments(baseId, docPage.value)
    documents.value = result.items; docTotal.value = result.total
    if (result.items.some((item) => item.status === 'pending' || item.status === 'processing')) polling.start()
    else polling.stop()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '文档读取失败'; polling.stop() }
}
async function loadQueries() {
  try { const result = await listQuestions(baseId, queryPage.value); queries.value = result.items; queryTotal.value = result.total }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '问答历史读取失败' }
}
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file || busy.value || currentUser.value?.role !== 'admin') return
  busy.value = true; error.value = ''
  try { await uploadDocument(baseId, file); notice.value = '文档已提交索引任务'; await loadDocuments() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '上传失败' }
  finally { busy.value = false; (event.target as HTMLInputElement).value = '' }
}
async function ask() {
  if (busy.value || !question.value.trim()) return
  busy.value = true; error.value = ''; answer.value = null
  try { answer.value = await askKnowledge(baseId, question.value); question.value = ''; await loadQueries() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '问答失败' }
  finally { busy.value = false }
}
onMounted(async () => {
  try { base.value = await getKnowledgeBase(baseId) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '知识库读取失败' }
  await Promise.all([loadDocuments(), loadQueries()])
})
</script>
<template><div class="page-stack"><div class="page-heading"><div><p class="eyebrow">KNOWLEDGE BASE / {{ id }}</p><h1>{{ base?.name || '知识库详情' }}</h1><p class="muted">{{ base?.description || '资料索引与有来源的问答。' }}</p></div><RouterLink to="/knowledge-bases" class="button ghost">返回知识库</RouterLink></div><p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="loadDocuments">重新读取</button></p><p v-if="notice" class="notice success" role="status">{{ notice }}</p>
  <section class="panel"><div class="panel-heading"><div><p class="eyebrow">DOCUMENTS</p><h2>已上传资料</h2></div><span class="count-pill">{{ docTotal }} 份</span></div><label v-if="currentUser?.role === 'admin'" class="field" style="max-width:330px;margin-bottom:22px">上传文档<input type="file" :disabled="busy" accept=".pdf,.txt,.md" @change="upload" /></label><p v-if="!documents.length" class="empty">暂无文档。资料就绪后才能参与问答。</p><div v-else class="table-wrap"><table><thead><tr><th>文件</th><th>大小</th><th>索引块</th><th>状态</th><th>反馈</th></tr></thead><tbody><tr v-for="doc in documents" :key="doc.id"><td>{{ doc.original_name }}</td><td>{{ Math.ceil(doc.size_bytes / 1024) }} KB</td><td>{{ doc.chunk_count }}</td><td><StatusBadge :status="doc.status" /></td><td>{{ doc.error_message || '—' }}</td></tr></tbody></table></div><div class="pager"><button type="button" class="button ghost" :disabled="docPage <= 1" @click="docPage--; loadDocuments()">上一页</button><span>第 {{ docPage }} 页</span><button type="button" class="button ghost" :disabled="docPage * 20 >= docTotal" @click="docPage++; loadDocuments()">下一页</button></div></section>
  <section class="panel"><p class="eyebrow">ASK THE KNOWLEDGE</p><h2>向知识库提问</h2><p class="muted">答案仅来自已索引资料；证据不足时会明确拒答。</p><form class="form-stack" @submit.prevent="ask"><label>问题<textarea v-model="question" name="question" required maxlength="2000" placeholder="输入您想从资料中确认的问题" /></label><button type="submit" class="button primary" :disabled="busy">{{ busy ? '正在检索与回答…' : '提交问题' }}</button></form><div v-if="answer" class="source-card" style="margin-top:20px"><StatusBadge :status="answer.status" /><h3>{{ answer.status === 'refused' ? '拒答：资料不足' : '回答' }}</h3><p class="pre-wrap">{{ answer.answer || answer.error_message }}</p><div v-for="citation in answer.citations" :key="citation.chunk_id" class="source-card"><strong>{{ citation.original_name }}{{ citation.page_number ? ` · 第 ${citation.page_number} 页` : '' }}</strong><p class="muted pre-wrap">{{ citation.excerpt }}</p></div></div></section>
  <section class="panel"><div class="panel-heading"><h2>问答历史</h2><span class="count-pill">{{ queryTotal }} 条</span></div><p v-if="!queries.length" class="empty">暂无问答记录</p><div v-for="query in queries" :key="query.id" class="source-card"><strong>{{ query.question }}</strong><p>{{ query.answer || query.error_message || '无答案' }}</p><StatusBadge :status="query.status" /><div v-for="citation in query.citations" :key="citation.chunk_id" class="muted">来源：{{ citation.original_name }}{{ citation.page_number ? ` · 第 ${citation.page_number} 页` : '' }} · {{ citation.excerpt }}</div></div><div class="pager"><button type="button" class="button ghost" :disabled="queryPage <= 1" @click="queryPage--; loadQueries()">上一页</button><span>第 {{ queryPage }} 页</span><button type="button" class="button ghost" :disabled="queryPage * 20 >= queryTotal" @click="queryPage++; loadQueries()">下一页</button></div></section></div></template>
