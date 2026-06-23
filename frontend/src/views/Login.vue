<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { googleLoginUrl } from '../api'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const identifier = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(identifier.value.trim(), password.value)
    router.push(route.query.redirect || { name: 'dashboard' })
  } catch (e) {
    error.value = e?.response?.data?.detail || 'No se pudo iniciar sesión.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="card auth-card">
      <h1 class="auth-title">Factura SiRADIG</h1>
      <p class="auth-sub">Ingresá a tu cuenta</p>

      <form @submit.prevent="submit">
        <div class="form-group">
          <label>Email o usuario</label>
          <input v-model="identifier" type="text" autocomplete="username" required />
        </div>
        <div class="form-group">
          <label>Contraseña</label>
          <input v-model="password" type="password" autocomplete="current-password" required />
        </div>

        <p v-if="error" class="auth-error">{{ error }}</p>

        <button class="btn btn-primary auth-btn" type="submit" :disabled="loading">
          {{ loading ? 'Ingresando…' : 'Ingresar' }}
        </button>
      </form>

      <p class="auth-forgot">
        <router-link to="/forgot-password">¿Olvidaste tu contraseña?</router-link>
      </p>

      <div class="auth-divider"><span>o</span></div>

      <a class="btn btn-outline auth-btn" :href="googleLoginUrl">Ingresar con Google</a>

      <p class="auth-foot">
        ¿Tenés una invitación?
        <router-link to="/register">Registrate</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap { display: flex; justify-content: center; align-items: flex-start; padding-top: 3rem; }
.auth-card { width: 100%; max-width: 380px; }
.auth-title { font-size: 1.4rem; font-weight: 800; text-align: center; color: #1976d2; }
.auth-sub { text-align: center; color: #666; margin: .25rem 0 1.25rem; font-size: .9rem; }
.auth-btn { width: 100%; justify-content: center; margin-top: .25rem; text-decoration: none; }
.auth-error { color: #c62828; font-size: .85rem; margin: .5rem 0; }
.auth-divider { display: flex; align-items: center; text-align: center; color: #999; margin: 1rem 0; font-size: .8rem; }
.auth-divider::before, .auth-divider::after { content: ''; flex: 1; border-bottom: 1px solid #e0e0e0; }
.auth-divider span { padding: 0 .75rem; }
.auth-foot { text-align: center; margin-top: 1.25rem; font-size: .85rem; color: #555; }
.auth-forgot { text-align: center; margin: .85rem 0 0; font-size: .85rem; }
</style>
