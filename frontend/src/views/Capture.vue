<template>
  <div>
    <h1 class="page-title">Escanear factura</h1>

    <!-- Step 1: Choose image -->
    <div class="card" v-if="step === 'pick'">
      <div class="upload-zone" @click="$refs.fileInput.click()" @dragover.prevent @drop.prevent="onDrop">
        <div class="upload-icon">📷</div>
        <p>Sacá una foto o seleccioná una imagen</p>
        <p class="muted small">JPEG, PNG, WEBP — máx 20 MB</p>
      </div>
      <input ref="fileInput" type="file" accept="image/*" capture="environment" hidden @change="onFile" />
      <button class="btn btn-primary mt" @click="$refs.fileInput.click()">Seleccionar imagen</button>
    </div>

    <!-- Step 2: Preview + OCR progress -->
    <div class="card" v-if="step === 'scanning'">
      <img :src="previewUrl" class="preview-img" />
      <div class="scanning-label">Procesando imagen con OCR…</div>
      <div class="spinner"></div>
    </div>

    <!-- Step 3: Confirm / correct fields -->
    <div class="card" v-if="step === 'confirm'">
      <div class="preview-row">
        <img :src="previewUrl" class="preview-thumb" />
        <div class="ocr-fields">
          <div v-for="f in fieldDefs" :key="f.key" class="form-group">
            <label>
              {{ f.label }}
              <span v-if="isUnrecognized(f.key)" class="unrecognized-tag">⚠️ No detectado</span>
              <span v-else class="confidence-tag">{{ confLabel(f.key) }}</span>
            </label>
            <input
              v-model="form[f.key]"
              :type="f.type || 'text'"
              :placeholder="f.placeholder"
              :class="{ 'field-warn': isUnrecognized(f.key) }"
            />
          </div>
          <div class="form-group">
            <label>Categoría</label>
            <select v-model="form.category">
              <option value="">— Seleccionar —</option>
              <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-outline" @click="reset">Cancelar</button>
        <button class="btn btn-primary" @click="save" :disabled="saving">
          {{ saving ? 'Guardando…' : 'Guardar factura' }}
        </button>
      </div>
      <p v-if="saveError" class="error-msg">{{ saveError }}</p>
    </div>

    <!-- Step 4: Done -->
    <div class="card center" v-if="step === 'done'">
      <div class="done-icon">✅</div>
      <p class="done-msg">Factura guardada correctamente.</p>
      <div class="form-actions">
        <button class="btn btn-outline" @click="reset">Escanear otra</button>
        <router-link to="/invoices" class="btn btn-primary">Ver facturas</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { scanInvoice, saveImage, createInvoice, recordCorrection } from '../api'

const step = ref('pick')       // pick | scanning | confirm | done
const previewUrl = ref('')
const ocrResult = ref(null)
const imagePath = ref('')
const saving = ref(false)
const saveError = ref('')

const form = reactive({
  cuit: '', invoice_date: '', invoice_number: '', total_amount: '', category: '',
})

const fieldDefs = [
  { key: 'cuit',           label: 'CUIT del emisor',     placeholder: '20-12345678-9' },
  { key: 'invoice_date',   label: 'Fecha',               placeholder: 'AAAA-MM-DD', type: 'date' },
  { key: 'invoice_number', label: 'Nro. comprobante',    placeholder: '0001-00012345' },
  { key: 'total_amount',   label: 'Total ($)',            placeholder: '1234.56', type: 'number' },
]

const categories = [
  'Gastos médicos y paramédicos',
  'Gastos de educación',
  'Servicio doméstico',
  'Alquileres',
  'Seguro de vida',
  'Donaciones',
  'Otros',
]

function isUnrecognized(key) {
  return ocrResult.value?.unrecognized_fields?.includes(key)
}

function confLabel(key) {
  const conf = ocrResult.value?.[key]?.confidence
  if (conf === undefined || conf >= 0.9) return ''
  return `(${Math.round(conf * 100)}%)`
}

function onDrop(e) {
  const file = e.dataTransfer.files[0]
  if (file) processFile(file)
}

function onFile(e) {
  const file = e.target.files[0]
  if (file) processFile(file)
}

async function processFile(file) {
  previewUrl.value = URL.createObjectURL(file)
  step.value = 'scanning'
  try {
    const [ocrRes, imgRes] = await Promise.all([
      scanInvoice(file),
      saveImage(file),
    ])
    ocrResult.value = ocrRes.data
    imagePath.value = imgRes.data.image_path
    // Pre-fill form
    form.cuit           = ocrRes.data.cuit?.value           || ''
    form.invoice_date   = ocrRes.data.invoice_date?.value   || ''
    form.invoice_number = ocrRes.data.invoice_number?.value || ''
    form.total_amount   = ocrRes.data.total_amount?.value   || ''
    step.value = 'confirm'
  } catch (err) {
    alert('Error procesando imagen: ' + (err.response?.data?.detail || err.message))
    reset()
  }
}

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    // Record corrections for any unrecognized fields the user filled in
    const corrections = (ocrResult.value?.unrecognized_fields || [])
      .filter(f => form[f])
      .map(f => recordCorrection({
        field_name: f,
        correct_value: form[f],
        image_hash: ocrResult.value?.image_hash,
        raw_snippet: ocrResult.value?.raw_text?.slice(0, 200),
      }))
    await Promise.allSettled(corrections)

    await createInvoice({
      cuit: form.cuit,
      invoice_date: form.invoice_date,
      invoice_number: form.invoice_number,
      total_amount: parseFloat(form.total_amount),
      category: form.category || null,
      image_path: imagePath.value,
      raw_ocr_text: ocrResult.value?.raw_text,
    })
    step.value = 'done'
  } catch (err) {
    saveError.value = err.response?.data?.detail || err.message
  } finally {
    saving.value = false
  }
}

function reset() {
  step.value = 'pick'
  previewUrl.value = ''
  ocrResult.value = null
  imagePath.value = ''
  Object.keys(form).forEach(k => (form[k] = ''))
  saveError.value = ''
}
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 1.25rem; }
.upload-zone {
  border: 2.5px dashed #90caf9;
  border-radius: 12px;
  padding: 2.5rem;
  text-align: center;
  cursor: pointer;
  transition: background .15s;
}
.upload-zone:hover { background: #e3f2fd; }
.upload-icon { font-size: 3rem; margin-bottom: .5rem; }
.muted { color: #888; }
.small { font-size: .8rem; }
.mt { margin-top: 1rem; }
.preview-img { width: 100%; max-height: 300px; object-fit: contain; border-radius: 8px; margin-bottom: 1rem; }
.scanning-label { text-align: center; margin-bottom: .75rem; font-weight: 600; }
.spinner {
  width: 40px; height: 40px; border: 4px solid #e3f2fd;
  border-top-color: #1976d2; border-radius: 50%;
  animation: spin .7s linear infinite; margin: 0 auto;
}
@keyframes spin { to { transform: rotate(360deg) } }
.preview-row { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.preview-thumb { width: 140px; height: 140px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.ocr-fields { flex: 1; min-width: 220px; }
.unrecognized-tag { background: #fff3e0; color: #e65100; font-size: .72rem; font-weight: 700; padding: .1rem .4rem; border-radius: 4px; margin-left: .4rem; }
.confidence-tag { color: #aaa; font-size: .75rem; margin-left: .3rem; }
.field-warn { border-color: #ff9800 !important; }
.form-actions { display: flex; gap: 1rem; justify-content: flex-end; margin-top: 1rem; flex-wrap: wrap; }
.error-msg { color: #b71c1c; font-size: .85rem; margin-top: .5rem; }
.center { text-align: center; }
.done-icon { font-size: 3rem; margin-bottom: .5rem; }
.done-msg { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
</style>
