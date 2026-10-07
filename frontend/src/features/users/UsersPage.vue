<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { currentUser } from '../../lib/session'
import { createUser, deactivateUser, listUsers, updateUser } from './api'
import type { User, UserCreate, UserUpdate, Role } from './types'
import ConfirmDialog from '../../components/ConfirmDialog.vue'

const users = ref<User[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const pendingDelete = ref<User | null>(null)
const editingUser = ref<User | null>(null)
const editInput = ref({ email: '', full_name: '', password: '' })
const input = ref<UserCreate>({ email: '', full_name: '', password: '', role: 'analyst' })
let attempt: { payload: string; key: string } | null = null

async function load() {
  loading.value = true; error.value = ''
  try { const result = await listUsers(page.value); users.value = result.items; total.value = result.total }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '加载用户失败' }
  finally { loading.value = false }
}
async function submit() {
  if (busy.value || currentUser.value?.role !== 'admin') return
  const payload = JSON.stringify({ ...input.value, email: input.value.email.trim(), full_name: input.value.full_name.trim() })
  if (!attempt || attempt.payload !== payload) attempt = { payload, key: crypto.randomUUID() }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await createUser(JSON.parse(payload) as UserCreate, attempt.key)
    attempt = null
    input.value = { email: '', full_name: '', password: '', role: 'analyst' }
    notice.value = '用户已创建'
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '创建用户失败' }
  finally { busy.value = false }
}
async function changeRole(user: User, role: Role) {
  if (busy.value || currentUser.value?.role !== 'admin') return
  busy.value = true; error.value = ''
  try { await updateUser(user.id, { role }); notice.value = '角色已更新'; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '更新失败，请重新加载后重试' }
  finally { busy.value = false }
}
function beginEdit(user: User) {
  editingUser.value = user
  editInput.value = { email: user.email, full_name: user.full_name, password: '' }
}
async function saveEdit() {
  if (!editingUser.value || busy.value || currentUser.value?.role !== 'admin') return
  const changes: UserUpdate = { email: editInput.value.email.trim(), full_name: editInput.value.full_name.trim() }
  if (editInput.value.password) changes.password = editInput.value.password
  busy.value = true; error.value = ''
  try { await updateUser(editingUser.value.id, changes); editingUser.value = null; notice.value = '用户资料已更新'; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '更新失败，请重新读取后重试' }
  finally { busy.value = false }
}
async function deactivate() {
  if (!pendingDelete.value || busy.value || currentUser.value?.role !== 'admin') return
  busy.value = true; error.value = ''
  try { await deactivateUser(pendingDelete.value.id); notice.value = '账号已停用'; pendingDelete.value = null; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '停用失败' }
  finally { busy.value = false }
}
onMounted(() => { if (currentUser.value?.role === 'admin') void load() })
</script>
<template>
  <section v-if="currentUser?.role !== 'admin'" class="panel"><h1>无权限</h1><p>只有管理员可以管理用户。</p></section>
  <div v-else class="page-stack">
    <div class="page-heading"><div><p class="eyebrow">TEAM ACCESS</p><h1>用户管理</h1><p class="muted">配置团队成员的访问权限，所有变更由服务端校验。</p></div><span class="count-pill">{{ total }} 位成员</span></div>
    <p v-if="error" role="alert" class="error notice">{{ error }} <button type="button" class="text-button" @click="load">重新读取</button></p>
    <p v-if="notice" role="status" class="success notice">{{ notice }}</p>
    <div class="two-column">
      <section class="panel"><div class="panel-heading"><h2>团队成员</h2><span class="muted">第 {{ page }} 页</span></div>
        <p v-if="loading" role="status">正在读取用户…</p><p v-else-if="!users.length" class="empty">暂无用户</p>
        <div v-else class="table-wrap"><table><thead><tr><th>成员</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td><strong>{{ user.full_name }}</strong><small>{{ user.email }}</small></td><td><select :aria-label="`修改 ${user.full_name} 的角色`" :value="user.role" :disabled="busy" @change="changeRole(user, ($event.target as HTMLSelectElement).value as Role)"><option value="admin">管理员</option><option value="operator">运营</option><option value="analyst">分析员</option></select></td><td><span class="status-badge" :class="user.is_active ? 'status-active' : 'status-inactive'">{{ user.is_active ? '启用' : '停用' }}</span></td><td><button data-test="edit-user" type="button" class="text-button" :disabled="busy" @click="beginEdit(user)">编辑</button><button type="button" class="text-button danger-text" :disabled="busy || !user.is_active" @click="pendingDelete = user">停用</button></td></tr></tbody></table></div>
        <div class="pager"><button type="button" class="button ghost" :disabled="page <= 1 || loading" @click="page--; load()">上一页</button><span>{{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span><button type="button" class="button ghost" :disabled="page * 20 >= total || loading" @click="page++; load()">下一页</button></div>
      </section>
      <section class="panel"><p class="eyebrow">INVITE A MEMBER</p><h2>创建账号</h2><p class="muted">初始管理员通过后端 CLI 创建；此处仅管理后续成员。</p><form class="form-stack" @submit.prevent="submit"><label>邮箱<input v-model="input.email" name="email" type="email" required /></label><label>姓名<input v-model="input.full_name" name="full_name" maxlength="100" required /></label><label>初始密码<input v-model="input.password" name="password" type="password" minlength="12" required /></label><label>角色<select v-model="input.role" name="role"><option value="analyst">分析员 · 只读</option><option value="operator">运营 · 业务写入</option><option value="admin">管理员 · 全部权限</option></select></label><button type="submit" class="button primary" :disabled="busy">{{ busy ? '正在创建…' : '创建用户' }}</button></form></section>
    </div>
    <section v-if="editingUser" class="panel"><div class="panel-heading"><h2>编辑 {{ editingUser.full_name }}</h2><button type="button" class="text-button" @click="editingUser = null">取消</button></div><form data-test="edit-form" class="form-stack" @submit.prevent="saveEdit"><div class="detail-grid"><label>邮箱<input v-model="editInput.email" name="edit_email" type="email" required /></label><label>姓名<input v-model="editInput.full_name" name="edit_full_name" maxlength="100" required /></label></div><label>新密码（不修改则留空）<input v-model="editInput.password" name="edit_password" type="password" minlength="12" /></label><button type="submit" class="button primary" :disabled="busy">{{ busy ? '保存中…' : '保存更改' }}</button></form></section>
    <ConfirmDialog :open="!!pendingDelete" title="停用账号" :message="`确认停用 ${pendingDelete?.full_name || ''}？该用户将无法继续登录。`" :busy="busy" @confirm="deactivate" @cancel="pendingDelete = null" />
  </div>
</template>
