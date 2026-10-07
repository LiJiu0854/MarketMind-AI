<script setup lang="ts">
import { currentUser } from '../lib/session'
</script>
<template>
  <div class="page-stack"><section class="hero"><p class="eyebrow">YOUR WORKSPACE</p><h1>早上好，{{ currentUser?.full_name }}。</h1><p>从真实业务对象出发，完成运营、知识沉淀与可追溯研究。</p></section><div class="card-grid"><RouterLink to="/products" class="feature-card"><span class="feature-icon">▣</span><span class="eyebrow">01 / CATALOG</span><h2>商品运营</h2><p>查看商品、优化 Listing、导入导出与研究。</p><span class="card-arrow">进入 →</span></RouterLink><RouterLink to="/knowledge-bases" class="feature-card"><span class="feature-icon">◈</span><span class="eyebrow">02 / KNOWLEDGE</span><h2>知识库</h2><p>沉淀资料，获取附带来源的问答结果。</p><span class="card-arrow">进入 →</span></RouterLink><RouterLink v-if="currentUser?.role === 'admin'" to="/users" class="feature-card"><span class="feature-icon">♧</span><span class="eyebrow">03 / TEAM</span><h2>团队管理</h2><p>维护成员账号与角色权限。</p><span class="card-arrow">进入 →</span></RouterLink></div></div>
</template>
