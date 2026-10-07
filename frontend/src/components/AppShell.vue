<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearSession, currentUser } from '../lib/session'

const router = useRouter()
const route = useRoute()
const admin = computed(() => currentUser.value?.role === 'admin')
const links = [
  { to: '/', label: '工作台', icon: '◫' },
  { to: '/products', label: '商品运营', icon: '▣' },
  { to: '/knowledge-bases', label: '知识库', icon: '◈' },
]
function logout() { clearSession(); void router.replace('/login') }
</script>

<template>
  <div class="workspace">
    <aside class="sidebar" aria-label="主导航">
      <RouterLink to="/" class="brand"><span class="brand-mark">M</span><span>MarketMind<small>AI WORKSPACE</small></span></RouterLink>
      <p class="sidebar-caption">工作空间</p>
      <nav class="nav-list">
        <RouterLink v-for="link in links" :key="link.to" :to="link.to" class="nav-link" :class="{ active: route.path === link.to }"><span aria-hidden="true">{{ link.icon }}</span>{{ link.label }}</RouterLink>
        <RouterLink v-if="admin" to="/users" class="nav-link" :class="{ active: route.path === '/users' }"><span aria-hidden="true">♧</span>用户管理</RouterLink>
      </nav>
      <div class="sidebar-bottom"><span class="online-dot" /> 企业运营工作台</div>
    </aside>
    <div class="workspace-main">
      <header class="topbar"><div class="topbar-title"><span class="topbar-kicker">MARKETMIND / WORKSPACE</span><strong>{{ String(route.meta.title || '工作台') }}</strong></div><div class="account"><span class="avatar">{{ currentUser?.full_name?.slice(0, 1) || 'U' }}</span><span class="account-name">{{ currentUser?.full_name }}<small>{{ currentUser?.role }}</small></span><button type="button" class="text-button" @click="logout">退出</button></div></header>
      <main class="content"><RouterView /></main>
    </div>
  </div>
</template>
