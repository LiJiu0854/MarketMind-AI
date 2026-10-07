<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { currentUser } from '../../lib/session'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ProductForm from './ProductForm.vue'
import { checkListing, deactivateProduct, getProduct, saveProduct } from './api'
import type { ListingCheckResult, Product, ProductInput } from './types'

const props = defineProps<{ id: string }>()
const router = useRouter()
const product = ref<Product | null>(null)
const listing = ref<ListingCheckResult | null>(null)
const editing = ref(props.id === 'new')
const confirmOpen = ref(false)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const canWrite = computed(() => currentUser.value?.role === 'admin' || currentUser.value?.role === 'operator')
const id = computed(() => Number(props.id))

async function load() {
  if (props.id === 'new') return
  loading.value = true; error.value = ''
  try { product.value = await getProduct(id.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '商品读取失败' }
  finally { loading.value = false }
}
async function inspect() {
  busy.value = true; error.value = ''
  try { listing.value = await checkListing(id.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '检查失败' }
  finally { busy.value = false }
}
async function save(input: ProductInput) {
  if (!canWrite.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const saved = await saveProduct(input, props.id === 'new' ? undefined : id.value)
    notice.value = '商品已保存'; editing.value = false; product.value = saved
    if (props.id === 'new') await router.replace(`/products/${saved.id}`)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}
async function deactivate() {
  if (!canWrite.value || !product.value || busy.value) return
  busy.value = true; error.value = ''
  try { product.value = await deactivateProduct(id.value); confirmOpen.value = false; notice.value = '商品已停用' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '停用失败' }
  finally { busy.value = false }
}
watch(() => props.id, () => { product.value = null; listing.value = null; editing.value = props.id === 'new'; void load() })
onMounted(() => { void load() })
</script>
<template>
  <div class="page-stack"><div class="page-heading"><div><p class="eyebrow">PRODUCT DETAIL</p><h1>{{ props.id === 'new' ? '新建商品' : product?.title || '商品详情' }}</h1><p class="muted">{{ product?.sku || '填写准确的商品基础信息。' }}</p></div><div class="actions"><RouterLink to="/products" class="button ghost">返回列表</RouterLink><button v-if="product && canWrite && !editing" type="button" class="button primary" @click="editing = true">编辑商品</button><button v-if="product?.is_active && canWrite && !editing" type="button" class="button ghost danger-text" @click="confirmOpen = true">停用商品</button></div></div>
    <p v-if="error" class="error notice" role="alert">{{ error }} <button v-if="props.id !== 'new'" type="button" class="text-button" @click="load">重新读取</button></p><p v-if="notice" class="notice success" role="status">{{ notice }}</p><p v-if="loading" role="status">正在读取商品…</p>
    <section v-if="editing && canWrite" class="panel"><h2>{{ props.id === 'new' ? '填写商品信息' : '编辑商品信息' }}</h2><ProductForm :initial="product || undefined" :busy="busy" @submit="save" /><button v-if="product" type="button" class="text-button" @click="editing = false">取消编辑</button></section>
    <template v-if="product && !editing"><section class="panel"><div class="panel-heading"><h2>基础信息</h2><span class="status-badge" :class="product.is_active ? 'status-active' : 'status-inactive'">{{ product.is_active ? '启用' : '停用' }}</span></div><dl class="detail-grid"><div v-for="[label, value] in [['SKU', product.sku], ['品牌', product.brand || '—'], ['品类', product.category || '—'], ['价格', `${product.price} ${product.currency}`]]" :key="label" class="kv"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl><h3>描述</h3><p class="pre-wrap muted">{{ product.description || '暂无描述' }}</p><h3>卖点</h3><ol v-if="product.bullet_points.length" class="list-clean"><li v-for="(bullet, index) in product.bullet_points" :key="index">{{ bullet }}</li></ol><p v-else class="muted">暂无卖点</p></section>
      <section class="panel"><div class="panel-heading"><div><p class="eyebrow">DETERMINISTIC CHECK</p><h2>Listing 检查</h2></div><button data-test="listing-check" type="button" class="button ghost" :disabled="busy" @click="inspect">{{ busy ? '检查中…' : '运行检查' }}</button></div><p class="muted">使用本地确定性规则检查，不调用付费模型。</p><div v-if="listing"><p :class="listing.passed ? 'success' : 'error'">{{ listing.passed ? '检查通过' : `${listing.issues.length} 项需改进` }}</p><div v-for="issue in listing.issues" :key="issue.code" class="source-card"><strong>{{ issue.message }}</strong><p class="muted">{{ issue.field }} · {{ issue.suggestion }}</p></div></div></section>
    </template>
    <ConfirmDialog :open="confirmOpen" title="停用商品" message="停用后该商品不会再参与正常运营。确认继续？" :busy="busy" @confirm="deactivate" @cancel="confirmOpen = false" />
  </div>
</template>
