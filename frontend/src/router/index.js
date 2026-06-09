import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
  { path: '/capture', name: 'capture', component: () => import('../views/Capture.vue') },
  { path: '/invoices', name: 'invoices', component: () => import('../views/Invoices.vue') },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue') },
  { path: '/export', name: 'export', component: () => import('../views/Export.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
