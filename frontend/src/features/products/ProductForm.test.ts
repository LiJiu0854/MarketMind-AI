import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ProductForm from './ProductForm.vue'

it('requires fields and emits decimal text and individual bullet points', async () => {
  const wrapper = mount(ProductForm)
  await wrapper.get('input[name="sku"]').setValue('A-1')
  await wrapper.get('input[name="title"]').setValue('测试商品')
  await wrapper.get('input[name="price"]').setValue('19.90')
  await wrapper.get('button[data-test="add-bullet"]').trigger('click')
  const bullets = wrapper.findAll('input[name="bullet"]')
  await bullets[0]!.setValue('第一条')
  await bullets[1]!.setValue('第二条')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ price: '19.90', bullet_points: ['第一条', '第二条'] })
})
