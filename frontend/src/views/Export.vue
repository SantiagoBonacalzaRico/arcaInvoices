<template>
  <div>
    <div class="page-header">
      <h1 class="page-title">Exportar para SiRADIG</h1>
      <div class="header-actions">
        <select v-model="fiscalYear" @change="load" class="year-select">
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-model="filterStatus" @change="load" class="status-select">
          <option value="">Todos los estados</option>
          <option value="pending">Pendientes</option>
          <option value="synced">Sincronizados</option>
        </select>
        <button class="btn btn-primary" @click="downloadCsvFile" :disabled="downloading">
          {{ downloading ? 'Generando…' : '⬇ Descargar CSV' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="card center muted">Cargando…</div>

    <div v-else-if="!groups.length" class="card center muted">
      No hay facturas para los filtros seleccionados.
    </div>

    <div v-else>
      <!-- Summary totals bar -->
      <div class="card totals-bar">
        <div class="total-item">
          <span class="total-label">Facturas</span>
          <span class="total-val">{{ totalInvoices }}</span>
        </div>
        <div class="total-item">
          <span class="total-label">Proveedores</span>
          <span class="total-val">{{ groups.length }}</span>
        </div>
        <div class="total-item">
          <span class="total-label">Total</span>
          <span class="total-val">$ {{ fmtARS(grandTotal) }}</span>
        </div>
      </div>

      <!-- One card per CUIT -->
      <div v-for="g in groups" :key="g.cuit" class="card group-card">
        <div class="group-header">
          <div class="group-identity">
            <span class="group-cuit">{{ g.cuit }}</span>
            <!-- Inline edit for razón social -->
            <span v-if="!editingRS[g.cuit]" class="group-razon" @click="startEditRS(g)">
              {{ g.razon_social || '— Sin nombre (clic para editar)' }}
              <span class="edit-hint">✏️</span>
            </span>
            <span v-else class="rs-edit">
              <input v-model="rsForm[g.cuit]" class="rs-input" @keyup.enter="saveRS(g)" @keyup.escape="editingRS[g.cuit] = false" placeholder="Razón social" autofocus />
              <button class="btn btn-primary btn-xs" @click="saveRS(g)">OK</button>
              <button class="btn btn-outline btn-xs" @click="editingRS[g.cuit] = false">✕</button>
            </span>
          </div>
          <div class="group-total">
            <span class="total-label">Total</span>
            <strong>$ {{ fmtARS(g.total) }}</strong>
          </div>
        </div>

        <!-- Invoice table -->
        <div class="tablewrap">
        <table class="inv-table">
          <thead>
            <tr>
              <th>{{ native ? 'Comprob.' : 'Nro Comprobante' }}</th>
              <th>Fecha</th>
              <th class="right">{{ native ? '$' : 'Importe' }}</th>
              <th>{{ native ? 'Cat.' : 'Categoría' }}</th>
              <th>{{ native ? 'Est.' : 'Estado' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in g.invoices" :key="inv.id">
              <td class="mono">{{ inv.invoice_number }}</td>
              <td class="date-cell">{{ native ? fmtDateShort(inv.date) : inv.date }}</td>
              <td class="right mono">{{ inv.amount }}</td>
              <td>
                <select v-model="inv.category" @change="updateCategory(inv)" class="cat-select">
                  <option value="">— Sin categoría —</option>
                  <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
                </select>
              </td>
              <td><span :class="['badge', `badge-${inv.sync_status}`]">{{ inv.sync_status }}</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="2" class="right muted">Subtotal</td>
              <td class="right mono"><strong>{{ g.total }}</strong></td>
              <td colspan="2"></td>
            </tr>
          </tfoot>
        </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { updateInvoice, exportSummary, exportCategories, setRazonSocial, downloadCsv } from '../api'
import { isNative } from '../lib/native'

const native = isNative()

function fmtDateShort(iso) {
  if (!iso) return ''
  const [y, m, d] = String(iso).split('-')
  return `${d}/${m}/${y.slice(2)}`
}

const fiscalYear = ref(new Date().getFullYear())
const filterStatus = ref('pending')
const groups = ref([])
const categories = ref([])
const loading = ref(true)
const downloading = ref(false)
const editingRS = reactive({})
const rsForm = reactive({})

const years = computed(() => {
  const yr = new Date().getFullYear()
  return [yr, yr - 1, yr - 2]
})

function currentParams() {
  const params = {}
  if (fiscalYear.value) params.fiscal_year = fiscalYear.value
  if (filterStatus.value) params.sync_status = filterStatus.value
  return params
}

const totalInvoices = computed(() => groups.value.reduce((s, g) => s + g.invoices.length, 0))
const grandTotal = computed(() =>
  groups.value.reduce((s, g) => s + parseFloat(g.total || 0), 0)
)

function fmtARS(val) {
  return parseFloat(val || 0).toLocaleString('es-AR', { minimumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  try {
    const res = await exportSummary(currentParams())
    groups.value = res.data
  } catch {
    groups.value = []
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const res = await exportCategories()
    categories.value = res.data
  } catch {
    categories.value = []
  }
}

async function downloadCsvFile() {
  downloading.value = true
  try {
    const res = await downloadCsv(currentParams())
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `facturas_${fiscalYear.value || 'todas'}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    alert('No se pudo generar el CSV.')
  } finally {
    downloading.value = false
  }
}

function startEditRS(g) {
  editingRS[g.cuit] = true
  rsForm[g.cuit] = g.razon_social || ''
}

async function saveRS(g) {
  if (!rsForm[g.cuit]?.trim()) return
  await setRazonSocial(g.cuit, rsForm[g.cuit])
  g.razon_social = rsForm[g.cuit]
  editingRS[g.cuit] = false
}

async function updateCategory(inv) {
  await updateInvoice(inv.id, { category: inv.category || null })
}

onMounted(async () => {
  await Promise.all([load(), loadCategories()])
})
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; flex-wrap: wrap; gap: .75rem; }
.page-title { font-size: 1.5rem; font-weight: 700; }
.header-actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.year-select, .status-select { padding: .45rem .7rem; border-radius: 8px; border: 1.5px solid #d0d7de; font-size: .9rem; background: white; }

.totals-bar { display: flex; gap: 2rem; padding: 1rem 1.5rem; flex-wrap: wrap; }
.total-item { display: flex; flex-direction: column; }
.total-label { font-size: .75rem; text-transform: uppercase; color: #888; letter-spacing: .5px; }
.total-val { font-size: 1.4rem; font-weight: 800; color: #1976d2; }

.group-card { margin-bottom: 1rem; }
.group-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: .75rem; flex-wrap: wrap; gap: .5rem; }
.group-identity { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
.group-cuit { font-family: monospace; font-size: .9rem; background: #f0f4ff; padding: .2rem .5rem; border-radius: 4px; font-weight: 600; }
.group-razon { font-size: 1rem; font-weight: 600; cursor: pointer; }
.group-razon:hover .edit-hint { opacity: 1; }
.edit-hint { font-size: .8rem; opacity: 0; transition: opacity .15s; margin-left: .3rem; }
.rs-edit { display: flex; align-items: center; gap: .4rem; }
.rs-input { padding: .35rem .6rem; border: 1.5px solid #1976d2; border-radius: 6px; font-size: .95rem; min-width: 220px; outline: none; }
.btn-xs { padding: .25rem .55rem; font-size: .78rem; }
.group-total { text-align: right; }
.group-total .total-label { font-size: .75rem; color: #888; display: block; }

.inv-table { width: 100%; border-collapse: collapse; font-size: .88rem; }
.inv-table th { text-align: left; padding: .4rem .6rem; background: #f5f7fa; font-size: .78rem; text-transform: uppercase; letter-spacing: .4px; color: #666; border-bottom: 2px solid #e0e0e0; }
.inv-table td { padding: .45rem .6rem; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
.inv-table tfoot td { background: #fafafa; font-size: .85rem; padding: .35rem .6rem; }
.inv-table tr:hover td { background: #f8fbff; }
.right { text-align: right; }
.mono { font-family: monospace; }
.cat-select { padding: .3rem .5rem; border-radius: 6px; border: 1.5px solid #d0d7de; font-size: .82rem; max-width: 220px; }
.muted { color: #888; }
.center { text-align: center; padding: 2rem; }

/* Native app only: ONLY the invoice table scrolls horizontally (the vendor
   header, totals and the rest stay static). width:max-content lets the table
   grow past the viewport so the wrapper scrolls instead of squeezing columns.
   PWA layout unchanged. */
.native .tablewrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.native .inv-table { font-size: .8rem; width: max-content; min-width: 100%; }
.native .inv-table th,
.native .inv-table td { white-space: nowrap; }
.native .cat-select { max-width: 160px; }
</style>
