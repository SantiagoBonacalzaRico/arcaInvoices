<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { resetPassword } from '../api'

const route = useRoute()
const token = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)
const done = ref(false)

onMounted(() => {
  token.value = String(route.query.token || '')
  if (!token.value) error.value = 'Falta el token de restablecimiento.'
})

const tooShort = computed(() => password.value.length > 0 && password.value.length < 8)
const mismatch = computed(() => confirm.value.length > 0 && password.value !== confirm.value)
const canSubmit = computed(
  () => token.value && password.value.length >= 8 && password.value === confirm.value && !loading.value,
)

async function submit() {
  error.value = ''
  if (!canSubmit.value) return
  loading.value = true
  try {
    await resetPassword(token.value, password.value)
    done.value = true
  } catch (e) {
    error.value = e?.response?.data?.detail || 'No se pudo restablecer la contraseña.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="card auth-card">
      <h1 class="auth-title">Nueva contraseña</h1>

      <div v-if="done" class="auth-center">
        <p class="auth-ok">✅ ¡Tu contraseña fue actualizada!</p>
        <router-link class="btn btn-primary auth-btn" to="/login">Ingresar</router-link>
      </div>

      <template v-else>
        <p class="auth-sub">Elegí una nueva contraseña para tu cuenta.</p>
        <form @submit.prevent="submit">
          <div class="form-group">
            <label>Nueva contraseña</label>
            <input v-model="password" type="password" autocomplete="new-password" required minlength="8" />
            <small v-if="tooShort" class="hint">Mínimo 8 caracteres.</small>
          </div>
          <div class="form-group">
            <label>Repetir contraseña</label>
            <input v-model="confirm" type="password" autocomplete="new-password" required />
            <small v-if="mismatch" class="hint">Las contraseñas no coinciden.</small>
          </div>

          <p v-if="error" class="auth-error">{{ error }}</p>

          <button class="btn btn-primary auth-btn" type="submit" :disabled="!canSubmit">
            {{ loading ? 'Guardando…' : 'Guardar contraseña' }}
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
.auth-ok { font-size: 1.1rem; font-weight: 700; color: #2e7d32; margin-bottom: 1rem; text-align: center; }
.auth-foot { text-align: center; margin-top: 1.25rem; font-size: .85rem; color: #555; }
.auth-center { display: flex; flex-direction: column; gap: .5rem; text-align: center; }
.hint { color: #c62828; font-size: .78rem; }
</style>
