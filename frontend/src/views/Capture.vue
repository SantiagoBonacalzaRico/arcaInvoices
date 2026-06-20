<template>
  <div>
    <h1 class="page-title">Escanear factura</h1>

    <!-- Step 1: Choose images -->
    <div class="card" v-if="step === 'pick'">
      <div
        class="upload-zone"
        @dragover.prevent
        @drop.prevent="onDrop"
        @click="$refs.galleryInput.click()"
      >
        <div class="upload-icon">📷</div>
        <p>Arrastrá imágenes aquí o usá los botones de abajo</p>
        <p class="muted small">JPEG, PNG, WEBP — máx 20 MB por imagen</p>
      </div>

      <!-- Hidden inputs -->
      <input ref="cameraInput"  type="file" accept="image/*" capture="environment" hidden @change="onCameraFile" />
      <input ref="galleryInput" type="file" accept="image/*" multiple            hidden @change="onGalleryFiles" />

      <div class="pick-buttons">
        <button class="btn btn-outline" @click.stop="native ? takePhoto() : $refs.cameraInput.click()">📷 Sacar foto</button>
        <button class="btn btn-outline" @click.stop="$refs.galleryInput.click()">🖼 Elegir archivos</button>
      </div>

      <p class="tip-note">💡 Si el ticket es muy largo te recomendamos tomar más de una foto para que sea más nítido.</p>

      <!-- Thumbnails of already-added images -->
      <div v-if="selectedFiles.length" class="thumb-grid">
        <div v-for="(url, i) in previewUrls" :key="i" class="thumb-item">
          <img :src="url" class="thumb-img" />
          <button class="thumb-remove" @click="removeFile(i)" title="Eliminar">✕</button>
        </div>
      </div>

      <div class="form-actions">
        <button
          class="btn btn-primary mt"
          :disabled="!selectedFiles.length"
          @click="startScan"
        >
          {{ selectedFiles.length === 1 ? 'Escanear imagen' : `Escanear ${selectedFiles.length} imágenes` }}
        </button>
      </div>
    </div>

    <!-- Step 2: Preview + OCR progress -->
    <div class="card" v-if="step === 'scanning'">
      <div class="thumb-grid scanning-thumbs">
        <img v-for="(url, i) in previewUrls" :key="i" :src="url" class="thumb-img" />
      </div>
      <div class="scan-status">
        <div class="scan-phase-icon">{{ scanPhaseIcon }}</div>
        <div class="scan-phase-label">{{ scanStatus }}</div>
        <div class="spinner"></div>
        <div class="scan-phases">
          <div
            v-for="phase in visiblePhases"
            :key="phase.id"
            class="scan-phase-row"
            :class="{
              'phase-done':    phase.state === 'done',
              'phase-active':  phase.state === 'active',
              'phase-pending': phase.state === 'pending',
              'phase-skip':    phase.state === 'skip',
            }"
          >
            <span class="phase-dot"></span>
            <span class="phase-text">{{ phase.label }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Confirm / correct fields -->
    <div class="card" v-if="step === 'confirm'">

      <!-- Barcode source badge -->
      <div v-if="ocrResult?.barcode_source" class="source-badge"
           :class="ocrResult.barcode_source === 'arca_qr' ? 'badge-green' : 'badge-blue'">
        <span v-if="ocrResult.barcode_source === 'arca_qr'">
          ✅ Datos extraídos del <strong>QR de ARCA</strong> — máxima confiabilidad.
        </span>
        <span v-else-if="ocrResult.barcode_source === 'qr_fetch'">
          🌐 Datos complementados desde el <strong>enlace del QR</strong>.
          <span v-if="ocrResult.qr_url" class="badge-url">({{ ocrResult.qr_url }})</span>
        </span>
        <span v-else>
          📊 Fecha y Nro. comprobante extraídos del <strong>código de barras</strong> del ticket.
        </span>
      </div>

      <!-- Retake recommendation when OCR was the fallback and the score is weak -->
      <div v-if="recommendRetake" class="retake-hint">
        <div class="retake-text">
          ⚠️ <strong>La lectura no fue óptima.</strong> No se detectó un código QR de ARCA legible,
          así que los datos se extrajeron del texto y pueden tener errores.
          Completamos lo que se pudo leer — <strong>revisá y corregí</strong> los campos de abajo.
          Para obtener todos los datos con precisión, te recomendamos volver a sacar la foto,
          idealmente <strong>incluyendo el código QR</strong> bien nítido.
        </div>
        <button class="btn btn-outline btn-sm" @click="reset">📷 Volver a sacar la foto</button>
      </div>

      <div class="preview-row">
        <!-- Thumbnail strip (all images, scrollable) -->
        <div class="thumb-strip">
          <img v-for="(url, i) in previewUrls" :key="i" :src="url" class="preview-thumb" />
        </div>
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
              :list="f.key === 'cuit' ? 'cuit-options' : null"
            />
            <span v-if="f.key === 'cuit' && cuitRazon" class="cuit-razon">✓ {{ cuitRazon }}</span>
          </div>
          <!-- Known CUIT → razón social pairs (editable combo box for the CUIT field) -->
          <datalist id="cuit-options">
            <option v-for="c in knownCuits" :key="c.cuit" :value="c.cuit">
              {{ c.cuit }} — {{ c.razon_social }}
            </option>
          </datalist>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { detectCodes, scanInvoice, saveImage, createInvoice, recordCorrection, listCuits } from '../api'
import { isNative } from '../lib/native'
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera'

const native = isNative()

// Native camera capture (Capacitor). Returns a File fed into the same scan flow.
async function takePhoto() {
  try {
    const photo = await Camera.getPhoto({
      quality: 80,
      resultType: CameraResultType.Uri,
      source: CameraSource.Camera,
      allowEditing: false,
    })
    if (!photo?.webPath) return
    const blob = await (await fetch(photo.webPath)).blob()
    const ext = photo.format || 'jpeg'
    const file = new File([blob], `factura-${Date.now()}.${ext}`, {
      type: blob.type || `image/${ext}`,
    })
    _addFiles([file])
  } catch (e) {
    const msg = e?.message || ''
    if (msg && !/cancel/i.test(msg)) alert('No se pudo usar la cámara: ' + msg)
  }
}

const step = ref('pick')       // pick | scanning | confirm | done
const previewUrls = ref([])    // blob URL per image
const selectedFiles = ref([])  // File objects
const ocrResult = ref(null)
const imagePath = ref('')
const saving = ref(false)

// Known CUIT → razón social pairs for the editable CUIT combo box
const knownCuits = ref([])
const cuitRazon = computed(() => {
  const c = (form.cuit || '').trim()
  return knownCuits.value.find((k) => k.cuit === c)?.razon_social || ''
})
onMounted(async () => {
  try { knownCuits.value = (await listCuits()).data } catch { /* non-fatal */ }
})
const saveError = ref('')

// ── Scan progress ─────────────────────────────────────────────────────────────
const scanStatus = ref('Detectando códigos en la imagen…')
const scanPhase  = ref('detect')   // detect | ocr | qr_fetch | arca_qr

const scanPhaseIcon = computed(() => ({
  detect:  '🔍',
  arca_qr: '✅',
  qr_fetch:'🌐',
  ocr:     '📄',
}[scanPhase.value] ?? '🔍'))

// Three possible phases shown to the user; each has a state: pending | active | done | skip
const visiblePhases = computed(() => {
  const p = scanPhase.value
  const phases = [
    {
      id: 'detect',
      label: 'Buscando códigos QR y de barras',
      state: p === 'detect' ? 'active'
           : p !== 'detect' ? 'done'
           : 'pending',
    },
    {
      id: 'ocr',
      label: p === 'arca_qr' ? 'OCR omitido — QR de ARCA tiene todos los datos'
                             : 'Procesando imagen con OCR',
      state: p === 'arca_qr'  ? 'skip'
           : p === 'ocr'      ? 'active'
           : p === 'qr_fetch' ? 'done'
           : 'pending',
    },
    {
      id: 'qr',
      label: p === 'qr_fetch' ? 'Consultando enlace del QR…'
                              : 'Consulta de enlace QR',
      state: p === 'arca_qr'                             ? 'skip'
           : p === 'qr_fetch'                            ? 'active'
           : ['ocr', 'detect'].includes(p)               ? 'pending'
           : 'pending',
    },
  ]
  // Hide the QR-fetch phase unless the image actually has a non-ARCA QR
  // (we only know this after detect, so keep it until then)
  return phases
})

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

// Recommend retaking the photo when the scan fell back to OCR (no usable ARCA
// QR) AND the result is weak — i.e. some field is missing or low-confidence.
// A clean ARCA-QR scan is always reliable, so it never triggers.
const recommendRetake = computed(() => {
  const r = ocrResult.value
  if (!r) return false
  if (r.barcode_source === 'arca_qr') return false
  const FIELDS = ['cuit', 'invoice_date', 'invoice_number', 'total_amount']
  return FIELDS.some((k) => {
    const f = r[k]
    return !f?.value || (f.confidence ?? 0) < 0.8
  })
})

function confLabel(key) {
  const conf = ocrResult.value?.[key]?.confidence
  if (conf === undefined || conf >= 0.9) return ''
  return `(${Math.round(conf * 100)}%)`
}

function _addFiles(fileList) {
  for (const file of fileList) {
    selectedFiles.value.push(file)
    previewUrls.value.push(URL.createObjectURL(file))
  }
}

function onDrop(e) {
  _addFiles(e.dataTransfer.files)
}

function onCameraFile(e) {
  if (e.target.files[0]) _addFiles([e.target.files[0]])
  e.target.value = ''
}

function onGalleryFiles(e) {
  _addFiles(e.target.files)
  e.target.value = ''
}

function removeFile(index) {
  URL.revokeObjectURL(previewUrls.value[index])
  previewUrls.value.splice(index, 1)
  selectedFiles.value.splice(index, 1)
}

async function startScan() {
  if (!selectedFiles.value.length) return
  step.value = 'scanning'
  scanPhase.value  = 'detect'
  scanStatus.value = 'Detectando códigos QR y de barras…'

  try {
    // Phase 1: fast barcode/QR detection (~100 ms) — drives the status label
    let hasQrFetch = false
    try {
      const bcRes = await detectCodes(selectedFiles.value)
      const bc = bcRes.data
      if (bc.barcode_source === 'arca_qr') {
        scanPhase.value  = 'arca_qr'
        scanStatus.value = 'QR de ARCA detectado — extrayendo todos los datos…'
      } else if (bc.qr_url) {
        hasQrFetch = true
        scanPhase.value  = 'ocr'
        scanStatus.value = 'QR detectado — procesando imagen con OCR…'
      } else if (bc.barcode_source === 'code128') {
        scanPhase.value  = 'ocr'
        scanStatus.value = 'Código de barras detectado — procesando imagen con OCR…'
      } else {
        scanPhase.value  = 'ocr'
        scanStatus.value = 'Procesando imagen con OCR…'
      }
    } catch {
      // detect endpoint is best-effort; fall through to full scan
      scanPhase.value  = 'ocr'
      scanStatus.value = 'Procesando imagen con OCR…'
    }

    // Phase 2: full OCR (+ QR URL fetch if applicable)
    if (hasQrFetch) {
      // Update label when OCR finishes and QR fetch begins
      // We can't get a mid-request callback, so show both actions in the label
      scanStatus.value = 'Procesando imagen y consultando enlace del QR…'
      scanPhase.value  = 'qr_fetch'
    }

    const [ocrRes, imgRes] = await Promise.all([
      scanInvoice(selectedFiles.value),
      saveImage(selectedFiles.value[0]),
    ])
    ocrResult.value = ocrRes.data
    imagePath.value = imgRes.data.image_path
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
  previewUrls.value.forEach(u => URL.revokeObjectURL(u))
  previewUrls.value = []
  selectedFiles.value = []
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
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: background .15s;
}
.upload-zone:hover { background: #e3f2fd; }
.upload-icon { font-size: 3rem; margin-bottom: .5rem; }
.muted { color: #888; }
.small { font-size: .8rem; }
.mt { margin-top: 1rem; }

.pick-buttons {
  display: flex; gap: .75rem; justify-content: center;
  margin-top: 1rem; flex-wrap: wrap;
}

.tip-note {
  margin-top: 1rem;
  padding: .65rem .85rem;
  background: #fff8e1;
  border: 1px solid #ffe29a;
  border-radius: 8px;
  color: #6b5300;
  font-size: .85rem;
  text-align: center;
}

/* Thumbnail grid (pick step) */
.thumb-grid {
  display: flex; flex-wrap: wrap; gap: .6rem;
  margin-top: 1rem;
}
.thumb-item {
  position: relative; width: 90px; height: 90px;
}
.thumb-img {
  width: 100%; height: 100%; object-fit: cover;
  border-radius: 8px; display: block;
}
.thumb-remove {
  position: absolute; top: -6px; right: -6px;
  background: #e53935; color: #fff; border: none;
  border-radius: 50%; width: 20px; height: 20px;
  font-size: .65rem; cursor: pointer; line-height: 20px;
  padding: 0; text-align: center;
}

/* Scanning thumbnails */
.scanning-thumbs { justify-content: center; margin-bottom: 1rem; }

.scan-status {
  display: flex; flex-direction: column; align-items: center; gap: .6rem;
  padding: .5rem 0 .25rem;
}
.scan-phase-icon { font-size: 2rem; }
.scan-phase-label {
  font-weight: 600; font-size: .95rem; text-align: center; color: #1565c0;
}
.spinner {
  width: 36px; height: 36px; border: 4px solid #e3f2fd;
  border-top-color: #1976d2; border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg) } }

.scan-phases {
  display: flex; flex-direction: column; gap: .35rem;
  align-self: stretch; margin-top: .4rem;
}
.scan-phase-row {
  display: flex; align-items: center; gap: .55rem;
  font-size: .82rem; color: #999;
}
.phase-dot {
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
  background: currentColor;
}
.phase-active  { color: #1565c0; font-weight: 600; }
.phase-active .phase-dot { background: #1976d2; box-shadow: 0 0 0 3px #bbdefb; }
.phase-done    { color: #2e7d32; }
.phase-done .phase-dot { background: #43a047; }
.phase-skip    { color: #bbb; text-decoration: line-through; }
.phase-pending { color: #bbb; }

/* Confirm step layout */
.preview-row { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.thumb-strip {
  display: flex; flex-direction: column; gap: .5rem;
  overflow-y: auto; max-height: 340px;
  flex-shrink: 0;
}
.preview-thumb { width: 120px; height: 120px; object-fit: cover; border-radius: 8px; }
.ocr-fields { flex: 1; min-width: 220px; }

.unrecognized-tag { background: #fff3e0; color: #e65100; font-size: .72rem; font-weight: 700; padding: .1rem .4rem; border-radius: 4px; margin-left: .4rem; }
.confidence-tag { color: #aaa; font-size: .75rem; margin-left: .3rem; }
.field-warn { border-color: #ff9800 !important; }
.cuit-razon { display: block; margin-top: .25rem; font-size: .8rem; color: #1a7f37; font-weight: 600; }

.source-badge {
  border-radius: 8px; padding: .65rem 1rem; margin-bottom: 1rem; font-size: .88rem;
}
.badge-green { background: #e8f5e9; color: #2e7d32; border: 1.5px solid #a5d6a7; }
.badge-blue  { background: #e3f2fd; color: #0d47a1; border: 1.5px solid #90caf9; }
.badge-url   { font-size: .75rem; word-break: break-all; opacity: .75; }

.qr-hint {
  background: #fff8e1; color: #e65100; border: 1.5px solid #ffe082;
  border-radius: 8px; padding: .65rem 1rem; margin-bottom: 1rem; font-size: .85rem;
}
.retake-hint {
  background: #fff8e1; color: #8a4b00; border: 1.5px solid #ffd479;
  border-radius: 8px; padding: .75rem 1rem; margin-bottom: 1rem; font-size: .85rem;
  display: flex; flex-direction: column; gap: .6rem; align-items: flex-start;
}
.retake-hint .retake-text { line-height: 1.45; }
.retake-hint .btn { flex-shrink: 0; }
.form-actions { display: flex; gap: 1rem; justify-content: flex-end; margin-top: 1rem; flex-wrap: wrap; }
.error-msg { color: #b71c1c; font-size: .85rem; margin-top: .5rem; }
.center { text-align: center; }
.done-icon { font-size: 3rem; margin-bottom: .5rem; }
.done-msg { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
</style>
