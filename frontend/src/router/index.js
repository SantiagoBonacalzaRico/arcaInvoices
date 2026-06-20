import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { isNative, loadToken } from '../lib/native'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/register', name: 'register', component: () => import('../views/Register.vue'), meta: { public: true } },
  { path: '/verify', name: 'verify', component: () => import('../views/VerifyEmail.vue'), meta: { public: true } },
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/capture', name: 'capture', component: () => import('../views/Capture.vue') },
  { path: '/invoices', name: 'invoices', component: () => import('../views/Invoices.vue') },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue') },
  { path: '/export', name: 'export', component: () => import('../views/Export.vue') },
  { path: '/siradig', name: 'siradig', component: () => import('../views/Siradig.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  // "Cargar SiRADIG" is excluded from the native apps (separate epic).
  if (isNative() && to.name === 'siradig') return { name: 'dashboard' }

  const auth = useAuthStore()
  // Resolve auth state once on first navigation. Hydrate the native bearer
  // token BEFORE the first /auth/me, otherwise it races and 401s on relaunch.
  if (!auth.ready) {
    await loadToken()
    await auth.fetchMe()
  }

  if (to.meta.public) {
    // Already authenticated users shouldn't sit on login/register.
    if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
      return { name: 'dashboard' }
    }
    return true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
