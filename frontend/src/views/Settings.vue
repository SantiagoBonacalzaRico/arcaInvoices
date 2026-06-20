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
          y configurar un certificado digital. El asistente de abajo lo hace paso a paso.
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
        <button class="btn btn-outline btn-sm mt" @click="openCertWizard" :disabled="csrLoading">
          {{ csrLoading ? 'Generando…' : '🔐 Configurar certificado paso a paso' }}
        </button>
        <p v-if="certInlineError" class="error-msg">{{ certInlineError }}</p>
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

    <!-- AFIP certificate wizard modal -->
    <transition name="fade">
      <div v-if="showCertModal" class="modal-overlay" @click.self="showCertModal = false">
        <div class="modal-card">
          <button class="modal-close" @click="showCertModal = false" aria-label="Cerrar">✕</button>
          <h2 class="modal-title">Configurar certificado de ARCA</h2>
          <p class="hint">
            Seguí estos pasos para habilitar la búsqueda de razón social con el servicio
            oficial <code>ws_sr_padron_a13</code>.
          </p>

          <!-- Paso 1 -->
          <div class="wiz-step">
            <div class="wiz-head"><span class="wiz-num done">✓</span> <strong>Paso 1 — Generar pedido (CSR)</strong></div>
            <p class="hint">
              Listo: generamos tu clave privada y el archivo <code>request.csr</code> para tu CUIT
              <strong>{{ form.afip_cuit }}</strong>. La clave privada queda en tu equipo y nunca se comparte.
            </p>
            <a :href="downloadCsrUrl" class="btn btn-outline btn-sm" download>⬇ Descargar request.csr</a>
            <p class="hint" style="margin-top:.5rem">
              Usá <strong>siempre este botón</strong> para bajar el CSR (coincide con tu clave actual).
              <a href="#" @click.prevent="regenerateCsr">¿Empezar de cero? Regenerar clave y CSR</a>.
            </p>
          </div>

          <!-- Paso 2 -->
          <div class="wiz-step">
            <div class="wiz-head"><span class="wiz-num">2</span> <strong>Paso 2 — Subir el CSR a ARCA</strong></div>
            <ol class="wiz-list">
              <li>Entrá a <a href="https://auth.afip.gob.ar" target="_blank">auth.afip.gob.ar</a> con tu CUIT y Clave Fiscal (nivel 2 o superior).</li>
              <li>Abrí el servicio <strong>«Administrador de Certificados Digitales»</strong>.
                <span class="hint">Si no lo ves, agregalo desde «Administrador de Relaciones de Clave Fiscal» → Adherir servicio → ARCA.</span></li>
              <li>Hacé clic en <strong>«Agregar alias»</strong>, ponele un nombre (ej. <code>factura-siradig</code>) y subí el archivo <code>request.csr</code> que descargaste.</li>
              <li><strong>Descargá</strong> el certificado que te genera ARCA (archivo <code>.crt</code> / <code>.pem</code>).</li>
            </ol>
          </div>

          <!-- Paso 3 -->
          <div class="wiz-step">
            <div class="wiz-head"><span class="wiz-num" :class="{ done: certUploaded }">{{ certUploaded ? '✓' : '3' }}</span> <strong>Paso 3 — Subir el certificado (.crt)</strong></div>
            <p class="hint">Elegí el archivo <code>.crt</code> que descargaste de ARCA:</p>
            <input type="file" accept=".crt,.pem,.cer,.txt" @change="onCertFile" />
            <button class="btn btn-primary btn-sm mt" :disabled="!certPem || uploadingCert" @click="uploadCertFile">
              {{ uploadingCert ? 'Subiendo…' : 'Subir certificado' }}
            </button>
            <p v-if="certUploadMsg" :class="certUploadMsg.error ? 'error-msg' : 'ok-msg'">{{ certUploadMsg.text }}</p>
          </div>

          <!-- Paso 4 -->
          <div class="wiz-step">
            <div class="wiz-head"><span class="wiz-num">4</span> <strong>Paso 4 — Autorizar el servicio y probar</strong></div>
            <p class="hint">
              En ARCA → <strong>«Administrador de Relaciones de Clave Fiscal»</strong>, autorizá el
              servicio <code>ws_sr_padron_a13</code> («Padrón ARCA Alcance 13») para tu CUIT,
              vinculado a este certificado. Luego probá una búsqueda:
            </p>
            <div class="test-row">
              <input v-model="testCuit" placeholder="CUIT a consultar (ej. 30-58962149-9)" />
              <button class="btn btn-outline btn-sm" :disabled="!testCuit || testingLookup" @click="testLookup">
                {{ testingLookup ? 'Consultando…' : 'Probar búsqueda' }}
              </button>
            </div>
            <p v-if="lookupResult"
               :class="lookupResult.ok ? 'ok-msg' : 'error-msg'">
              {{ lookupResult.ok
                  ? `✓ ${lookupResult.razon_social}  (fuente: ${lookupResult.source})`
                  : `✕ ${lookupResult.error}` }}
            </p>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  getSettings, updateSettings, testNotification,
  generateCsr, uploadCert, downloadCsrUrl, diagnoseCuit, pickFolder as pickFolderApi,
} from '../api'

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

// ── AFIP certificate wizard ──────────────────────────────────────────────────
const showCertModal  = ref(false)
const csrLoading     = ref(false)
const certInlineError = ref('')
const certPem        = ref('')
const certUploaded   = ref(false)
const uploadingCert  = ref(false)
const certUploadMsg  = ref(null)
const testCuit       = ref('')
const testingLookup  = ref(false)
const lookupResult   = ref(null)

async function openCertWizard() {
  certInlineError.value = ''
  if (!form.afip_cuit) {
    certInlineError.value = 'Ingresá tu CUIT arriba antes de generar el certificado.'
    return
  }
  csrLoading.value = true
  try {
    // Persist the CUIT first so the CSR is tied to it, then generate the CSR.
    await updateSettings({ ...form })
    await generateCsr()
    showCertModal.value = true
  } catch (e) {
    certInlineError.value = e.response?.data?.detail || 'No se pudo generar el CSR.'
  } finally {
    csrLoading.value = false
  }
}

async function regenerateCsr() {
  if (!confirm('Esto crea una NUEVA clave privada. El certificado que ya tengas registrado en ARCA dejará de servir y tendrás que registrar el CSR nuevo. ¿Continuar?')) return
  csrLoading.value = true
  try {
    await generateCsr(true)
    certUploaded.value = false
    certUploadMsg.value = null
    lookupResult.value = null
    alert('Clave y CSR regenerados. Descargá el nuevo request.csr y registralo en ARCA.')
  } catch (e) {
    certInlineError.value = e.response?.data?.detail || 'No se pudo regenerar el CSR.'
  } finally {
    csrLoading.value = false
  }
}

function onCertFile(e) {
  const file = e.target.files?.[0]
  certUploadMsg.value = null
  if (!file) { certPem.value = ''; return }
  const reader = new FileReader()
  reader.onload = () => { certPem.value = String(reader.result || '') }
  reader.readAsText(file)
}

async function uploadCertFile() {
  uploadingCert.value = true
  certUploadMsg.value = null
  try {
    await uploadCert(certPem.value)
    certUploaded.value = true
    certUploadMsg.value = { text: 'Certificado subido correctamente.', error: false }
    await load()
  } catch (e) {
    certUploadMsg.value = { text: e.response?.data?.detail || 'Certificado inválido.', error: true }
  } finally {
    uploadingCert.value = false
  }
}

async function testLookup() {
  testingLookup.value = true
  lookupResult.value = null
  try {
    const { data } = await diagnoseCuit(testCuit.value)
    lookupResult.value = data
  } catch (e) {
    lookupResult.value = { ok: false, error: e.response?.data?.detail || e.message }
  } finally {
    testingLookup.value = false
  }
}

async function pickFolder() {
  pickingFolder.value = true
  folderError.value = ''
  try {
    const { data } = await pickFolderApi()
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

/* AFIP certificate wizard modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.45);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 2rem 1rem; z-index: 1000; overflow-y: auto;
}
.modal-card {
  background: #fff; border-radius: 14px; padding: 1.5rem 1.75rem;
  max-width: 620px; width: 100%; position: relative;
  box-shadow: 0 12px 40px rgba(0,0,0,.25);
}
.modal-close {
  position: absolute; top: .9rem; right: 1rem; border: none; background: transparent;
  font-size: 1.1rem; cursor: pointer; color: #888; line-height: 1;
}
.modal-close:hover { color: #333; }
.modal-title { font-size: 1.2rem; font-weight: 700; margin-bottom: .35rem; }
.wiz-step {
  border: 1px solid #e6e8ee; border-radius: 10px;
  padding: .9rem 1rem; margin-top: .9rem;
}
.wiz-head { display: flex; align-items: center; gap: .5rem; margin-bottom: .4rem; font-size: .95rem; }
.wiz-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  background: #e7ebf3; color: #445; font-size: .8rem; font-weight: 700; flex-shrink: 0;
}
.wiz-num.done { background: #d6f0dd; color: #1a7f37; }
.wiz-list { margin: .25rem 0 0 1.1rem; padding: 0; font-size: .85rem; color: #555; }
.wiz-list li { margin-bottom: .4rem; }
.wiz-list .hint { display: block; margin: .15rem 0 0; }
.test-row { display: flex; gap: .5rem; flex-wrap: wrap; }
.test-row input { flex: 1 1 220px; }
</style>
