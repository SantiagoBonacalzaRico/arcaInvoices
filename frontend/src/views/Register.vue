<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { register, googleLoginUrl } from '../api'

const route = useRoute()
const inviteCode = ref('')
const email = ref('')
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

onMounted(() => {
  if (route.query.invite) inviteCode.value = String(route.query.invite)
})

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await register({
      invite_code: inviteCode.value.trim(),
      email: email.value.trim(),
      username: username.value.trim(),
      password: password.value,
    })
    done.value = true
  } catch (e) {
    error.value = e?.response?.data?.detail || 'No se pudo completar el registro.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="card auth-card">
      <h1 class="auth-title">Crear cuenta</h1>

      <div v-if="done" class="auth-done">
        <p>✅ ¡Cuenta creada!</p>
        <p class="auth-sub">
          Te enviamos un email para verificar tu cuenta. Revisá tu bandeja
          (y la carpeta de spam) y seguí el enlace para activarla.
        </p>
        <router-link class="btn btn-primary auth-btn" to="/login">Ir a ingresar</router-link>
      </div>

      <form v-else @submit.prevent="submit">
        <p class="auth-sub">El registro requiere un código de invitación.</p>
        <div class="form-group">
          <label>Código de invitación</label>
          <input v-model="inviteCode" type="text" required />
        </div>
        <div class="form-group">
          <label>Email</label>
          <input v-model="email" type="email" autocomplete="email" required />
        </div>
        <div class="form-group">
          <label>Usuario</label>
          <input v-model="username" type="text" autocomplete="username" required />
        </div>
        <div class="form-group">
          <label>Contraseña (mín. 8 caracteres)</label>
          <input v-model="password" type="password" autocomplete="new-password" minlength="8" required />
        </div>

        <p v-if="error" class="auth-error">{{ error }}</p>

        <button class="btn btn-primary auth-btn" type="submit" :disabled="loading">
          {{ loading ? 'Creando…' : 'Crear cuenta' }}
        </button>

        <div class="auth-divider"><span>o</span></div>
        <a class="btn btn-outline auth-btn" :href="googleLoginUrl">Registrarme con Google</a>
        <p class="auth-hint">Con Google también necesitás una invitación válida para tu email.</p>
      </form>

      <p class="auth-foot">
        ¿Ya tenés cuenta? <router-link to="/login">Ingresá</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap { display: flex; justify-content: center; align-items: flex-start; padding-top: 2rem; }
.auth-card { width: 100%; max-width: 380px; }
.auth-title { font-size: 1.4rem; font-weight: 800; text-align: center; color: #1976d2; margin-bottom: .75rem; }
.auth-sub { text-align: center; color: #666; margin-bottom: 1rem; font-size: .9rem; }
.auth-btn { width: 100%; justify-content: center; margin-top: .25rem; text-decoration: none; }
.auth-error { color: #c62828; font-size: .85rem; margin: .5rem 0; }
.auth-hint { font-size: .78rem; color: #888; text-align: center; margin-top: .5rem; }
.auth-divider { display: flex; align-items: center; text-align: center; color: #999; margin: 1rem 0; font-size: .8rem; }
.auth-divider::before, .auth-divider::after { content: ''; flex: 1; border-bottom: 1px solid #e0e0e0; }
.auth-divider span { padding: 0 .75rem; }
.auth-done { text-align: center; }
.auth-done p:first-child { font-size: 1.1rem; font-weight: 700; margin-bottom: .5rem; }
.auth-foot { text-align: center; margin-top: 1.25rem; font-size: .85rem; color: #555; }
</style>
