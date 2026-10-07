<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { createKnowledgeBase, listKnowledgeBases } from './api'
import type { KnowledgeBase } from './types'

const items = ref<KnowledgeBase[]>([])
const total = ref(0)
const page = ref(1)
const name = ref('')
const description = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
async function load() {
  loading.value = true; error.value = ''
  try { const result = await listKnowledgeBases(page.value); items.value = result.items; total.value = result.total }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '知识库读取失败' }
  finally { loading.value = false }
}
async function create() {
  if (busy.value || currentUser.value?.role !== 'admin') return
  busy.value = true; error.value = ''
  try { await createKnowledgeBase({ name: name.value.trim(), description: description.value.trim() || null }); name.value = ''; description.value = ''; notice.value = '知识库已创建'; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '创建失败' }
  finally { busy.value = false }
}
onMounted(() => { void load() })
</script>
<template><div class="page-stack"><div class="page-heading"><div><p class="eyebrow">KNOWLEDGE SYSTEM</p><h1>知识库</h1><p class="muted">把可靠资料整理成可追溯的知识来源。</p></div><span class="count-pill">{{ total }} 个知识库</span></div><p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="load">重试</button></p><p v-if="notice" class="notice success" role="status">{{ notice }}</p><div class="two-column"><section class="panel"><div class="panel-heading"><h2>全部知识库</h2><span class="muted">第 {{ page }} 页</span></div><p v-if="loading" role="status">正在读取…</p><p v-else-if="!items.length" class="empty">暂无知识库</p><div v-else class="card-grid" style="grid-template-columns:repeat(auto-fit,minmax(215px,1fr))"><RouterLink v-for="base in items" :key="base.id" :to="`/knowledge-bases/${base.id}`" class="feature-card"><span class="feature-icon">◈</span><h2>{{ base.name }}</h2><p>{{ base.description || '暂无描述' }}</p><small>模型：{{ base.embedding_model }}</small><span class="card-arrow">查看资料与问答 →</span></RouterLink></div><div class="pager"><button type="button" class="button ghost" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button><span>{{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span><button type="button" class="button ghost" :disabled="page * 20 >= total || loading" @click="page++; load()">下一页</button></div></section><section v-if="currentUser?.role === 'admin'" class="panel"><p class="eyebrow">CREATE A SOURCE</p><h2>新建知识库</h2><p class="muted">上传资料前先创建知识库，模型配置由服务端管理。</p><form class="form-stack" @submit.prevent="create"><label>名称<input v-model="name" required maxlength="100" /></label><label>说明<textarea v-model="description" maxlength="500" /></label><button type="submit" class="button primary" :disabled="busy">{{ busy ? '正在创建…' : '创建知识库' }}</button></form></section></div></div></template>
