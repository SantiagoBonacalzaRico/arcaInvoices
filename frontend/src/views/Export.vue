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
        <a :href="csvUrl" class="btn btn-primary" download>⬇ Descargar CSV</a>
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
        <table class="inv-table">
          <thead>
            <tr>
              <th>Nro Comprobante</th>
              <th>Fecha</th>
              <th class="right">Importe</th>
              <th>Categoría</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in g.invoices" :key="inv.id">
              <td class="mono">{{ inv.invoice_number }}</td>
              <td>{{ inv.date }}</td>
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
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { updateInvoice } from '../api'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

const fiscalYear = ref(new Date().getFullYear())
const filterStatus = ref('pending')
const groups = ref([])
const categories = ref([])
const loading = ref(true)
const editingRS = reactive({})
const rsForm = reactive({})

const years = computed(() => {
  const yr = new Date().getFullYear()
  return [yr, yr - 1, yr - 2]
})

const csvUrl = computed(() => {
  const params = new URLSearchParams()
  if (fiscalYear.value) params.set('fiscal_year', fiscalYear.value)
  if (filterStatus.value) params.set('sync_status', filterStatus.value)
  return `/api/export/csv?${params}`
})

const totalInvoices = computed(() => groups.value.reduce((s, g) => s + g.invoices.length, 0))
const grandTotal = computed(() =>
  groups.value.reduce((s, g) => s + parseFloat(g.total || 0), 0)
)

function fmtARS(val) {
  return parseFloat(val || 0).toLocaleString('es-AR', { minimumFractionDigits: 2 })
}

async function load() {
  loading.value = true
  const params = {}
  if (fiscalYear.value) params.fiscal_year = fiscalYear.value
  if (filterStatus.value) params.sync_status = filterStatus.value
  const res = await api.get('/export/summary', { params })
  groups.value = res.data
  loading.value = false
}

async function loadCategories() {
  const res = await api.get('/export/categories')
  categories.value = res.data
}

function startEditRS(g) {
  editingRS[g.cuit] = true
  rsForm[g.cuit] = g.razon_social || ''
}

async function saveRS(g) {
  if (!rsForm[g.cuit]?.trim()) return
  await api.post(`/cuit/${g.cuit}`, null, { params: { razon_social: rsForm[g.cuit] } })
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
</style>
