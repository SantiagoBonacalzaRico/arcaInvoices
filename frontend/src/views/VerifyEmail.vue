<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { verifyEmail } from '../api'

const route = useRoute()
const state = ref('loading') // loading | ok | error
const message = ref('')

onMounted(async () => {
  const token = route.query.token
  if (!token) {
    state.value = 'error'
    message.value = 'Falta el token de verificación.'
    return
  }
  try {
    await verifyEmail(String(token))
    state.value = 'ok'
  } catch (e) {
    state.value = 'error'
    message.value = e?.response?.data?.detail || 'No se pudo verificar la cuenta.'
  }
})
</script>

<template>
  <div class="auth-wrap">
    <div class="card auth-card">
      <h1 class="auth-title">Verificación de cuenta</h1>
      <p v-if="state === 'loading'" class="auth-sub">Verificando…</p>
      <div v-else-if="state === 'ok'" class="auth-center">
        <p class="auth-ok">✅ ¡Tu cuenta fue verificada!</p>
        <router-link class="btn btn-primary auth-btn" to="/login">Ingresar</router-link>
      </div>
      <div v-else class="auth-center">
        <p class="auth-error">{{ message }}</p>
        <router-link class="btn btn-outline auth-btn" to="/login">Volver a ingresar</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap { display: flex; justify-content: center; align-items: flex-start; padding-top: 3rem; }
.auth-card { width: 100%; max-width: 380px; text-align: center; }
.auth-title { font-size: 1.3rem; font-weight: 800; color: #1976d2; margin-bottom: .75rem; }
.auth-sub { color: #666; }
.auth-ok { font-size: 1.1rem; font-weight: 700; color: #2e7d32; margin-bottom: 1rem; }
.auth-error { color: #c62828; margin-bottom: 1rem; }
.auth-btn { width: 100%; justify-content: center; text-decoration: none; }
.auth-center { display: flex; flex-direction: column; gap: .5rem; }
</style>
