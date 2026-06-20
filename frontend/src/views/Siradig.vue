<script setup>
import { ref, computed, onMounted } from 'vue'
import { listInvoices, setInvoiceSyncStatus } from '../api'

// AFIP Clave Fiscal login (from there the user opens "SiRADIG – Trabajador").
const SIRADIG_URL = 'https://auth.afip.gob.ar/contribuyente_/loginClave.xhtml'

const invoices = ref([])
const loading = ref(true)
const error = ref('')
const idx = ref(0)
const doneIds = ref(new Set())
const copiedKey = ref('')
const nextFieldIdx = ref(0)
const marking = ref(false)

const current = computed(() => invoices.value[idx.value] || null)
const total = computed(() => invoices.value.length)
const doneCount = computed(() => doneIds.value.size)
const progressPct = computed(() => (total.value ? Math.round((doneCount.value / total.value) * 100) : 0))

function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}` // SiRADIG uses DD/MM/YYYY
}
function fmtAmount(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : String(v ?? '')
}

// The values you actually paste into the form, in form order.
// `value` is shown for readability; `copy` is what lands on the clipboard
// (e.g. SiRADIG expects the CUIT as plain digits, without dashes).
const pasteFields = computed(() => {
  const inv = current.value
  if (!inv) return []
  const amount = fmtAmount(inv.total_amount)
  const date = fmtDate(inv.invoice_date)
  // SiRADIG splits the comprobante into two fields: punto de venta + número.
  const [pdv = '', nro = ''] = (inv.invoice_number || '').split('-')
  return [
    { key: 'cuit', label: 'CUIT emisor', value: inv.cuit, copy: (inv.cuit || '').replace(/\D/g, '') },
    { key: 'pdv', label: 'Punto de venta', value: pdv, copy: pdv },
    { key: 'nro', label: 'Número de comprobante', value: nro, copy: nro },
    { key: 'fecha', label: 'Fecha', value: date, copy: date },
    { key: 'importe', label: 'Importe', value: amount, copy: amount },
  ]
})

async function copy(key, value) {
  try {
    await navigator.clipboard.writeText(value ?? '')
    copiedKey.value = key
    // advance the "next field" pointer if this was the expected one
    const i = pasteFields.value.findIndex((f) => f.key === key)
    if (i === nextFieldIdx.value) nextFieldIdx.value = Math.min(i + 1, pasteFields.value.length)
    setTimeout(() => { if (copiedKey.value === key) copiedKey.value = '' }, 1200)
  } catch {
    error.value = 'No se pudo copiar al portapapeles (requiere HTTPS).'
  }
}

async function copyNext() {
  const f = pasteFields.value[nextFieldIdx.value]
  if (f) await copy(f.key, f.copy)
}

function resetPerInvoice() {
  nextFieldIdx.value = 0
  copiedKey.value = ''
}

function go(i) {
  if (i < 0 || i >= total.value) return
  idx.value = i
  resetPerInvoice()
}
function next() { go(idx.value + 1) }
function prev() { go(idx.value - 1) }

async function markLoaded() {
  const inv = current.value
  if (!inv) return
  marking.value = true
  try {
    await setInvoiceSyncStatus(inv.id, 'synced')
    doneIds.value.add(inv.id)
    doneIds.value = new Set(doneIds.value) // trigger reactivity
    if (idx.value < total.value - 1) next()
  } catch {
    error.value = 'No se pudo marcar como cargada.'
  } finally {
    marking.value = false
  }
}

function openSiradig() {
  window.open(SIRADIG_URL, '_blank', 'noopener')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await listInvoices({ status: 'pending', limit: 500 })
    invoices.value = (data || []).sort((a, b) => a.invoice_date.localeCompare(b.invoice_date))
    idx.value = 0
    resetPerInvoice()
  } catch {
    error.value = 'No se pudieron cargar las facturas pendientes.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="siradig">
    <div class="head">
      <div>
        <h1 class="page-title">Cargar en SiRADIG</h1>
        <p class="lead">Copiá cada dato y pegalo en el formulario 572 de AFIP. Cuando cargaste una factura,
          marcala como cargada y pasá a la siguiente.</p>
      </div>
      <button class="btn btn-primary" @click="openSiradig">Abrir SiRADIG ↗</button>
    </div>

    <div v-if="loading" class="card">Cargando facturas pendientes…</div>

    <div v-else-if="error && !current" class="card err">{{ error }}</div>

    <div v-else-if="!total" class="card empty">
      🎉 No tenés facturas pendientes de carga. ¡Todo al día!
    </div>

    <template v-else>
      <!-- progress -->
      <div class="card progress-card">
        <div class="progress-top">
          <span><strong>{{ doneCount }}</strong> de <strong>{{ total }}</strong> cargadas</span>
          <span class="muted">Factura {{ idx + 1 }} / {{ total }}</span>
        </div>
        <div class="bar"><i :style="{ width: progressPct + '%' }"></i></div>
      </div>

      <!-- current invoice -->
      <div class="card invoice" v-if="current">
        <div class="ref">
          <div class="ref-item">
            <span class="ref-lbl">Razón social</span>
            <span class="ref-val">{{ current.razon_social || '—' }}</span>
          </div>
          <div class="ref-item">
            <span class="ref-lbl">Categoría (seleccioná en SiRADIG)</span>
            <span class="ref-val cat">{{ current.category || '—' }}</span>
          </div>
        </div>

        <div class="fields">
          <div
            v-for="(f, i) in pasteFields"
            :key="f.key"
            class="frow"
            :class="{ nextup: i === nextFieldIdx }"
          >
            <div class="finfo">
              <span class="flbl">{{ f.label }}</span>
              <span class="fval">{{ f.value }}</span>
            </div>
            <button class="copybtn" :class="{ ok: copiedKey === f.key }" @click="copy(f.key, f.copy)">
              {{ copiedKey === f.key ? '✓ copiado' : 'copiar' }}
            </button>
          </div>
        </div>

        <button class="btn btn-outline copynext" @click="copyNext" :disabled="nextFieldIdx >= pasteFields.length">
          {{ nextFieldIdx >= pasteFields.length ? 'Todos los campos copiados' : `Copiar siguiente campo · ${pasteFields[nextFieldIdx]?.label}` }}
        </button>

        <div class="actions">
          <button class="btn btn-ghost" @click="prev" :disabled="idx === 0">← Anterior</button>
          <button class="btn btn-ghost" @click="next" :disabled="idx >= total - 1">Saltar →</button>
          <button class="btn btn-success" @click="markLoaded" :disabled="marking">
            {{ marking ? 'Guardando…' : '✓ Cargada · Siguiente' }}
          </button>
        </div>
        <p v-if="error" class="inline-err">{{ error }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
.page-title { font-size: 1.5rem; font-weight: 700; }
.lead { color: #666; font-size: .9rem; max-width: 560px; margin-top: .25rem; }
.err { color: #b71c1c; }
.empty { text-align: center; font-size: 1.05rem; padding: 2rem 1rem; }
.muted { color: #888; font-size: .85rem; }

.progress-card { padding: .9rem 1.1rem; }
.progress-top { display: flex; justify-content: space-between; align-items: center; font-size: .9rem; margin-bottom: .5rem; }
.bar { height: 8px; background: #eef1f6; border-radius: 6px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: #34c759; transition: width .25s; }

.invoice { display: flex; flex-direction: column; gap: .9rem; }
.ref { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }
@media (max-width: 560px) { .ref { grid-template-columns: 1fr; } }
.ref-item { background: #f5f7fa; border-radius: 10px; padding: .55rem .7rem; }
.ref-lbl { display: block; font-size: .7rem; text-transform: uppercase; letter-spacing: .4px; color: #888; }
.ref-val { font-weight: 600; }
.ref-val.cat { color: #1565c0; }

.fields { display: flex; flex-direction: column; gap: .5rem; }
.frow { display: flex; align-items: center; justify-content: space-between; gap: .75rem;
        border: 1.5px solid #e3e8ef; border-radius: 10px; padding: .55rem .7rem; transition: border-color .15s, background .15s; }
.frow.nextup { border-color: #1976d2; background: #f0f7ff; }
.finfo { display: flex; flex-direction: column; min-width: 0; }
.flbl { font-size: .7rem; text-transform: uppercase; letter-spacing: .4px; color: #888; }
.fval { font-size: 1.05rem; font-weight: 700; font-variant-numeric: tabular-nums; word-break: break-all; }
.copybtn { flex: none; background: #1976d2; color: #fff; border: none; border-radius: 8px; font-weight: 700;
           font-size: .82rem; padding: .5rem .9rem; cursor: pointer; min-width: 90px; }
.copybtn.ok { background: #2e7d32; }

.copynext { width: 100%; justify-content: center; }

.actions { display: flex; gap: .5rem; flex-wrap: wrap; }
.btn-ghost { background: transparent; color: #555; border: 1.5px solid #d0d7de; }
.btn-success { background: #34c759; color: #06310f; margin-left: auto; }
.btn-success:hover:not(:disabled) { background: #2eb150; }
.inline-err { color: #b71c1c; font-size: .85rem; }
</style>
