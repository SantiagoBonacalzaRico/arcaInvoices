<script setup>
import { ref } from 'vue'
import { forgotPassword } from '../api'

const email = ref('')
const error = ref('')
const loading = ref(false)
const sent = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await forgotPassword(email.value.trim())
    sent.value = true
  } catch (e) {
    error.value = e?.response?.data?.detail || 'No se pudo enviar el correo. Probá de nuevo.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="card auth-card">
      <h1 class="auth-title">Restablecer contraseña</h1>

      <div v-if="sent" class="auth-center">
        <p class="auth-ok">✅ Si ese email tiene una cuenta, te enviamos un enlace para crear una nueva contraseña.</p>
        <p class="auth-sub">Revisá tu bandeja de entrada (y el correo no deseado). El enlace vence en 2 horas.</p>
        <router-link class="btn btn-primary auth-btn" to="/login">Volver a ingresar</router-link>
      </div>

      <template v-else>
        <p class="auth-sub">Ingresá tu email y te mandamos un enlace para elegir una nueva contraseña.</p>
        <form @submit.prevent="submit">
          <div class="form-group">
            <label>Email</label>
            <input v-model="email" type="email" autocomplete="email" required />
          </div>

          <p v-if="error" class="auth-error">{{ error }}</p>

          <button class="btn btn-primary auth-btn" type="submit" :disabled="loading">
            {{ loading ? 'Enviando…' : 'Enviar enlace' }}
          </button>
        </form>

        <p class="auth-foot">
          <router-link to="/login">Volver a ingresar</router-link>
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.auth-wrap { display: flex; justify-content: center; align-items: flex-start; padding-top: 3rem; }
.auth-card { width: 100%; max-width: 380px; }
.auth-title { font-size: 1.3rem; font-weight: 800; text-align: center; color: #1976d2; }
.auth-sub { text-align: center; color: #666; margin: .5rem 0 1.25rem; font-size: .9rem; }
.auth-btn { width: 100%; justify-content: center; margin-top: .25rem; text-decoration: none; }
.auth-error { color: #c62828; font-size: .85rem; margin: .5rem 0; }
.auth-ok { font-size: 1rem; font-weight: 700; color: #2e7d32; margin-bottom: .5rem; text-align: center; }
.auth-foot { text-align: center; margin-top: 1.25rem; font-size: .85rem; color: #555; }
.auth-center { display: flex; flex-direction: column; gap: .5rem; text-align: center; }
</style>
