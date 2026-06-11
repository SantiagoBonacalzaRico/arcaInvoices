<template>
  <div>
    <h1 class="page-title">Configuración</h1>

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
        Cuitalizer es una API argentina que devuelve la razón social de un CUIT automáticamente.
        Con el plan gratuito tenés 10 consultas por mes (suficiente para uso personal — los resultados se cachean localmente).
        Obtené tu clave en <a href="https://cuitalizer.com.ar" target="_blank">cuitalizer.com.ar</a>.
        Si no configurás una clave, la búsqueda usará el servicio oficial de AFIP (requiere certificado WSAA).
      </p>
      <div class="form-group">
        <label>Cuitalizer API Key <span class="optional">(opcional)</span></label>
        <input v-model="form.cuitalizer_api_key" placeholder="ctlz_..." />
      </div>
    </div>

    <!-- AFIP certificate wizard -->
    <div class="card">
      <h2>Integración AFIP/ARCA</h2>
      <div class="form-group">
        <label>CUIT</label>
        <input v-model="form.afip_cuit" placeholder="20-12345678-9" />
      </div>
      <label class="toggle-label">
        <input type="checkbox" v-model="form.afip_production" /> Usar entorno de producción
      </label>

      <div class="setup-wizard" v-if="guide">
        <h3>Configuración del certificado digital</h3>
        <p class="hint">
          El WSDL de SiRADIG – Trabajador está especificado en
          <a href="https://www.afip.gob.ar/572web/documentos/ManualSiRADIG.pdf" target="_blank">ManualSiRADIG.pdf v1.19</a>.
          Descargalo, obtené las URLs de WSDL y configurá las variables
          <code>AFIP_SIRADIG_HOMO_WSDL</code> / <code>AFIP_SIRADIG_PROD_WSDL</code> en el archivo <code>.env</code>.
        </p>
        <div class="steps">
          <div v-for="step in guide.steps" :key="step.index"
               :class="['step', { done: step.done, current: step.index === guide.current_step }]">
            <span class="step-icon">{{ step.done ? '✅' : (step.index === guide.current_step ? '➡️' : '⬜') }}</span>
            <span>{{ step.description }}</span>
          </div>
        </div>

        <div class="wizard-actions">
          <button
            v-if="guide.current_step === 2 || (!csrPem && guide.current_step <= 3)"
            class="btn btn-outline btn-sm"
            @click="generateCsr"
            :disabled="generatingCsr"
          >
            {{ generatingCsr ? 'Generando…' : 'Generar par de claves (CSR)' }}
          </button>
          <a v-if="csrPem || guide.current_step >= 3"
             :href="downloadCsrUrl"
             class="btn btn-outline btn-sm"
             download="request.csr">
            Descargar request.csr
          </a>
          <div v-if="guide.current_step >= 4" class="form-group mt">
            <label>Pegar contenido del certificado (.crt) de AFIP</label>
            <textarea v-model="certPem" rows="6" class="cert-textarea" placeholder="-----BEGIN CERTIFICATE-----&#10;..."></textarea>
            <button class="btn btn-primary btn-sm mt" @click="uploadCert" :disabled="uploadingCert">
              {{ uploadingCert ? 'Guardando…' : 'Subir certificado' }}
            </button>
          </div>
          <button
            v-if="guide.current_step >= 6"
            class="btn btn-primary btn-sm mt"
            @click="verifyConn"
            :disabled="verifying"
          >
            {{ verifying ? 'Verificando…' : 'Verificar conexión WSAA' }}
          </button>
        </div>
        <p v-if="wizardMsg" :class="wizardMsg.error ? 'error-msg' : 'ok-msg'">{{ wizardMsg.text }}</p>
      </div>
    </div>

    <!-- Save button -->
    <div class="form-actions">
      <button class="btn btn-primary" @click="save" :disabled="saving">
        {{ saving ? 'Guardando…' : 'Guardar configuración' }}
      </button>
    </div>
    <p v-if="saveMsg" :class="saveMsg.error ? 'error-msg' : 'ok-msg'">{{ saveMsg.text }}</p>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import {
  getSettings, updateSettings, getAfipSetupGuide,
  generateCsr as apiGenerateCsr, downloadCsrUrl,
  uploadCert as apiUploadCert, verifyAfipConnection,
  testNotification,
} from '../api'

const form = reactive({
  invoice_dir: '', sync_day_of_month: 20, notification_days_before: 5,
  min_invoice_threshold: 3, notify_email: true, notify_sms: false,
  email_address: '', smtp_host: '', smtp_port: 587, smtp_user: '', smtp_password: '',
  phone_number: '', afip_cuit: '', afip_production: false, cuitalizer_api_key: '',
})

const guide = ref(null)
const csrPem = ref('')
const pickingFolder = ref(false)
const folderError = ref('')
const certPem = ref('')
const saving = ref(false)
const saveMsg = ref(null)
const generatingCsr = ref(false)
const uploadingCert = ref(false)
const verifying = ref(false)
const wizardMsg = ref(null)
const testingNotif = ref(false)
const notifResult = ref(null)

async function pickFolder() {
  pickingFolder.value = true
  folderError.value = ''
  try {
    const res = await updateSettings({}) // warm-up axios instance (no-op)
    const { data } = await axios.post('/api/settings/pick-folder')
    if (data?.path) form.invoice_dir = data.path
  } catch (e) {
    if (e.response?.status === 204) return // user cancelled — no error shown
    folderError.value = 'No se pudo abrir el selector de carpetas.'
  } finally {
    pickingFolder.value = false
  }
}

async function load() {
  const [s, g] = await Promise.all([getSettings(), getAfipSetupGuide()])
  Object.assign(form, s.data)
  guide.value = g.data
}

async function save() {
  saving.value = true; saveMsg.value = null
  try {
    await updateSettings({ ...form })
    saveMsg.value = { text: 'Configuración guardada.', error: false }
    await load()
  } catch (e) {
    saveMsg.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally { saving.value = false }
}

async function generateCsr() {
  if (!form.afip_cuit) { alert('Ingresá el CUIT antes de generar el certificado.'); return }
  await updateSettings({ afip_cuit: form.afip_cuit })
  generatingCsr.value = true; wizardMsg.value = null
  try {
    const res = await apiGenerateCsr()
    csrPem.value = res.data.csr_pem
    wizardMsg.value = { text: res.data.message, error: false }
    await load()
  } catch (e) {
    wizardMsg.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally { generatingCsr.value = false }
}

async function uploadCert() {
  uploadingCert.value = true; wizardMsg.value = null
  try {
    await apiUploadCert(certPem.value)
    wizardMsg.value = { text: 'Certificado guardado correctamente.', error: false }
    await load()
  } catch (e) {
    wizardMsg.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally { uploadingCert.value = false }
}

async function verifyConn() {
  verifying.value = true; wizardMsg.value = null
  try {
    const res = await verifyAfipConnection()
    wizardMsg.value = {
      text: res.data.status === 'ok' ? '✅ Conexión WSAA exitosa.' : '❌ Falló la conexión.',
      error: res.data.status !== 'ok',
    }
    await load()
  } catch (e) {
    wizardMsg.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally { verifying.value = false }
}

async function testNotif() {
  testingNotif.value = true; notifResult.value = null
  try {
    const res = await testNotification()
    notifResult.value = { text: JSON.stringify(res.data), error: false }
  } catch (e) {
    notifResult.value = { text: e.response?.data?.detail || e.message, error: true }
  } finally { testingNotif.value = false }
}

onMounted(load)
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 1.25rem; }
h2 { font-size: 1.05rem; font-weight: 700; margin-bottom: 1rem; color: #333; }
h3 { font-size: .95rem; font-weight: 700; margin: 1rem 0 .5rem; }
.form-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .5rem 1rem; }
.toggle-row { display: flex; gap: 1.5rem; margin-bottom: 1rem; }
.toggle-label { display: flex; align-items: center; gap: .4rem; font-size: .9rem; font-weight: 600; cursor: pointer; }
.hint { font-size: .8rem; color: #666; margin: .4rem 0; }
.hint a { color: #1976d2; }
.hint code { background: #f0f0f0; padding: .1rem .3rem; border-radius: 3px; font-size: .78rem; }
.setup-wizard { background: #f8f9ff; border-radius: 8px; padding: 1rem; margin-top: 1rem; }
.steps { display: flex; flex-direction: column; gap: .5rem; margin: .75rem 0; }
.step { display: flex; align-items: flex-start; gap: .5rem; font-size: .88rem; padding: .4rem .6rem; border-radius: 6px; }
.step.done { opacity: .6; }
.step.current { background: #e3f2fd; font-weight: 600; }
.step-icon { font-size: 1rem; flex-shrink: 0; }
.wizard-actions { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: .75rem; align-items: flex-start; flex-direction: column; }
.cert-textarea { width: 100%; padding: .6rem; border: 1.5px solid #d0d7de; border-radius: 8px; font-family: monospace; font-size: .8rem; resize: vertical; }
.form-actions { display: flex; justify-content: flex-end; margin-top: 1rem; }
.btn-sm { padding: .35rem .8rem; font-size: .82rem; }
.mt { margin-top: .5rem; }
.folder-row { display: flex; gap: .5rem; align-items: center; }
.folder-input { flex: 1; background: #f9f9f9; cursor: default; }
.folder-btn { white-space: nowrap; flex-shrink: 0; }
.optional { font-size: .75rem; color: #888; font-weight: 400; margin-left: .3rem; }
.ok-msg { color: #2e7d32; font-size: .85rem; margin-top: .5rem; }
.error-msg { color: #b71c1c; font-size: .85rem; margin-top: .5rem; }
</style>
