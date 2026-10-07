<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ProductInput } from './types'

const props = defineProps<{ initial?: ProductInput; busy?: boolean }>()
const emit = defineEmits<{ submit: [input: ProductInput] }>()
const empty = (): ProductInput => ({ sku: '', title: '', description: '', bullet_points: [''], brand: '', category: '', price: '', currency: 'CNY', is_active: true })
const copy = (value: ProductInput): ProductInput => ({
  sku: value.sku, title: value.title, description: value.description,
  bullet_points: [...value.bullet_points], brand: value.brand, category: value.category,
  price: value.price, currency: value.currency, is_active: value.is_active,
})
const form = ref<ProductInput>(props.initial ? copy(props.initial) : empty())
watch(() => props.initial, (value) => { if (value) form.value = copy(value) })
function submit() {
  const input = { ...form.value, sku: form.value.sku.trim(), title: form.value.title.trim(), price: form.value.price.trim(), bullet_points: form.value.bullet_points.map((item) => item.trim()).filter(Boolean) }
  if (!input.sku || !input.title || !/^\d+(?:\.\d{1,2})?$/.test(input.price) || Number(input.price) <= 0) return
  emit('submit', input)
}
</script>
<template>
  <form class="form-stack" @submit.prevent="submit">
    <div class="detail-grid"><label>SKU<input v-model="form.sku" name="sku" required maxlength="50" /></label><label>标题<input v-model="form.title" name="title" required maxlength="200" /></label><label>品牌<input v-model="form.brand" maxlength="100" /></label><label>品类<input v-model="form.category" maxlength="100" /></label><label>价格<input v-model="form.price" name="price" inputmode="decimal" required pattern="[0-9]+(\.[0-9]{1,2})?" placeholder="19.90" /></label><label>币种<input v-model="form.currency" maxlength="3" required pattern="[A-Z]{3}" /></label></div>
    <label>描述<textarea v-model="form.description" rows="5" /></label><div><div class="panel-heading"><h3>卖点</h3><button type="button" data-test="add-bullet" class="text-button" @click="form.bullet_points.push('')">＋ 添加一条</button></div><div v-for="(_, index) in form.bullet_points" :key="index" class="actions" style="margin-bottom:9px"><input v-model="form.bullet_points[index]" name="bullet" :aria-label="`卖点 ${index + 1}`" style="flex:1;min-width:180px" /><button type="button" class="text-button danger-text" @click="form.bullet_points.splice(index, 1)">移除</button></div></div><label class="field"><span>状态</span><select v-model="form.is_active"><option :value="true">启用</option><option :value="false">停用</option></select></label><button type="submit" class="button primary" :disabled="busy">{{ busy ? '正在保存…' : '保存商品' }}</button>
  </form>
</template>
