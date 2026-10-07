import { createRouter, createWebHistory } from 'vue-router'
import { currentUser, restoreSession } from './lib/session'
import LoginPage from './pages/LoginPage.vue'
import HomePage from './pages/HomePage.vue'
import AppShell from './components/AppShell.vue'
import UsersPage from './features/users/UsersPage.vue'
import ProductsPage from './features/products/ProductsPage.vue'
import ProductPage from './features/products/ProductPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: LoginPage, meta: { title: '登录' } },
    { path: '/', component: AppShell, children: [
      { path: '', component: HomePage, meta: { title: '工作台' } },
      { path: 'users', component: UsersPage, meta: { title: '用户管理', admin: true } },
      { path: 'products', component: ProductsPage, meta: { title: '商品运营' } },
      { path: 'products/new', component: ProductPage, props: { id: 'new' }, meta: { title: '新建商品', manager: true } },
      { path: 'products/:id', component: ProductPage, props: true, meta: { title: '商品详情' } },
    ] },
  ],
})

router.beforeEach(async (to) => {
  if (!currentUser.value) {
    try { await restoreSession() }
    catch { if (to.path !== '/login') return '/login' }
  }
  if (to.path === '/login') return currentUser.value ? '/' : true
  if (!currentUser.value) return '/login'
  if (to.meta.admin && currentUser.value.role !== 'admin') return '/'
  if (to.meta.manager && currentUser.value.role === 'analyst') return '/products'
  return true
})
