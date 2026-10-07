<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiJson } from '../lib/api'
import { restoreSession, saveToken } from '../lib/session'

const router = useRouter()
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const body = new URLSearchParams({ username: email.value.trim(), password: password.value })
    const result = await apiJson<{ access_token: string }>('/auth/token', { method: 'POST', body }, false)
    saveToken(result.access_token)
    await restoreSession()
    await router.replace('/')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败，请稍后重试'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-intro">
      <p class="eyebrow">MARKETMIND · INTELLIGENCE WORKSPACE</p>
      <h1>让每一次运营决策，<br><em>都有迹可循。</em></h1>
      <p>商品运营、知识沉淀与研究交付，汇聚在一处清晰的工作台。</p>
      <div class="login-lines" aria-hidden="true"><span /><span /><span /></div>
    </section>
    <section class="login-card" aria-labelledby="login-title">
      <p class="eyebrow">欢迎回来</p>
      <h2 id="login-title">登录工作台</h2>
      <p class="muted">请使用管理员分配的企业账号。</p>
      <form @submit.prevent="submit">
        <label for="login-email">邮箱</label>
        <input id="login-email" v-model="email" type="email" autocomplete="username" required placeholder="name@company.com" />
        <label for="login-password">密码</label>
        <input id="login-password" v-model="password" type="password" autocomplete="current-password" required placeholder="输入账号密码" />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" class="button primary full" :disabled="busy">{{ busy ? '正在验证…' : '进入工作台' }}</button>
      </form>
      <p class="login-foot">凭证仅保存在当前浏览器标签页</p>
    </section>
  </main>
</template>
