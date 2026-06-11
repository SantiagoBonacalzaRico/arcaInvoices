<template>
  <div ref="pageTop">
    <h1 class="page-title">Configuración</h1>

    <!-- Success banner -->
    <transition name="fade">
      <div v-if="saveMsg && !saveMsg.error" class="banner-success">
        ✅ Configuración guardada correctamente.
      </div>
    </transition>

    <!-- General settings -->
    <div class="card">
      <h2>General</h2>
      <div class="form-group">
        <label>Directorio de facturas</label>
        <div class="folder-row">
          <input v-model="form.invoice_dir" placeholder="data/invoices" class="folder-input" readonly />
          <button type="button" class="btn btn-outline folder-btn" @click="pickFolder" :disabled="pickingFolder">
            {{ pickingFolder ? '…' : '📁 Seleccionar' }}
          </button>
        </div>
        <p v-if="folderError" class="error-msg">{{ folderError }}</p>
      </div>
    </div>

    <!-- Sync schedule -->
    <div class="card">
      <h2>Sincronización con ARCA</h2>
      <div class="form-row">
        <div class="form-group">
          <label>Día del mes para sincronizar (1–28)</label>
          <input v-model.number="form.sync_day_of_month" type="number" min="1" max="28" />
        </div>
        <div class="form-group">
          <label>Notificar X días antes</label>
          <input v-model.number="form.notification_days_before" type="number" min="1" max="27" />
        </div>
        <div class="form-group">
          <label>Mínimo de facturas esperadas</label>
          <input v-model.number="form.min_invoice_threshold" type="number" min="0" />
        </div>
      </div>
    </div>

    <!-- Notifications -->
    <div class="card">
      <h2>Notificaciones</h2>
      <div class="toggle-row">
        <label class="toggle-label">
          <input type="checkbox" v-model="form.notify_email" /> Email
        </label>
        <label class="toggle-label">
          <input type="checkbox" v-model="form.notify_sms" /> SMS (Twilio)
        </label>
      </div>
      <template v-if="form.notify_email">
        <div class="form-row">
          <div class="form-group"><label>Correo</label><input v-model="form.email_address" type="email" /></div>
          <div class="form-group"><label>SMTP host</label><input v-model="form.smtp_host" placeholder="smtp.gmail.com" /></div>
          <div class="form-group"><label>SMTP puerto</label><input v-model.number="form.smtp_port" type="number" placeholder="587" /></div>
          <div class="form-group"><label>Usuario SMTP</label><input v-model="form.smtp_user" /></div>
          <div class="form-group"><label>Contraseña SMTP</label><input v-model="form.smtp_password" type="password" /></div>
        </div>
      </template>
      <template v-if="form.notify_sms">
        <div class="form-group"><label>Número de teléfono</label><input v-model="form.phone_number" placeholder="+54911..." /></div>
        <p class="hint">Configurá TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_FROM_NUMBER como variables de entorno.</p>
      </template>
      <button class="btn btn-outline btn-sm mt" @click="testNotif" :disabled="testingNotif">
        {{ testingNotif ? 'Enviando…' : 'Enviar notificación de prueba' }}
      </button>
      <p v-if="notifResult" :class="notifResult.error ? 'error-msg' : 'ok-msg'">{{ notifResult.text }}</p>
    </div>

    <!-- Razón Social lookup -->
    <div class="card">
      <h2>Búsqueda de Razón Social por CUIT</h2>
      <p class="hint">
        La app puede buscar automáticamente el nombre de un proveedor a partir de su CUIT.
        Elegí una de las dos opciones:
      </p>
      <div class="option-block">
        <strong>Opción A — Cuitalizer</strong> <span class="optional">(recomendado, sin certificado AFIP)</span>
        <p class="hint">
          Plan gratuito: 10 consultas/mes. Los resultados se cachean, suficiente para uso personal.
          Obtené tu clave en <a href="https://cuitalizer.com.ar" target="_blank">cuitalizer.com.ar</a>.
        </p>
        <div class="form-group">
          <label>Cuitalizer API Key <span class="optional">(opcional)</span></label>
          <input v-model="form.cuitalizer_api_key" placeholder="ctlz_..." />
        </div>
      </div>
      <div class="option-block">
        <strong>Opción B — Padrón oficial de ARCA</strong> <span class="optional">(requiere CUIT)</span>
        <p class="hint">
          Usa el servicio <code>ws_sr_padron_a13</code> de ARCA. Requiere ingresar tu CUIT
          y tener el certificado digital configurado en el servidor (ver README).
        </p>
        <div class="form-row">
          <div class="form-group">
            <label>Tu CUIT</label>
            <input v-model="form.afip_cuit" placeholder="20-12345678-9" />
          </div>
          <div class="form-group" style="display:flex;align-items:flex-end;">
            <label class="toggle-label" style="margin-bottom:.6rem">
              <input type="checkbox" v-model="form.afip_production" /> Usar entorno de producción
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- Save button -->
    <div class="form-actions">
      <button class="btn btn-primary" @click="save" :disabled="saving">
        {{ saving ? 'Guardando…' : 'Guardar configuración' }}
      </button>
    </div>
    <p v-if="saveMsg?.error" class="error-msg" style="text-align:right;margin-top:.5rem">
      {{ saveMsg.text }}
    </p>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import { getSettings, updateSettings, testNotification } from '../api'

const pageTop = ref(null)

const form = reactive({
  invoice_dir: '', sync_day_of_month: 20, notification_days_before: 5,
  min_invoice_threshold: 3, notify_email: true, notify_sms: false,
  email_address: '', smtp_host: '', smtp_port: 587, smtp_user: '', smtp_password: '',
  phone_number: '', afip_cuit: '', afip_production: false, cuitalizer_api_key: '',
})

const pickingFolder = ref(false)
const folderError   = ref('')
const saving        = ref(false)
const saveMsg       = ref(null)
const testingNotif  = ref(false)
const notifResult   = ref(null)

async function pickFolder() {
  pickingFolder.value = true
  folderError.value = ''
  try {
    const { data } = await axios.post('/api/settings/pick-folder')
    if (data?.path) form.invoice_dir = data.path
  } catch (e) {
    if (e.response?.status === 204) return
    folderError.value = 'No se pudo abrir el selector de carpetas.'
  } finally {
    pickingFolder.value = false
  }
}

async function load() {
  const { data } = await getSettings()
  Object.assign(form, data)
}

async function save() {
  saving.value = true
  saveMsg.value = null
  try {
    await updateSettings({ ...form })
    saveMsg.value = { text: 'OK', error: false }
    await load()
    // Scroll to top so the user sees the success banner
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    saveMsg.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally {
    saving.value = false
    // Auto-hide the success banner after 4 s
    if (!saveMsg.value?.error) {
      setTimeout(() => { saveMsg.value = null }, 4000)
    }
  }
}

async function testNotif() {
  testingNotif.value = true
  notifResult.value = null
  try {
    const res = await testNotification()
    notifResult.value = { text: JSON.stringify(res.data), error: false }
  } catch (e) {
    notifResult.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally {
    testingNotif.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 1.25rem; }
h2 { font-size: 1.05rem; font-weight: 700; margin-bottom: 1rem; color: #333; }

/* Success banner */
.banner-success {
  background: #e8f5e9;
  color: #2e7d32;
  border: 1.5px solid #a5d6a7;
  border-radius: 10px;
  padding: .85rem 1.25rem;
  font-weight: 600;
  margin-bottom: 1rem;
}
.fade-enter-active, .fade-leave-active { transition: opacity .4s, transform .4s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-6px); }

.form-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .5rem 1rem; }
.toggle-row { display: flex; gap: 1.5rem; margin-bottom: 1rem; }
.toggle-label { display: flex; align-items: center; gap: .4rem; font-size: .9rem; font-weight: 600; cursor: pointer; }

.option-block { background: #f8f9ff; border-radius: 8px; padding: 1rem; margin-top: .75rem; }
.option-block + .option-block { margin-top: .5rem; }

.hint { font-size: .8rem; color: #666; margin: .35rem 0 .5rem; }
.hint a { color: #1976d2; }
.hint code { background: #f0f0f0; padding: .1rem .3rem; border-radius: 3px; font-size: .78rem; }

.folder-row { display: flex; gap: .5rem; align-items: center; }
.folder-input { flex: 1; background: #f9f9f9; cursor: default; }
.folder-btn { white-space: nowrap; flex-shrink: 0; }

.form-actions { display: flex; justify-content: flex-end; margin-top: 1rem; }
.btn-sm { padding: .35rem .8rem; font-size: .82rem; }
.mt { margin-top: .5rem; }
.optional { font-size: .75rem; color: #888; font-weight: 400; margin-left: .3rem; }
.ok-msg   { color: #2e7d32; font-size: .85rem; margin-top: .5rem; }
.error-msg { color: #b71c1c; font-size: .85rem; margin-top: .5rem; }
</style>
