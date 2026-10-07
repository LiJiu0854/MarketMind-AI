<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { exportProducts, importProducts, listProducts } from './api'
import type { Product, ProductFilters, ProductImportResult } from './types'

const draft = ref({ sku: '', brand: '', category: '', is_active: '' })
const filters = ref<ProductFilters>({})
const items = ref<Product[]>([])
const total = ref(0)
const page = ref(1)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const importResult = ref<ProductImportResult | null>(null)
let requestId = 0

async function load() {
  const ownId = ++requestId
  loading.value = true; error.value = ''
  try {
    const result = await listProducts(filters.value, page.value)
    if (ownId !== requestId) return
    items.value = result.items; total.value = result.total
  } catch (cause) {
    if (ownId === requestId) error.value = cause instanceof Error ? cause.message : '商品加载失败'
  } finally { if (ownId === requestId) loading.value = false }
}
function applyFilters() {
  filters.value = {
    sku: draft.value.sku.trim() || undefined,
    brand: draft.value.brand.trim() || undefined,
    category: draft.value.category.trim() || undefined,
    is_active: draft.value.is_active === '' ? undefined : draft.value.is_active === 'true',
  }
  page.value = 1
  void load()
}
async function download() {
  busy.value = true; error.value = ''
  try { await exportProducts(filters.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '导出失败' }
  finally { busy.value = false }
}
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = '请上传 .xlsx 格式文件'; return }
  busy.value = true; error.value = ''; importResult.value = null
  try { importResult.value = await importProducts(file); notice.value = '导入校验完成'; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '导入失败' }
  finally { busy.value = false; (event.target as HTMLInputElement).value = '' }
}
onMounted(() => { void load() })
</script>
<template>
  <div class="page-stack"><div class="page-heading"><div><p class="eyebrow">PRODUCT CATALOG</p><h1>商品运营</h1><p class="muted">筛选、检查与维护您的商品资料。</p></div><div class="actions"><RouterLink v-if="currentUser?.role !== 'analyst'" to="/products/new" class="button primary">新建商品</RouterLink><button type="button" class="button ghost" :disabled="busy" @click="download">导出 Excel</button></div></div>
    <section class="panel"><form class="toolbar" @submit.prevent="applyFilters"><label class="field">SKU<input v-model="draft.sku" name="sku" placeholder="按 SKU 搜索" /></label><label class="field">品牌<input v-model="draft.brand" name="brand" placeholder="按品牌筛选" /></label><label class="field">品类<input v-model="draft.category" name="category" placeholder="按品类筛选" /></label><label class="field">状态<select v-model="draft.is_active"><option value="">全部</option><option value="true">启用</option><option value="false">停用</option></select></label><button type="submit" class="button primary">应用筛选</button></form></section>
    <p v-if="error" class="error notice" role="alert">{{ error }} <button type="button" class="text-button" @click="load">重试读取</button></p><p v-if="notice" role="status" class="notice success">{{ notice }}</p>
    <section class="panel"><div class="panel-heading"><h2>商品列表</h2><span class="count-pill">{{ total }} 件商品</span></div><p v-if="loading" role="status">正在读取商品…</p><p v-else-if="!items.length" class="empty">暂无商品。可调整筛选条件后重试。</p><div v-else class="table-wrap"><table><thead><tr><th>商品</th><th>品牌 / 品类</th><th>价格</th><th>状态</th><th></th></tr></thead><tbody><tr v-for="product in items" :key="product.id"><td><strong>{{ product.title }}</strong><small>{{ product.sku }}</small></td><td>{{ product.brand || '—' }}<small>{{ product.category || '未分类' }}</small></td><td>{{ product.price }} {{ product.currency }}</td><td><span class="status-badge" :class="product.is_active ? 'status-active' : 'status-inactive'">{{ product.is_active ? '启用' : '停用' }}</span></td><td><RouterLink :to="`/products/${product.id}`" class="text-button">查看详情 →</RouterLink></td></tr></tbody></table></div><div class="pager"><button type="button" class="button ghost" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button><span>第 {{ page }} 页</span><button type="button" class="button ghost" :disabled="page * 20 >= total || loading" @click="page++; load()">下一页</button></div></section>
    <section v-if="currentUser?.role !== 'analyst'" class="panel"><h2>批量导入</h2><p class="muted">上传 Excel 工作簿，服务端逐行校验。仅支持 .xlsx。</p><label class="field">选择文件<input type="file" accept=".xlsx" :disabled="busy" @change="upload" /></label><div v-if="importResult" role="status"><p>总计 {{ importResult.total_rows }} 行 · 成功 {{ importResult.imported_rows }} 行 · 失败 {{ importResult.failed_rows }} 行</p><div v-if="importResult.errors.length" class="table-wrap"><table><thead><tr><th>行</th><th>字段</th><th>错误码</th><th>说明</th></tr></thead><tbody><tr v-for="item in importResult.errors" :key="`${item.row}-${item.field}`"><td>{{ item.row }}</td><td>{{ item.field }}</td><td>{{ item.code }}</td><td>{{ item.message }}</td></tr></tbody></table></div></div></section>
  </div>
</template>
