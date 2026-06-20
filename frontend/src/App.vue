<script setup>
import { computed, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { isNative } from './lib/native'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const showNav = computed(() => auth.isAuthenticated)
// "Cargar SiRADIG" is a separate mobile epic — hide it in the native apps.
const native = isNative()

// On native the nav is a single horizontally-scrollable line; when the selected
// item is partly off-screen, scroll it fully into view.
function scrollActiveIntoView() {
  if (!native) return
  const nav = document.querySelector('.nav-links')
  const active = nav?.querySelector('a.router-link-exact-active, a.router-link-active')
  if (!nav || !active) return
  const navRect = nav.getBoundingClientRect()
  const aRect = active.getBoundingClientRect()
  const delta = (aRect.left + aRect.width / 2) - (navRect.left + navRect.width / 2)
  nav.scrollBy({ left: delta, behavior: 'smooth' })
}
watch(() => route.fullPath, () => nextTick(scrollActiveIntoView), { immediate: true })

async function onLogout() {
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app">
    <nav v-if="showNav" class="navbar">
      <span class="nav-brand">Factura SiRADIG</span>
      <div class="nav-links">
        <router-link to="/">Dashboard</router-link>
        <router-link to="/capture">Escanear</router-link>
        <router-link to="/invoices">Facturas</router-link>
        <router-link to="/export">Exportar</router-link>
        <router-link v-if="!native" to="/siradig">Cargar SiRADIG</router-link>
        <router-link to="/settings">Configuración</router-link>
      </div>
      <div class="nav-user">
        <span class="nav-username">{{ auth.user?.username }}</span>
        <button class="nav-logout" @click="onLogout">Salir</button>
      </div>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f5f7fa;
  color: #1a1a2e;
  min-height: 100vh;
}

.app { display: flex; flex-direction: column; min-height: 100vh; }

.navbar {
  background: #1976d2;
  color: white;
  padding: 0.75rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,.2);
}

.nav-brand { font-size: 1.1rem; font-weight: 700; letter-spacing: .5px; }

.nav-links { display: flex; gap: 1.25rem; }

.nav-links a {
  color: rgba(255,255,255,.85);
  text-decoration: none;
  font-size: .9rem;
  font-weight: 500;
  padding: .3rem .5rem;
  border-radius: 4px;
  transition: background .15s;
}
.nav-links a:hover,
.nav-links a.router-link-active { background: rgba(255,255,255,.2); color: white; }

.nav-user { display: flex; align-items: center; gap: .75rem; }
.nav-username { font-size: .85rem; color: rgba(255,255,255,.9); font-weight: 600; }
.nav-logout {
  background: rgba(255,255,255,.15);
  color: white;
  border: none;
  padding: .3rem .7rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: .8rem;
  font-weight: 600;
}
.nav-logout:hover { background: rgba(255,255,255,.3); }

/* Native app only (.native on <html>): keep the options on ONE horizontally
   scrollable line. The PWA is intentionally left unchanged. */
.native .navbar { flex-wrap: wrap; gap: .5rem; padding: .6rem 1rem; }
.native .nav-user { order: 2; }
.native .nav-links {
  order: 3;
  width: 100%;
  flex-wrap: nowrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  gap: .25rem;
}
.native .nav-links::-webkit-scrollbar { display: none; }
.native .nav-links a { flex: 0 0 auto; white-space: nowrap; font-size: .85rem; padding: .3rem .6rem; }

.content { flex: 1; padding: 1.5rem; max-width: 900px; margin: 0 auto; width: 100%; }

/* Shared card style */
.card {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 12px rgba(0,0,0,.07);
  margin-bottom: 1rem;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  padding: .55rem 1.1rem;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: .9rem;
  font-weight: 600;
  transition: opacity .15s, transform .1s;
}
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: #1976d2; color: white; }
.btn-primary:hover:not(:disabled) { background: #1565c0; }
.btn-danger  { background: #e53935; color: white; }
.btn-danger:hover:not(:disabled) { background: #c62828; }
.btn-outline { background: transparent; color: #1976d2; border: 2px solid #1976d2; }
.btn-outline:hover:not(:disabled) { background: #e3f2fd; }

/* Form fields */
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: .35rem; color: #444; }
.form-group input, .form-group select {
  width: 100%;
  padding: .6rem .8rem;
  border: 1.5px solid #d0d7de;
  border-radius: 8px;
  font-size: .95rem;
  transition: border-color .15s;
  outline: none;
}
.form-group input:focus, .form-group select:focus { border-color: #1976d2; }

/* Status badges */
.badge {
  display: inline-block;
  padding: .2rem .6rem;
  border-radius: 20px;
  font-size: .75rem;
  font-weight: 700;
  text-transform: uppercase;
}
.badge-pending  { background: #fff3e0; color: #e65100; }
.badge-synced   { background: #e8f5e9; color: #2e7d32; }
.badge-error    { background: #fce4ec; color: #b71c1c; }
</style>
