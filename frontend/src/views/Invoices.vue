<template>
  <div>
    <!-- Reusable copy icon (two overlapping sheets) defined once -->
    <svg width="0" height="0" class="svg-defs" aria-hidden="true">
      <symbol id="ico-copy" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
      </symbol>
    </svg>

    <div class="list-header">
      <h1 class="page-title">Facturas</h1>
      <div class="header-right">
        <div class="total-summary">
          <span class="total-label">{{ isFiltered ? 'Total filtrado' : 'Total' }} ({{ visibleInvoices.length }})</span>
          <span class="total-amount">${{ filteredTotal.toLocaleString('es-AR', { minimumFractionDigits: 2 }) }}</span>
        </div>
        <router-link to="/capture" class="btn btn-primary">+ Nueva</router-link>
      </div>
    </div>

    <div class="filters card">
      <input
        v-model="search"
        class="search-box"
        type="search"
        placeholder="Buscar por CUIT, fecha o razón social…"
      />
      <select v-model="filterStatus" @change="load">
        <option value="">Todos los estados</option>
        <option value="pending">Pendiente</option>
        <option value="synced">Sincronizado</option>
        <option value="error">Error</option>
      </select>
      <select v-model="filterRazon" class="facet-select">
        <option value="">Todas las razones sociales</option>
        <option v-for="r in razonOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="filterCuit" class="facet-select">
        <option value="">Todos los CUIT</option>
        <option v-for="c in cuitOptions" :key="c.cuit" :value="c.cuit">
          {{ c.cuit }}{{ c.razon ? ' — ' + c.razon : '' }}
        </option>
      </select>
      <div class="sort-control">
        <label class="sort-label">Ordenar:</label>
        <select v-model="sortField">
          <option value="invoice_date">Fecha</option>
          <option value="cuit">CUIT</option>
          <option value="razon_social">Razón social</option>
        </select>
        <button
          class="btn btn-outline btn-sm sort-dir"
          @click="sortDir = sortDir === 'asc' ? 'desc' : 'asc'"
          :title="sortDir === 'asc' ? 'Ascendente' : 'Descendente'"
        >
          {{ sortDir === 'asc' ? '▲' : '▼' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="center muted">Cargando…</div>

    <div v-else-if="invoices.length === 0" class="card center muted">
      No hay facturas. <router-link to="/capture">Escaneá una.</router-link>
    </div>

    <div v-else-if="visibleInvoices.length === 0" class="card center muted">
      Ningún resultado para los filtros aplicados.
    </div>

    <div v-else>
      <div class="card invoice-row" v-for="inv in visibleInvoices" :key="inv.id">
        <div v-if="editing !== inv.id" class="inv-view">
          <div class="inv-main">
            <span class="inv-number">{{ inv.invoice_number }}</span>
            <button class="copy-btn" @click="copyPlain('invoice_number', inv.invoice_number)"
                    title="Copiar número (solo dígitos)" aria-label="Copiar número">
              <svg class="ico"><use href="#ico-copy" /></svg>
            </button>
            <span :class="['badge', `badge-${inv.sync_status}`]">{{ inv.sync_status }}</span>
          </div>
          <div class="inv-meta">
            <span class="meta-item">
              CUIT: <strong>{{ inv.cuit }}</strong>
              <button class="copy-btn" @click="copyPlain('cuit', inv.cuit)"
                      title="Copiar CUIT (solo dígitos)" aria-label="Copiar CUIT">
                <svg class="ico"><use href="#ico-copy" /></svg>
              </button>
            </span>
            <span class="meta-item">
              Fecha: <strong>{{ inv.invoice_date }}</strong>
              <button class="copy-btn" @click="copyPlain('invoice_date', inv.invoice_date)"
                      title="Copiar fecha" aria-label="Copiar fecha">
                <svg class="ico"><use href="#ico-copy" /></svg>
              </button>
            </span>
            <span class="meta-item">
              Total: <strong>${{ Number(inv.total_amount).toLocaleString('es-AR', {minimumFractionDigits:2}) }}</strong>
              <button class="copy-btn" @click="copyPlain('total_amount', inv.total_amount)"
                      title="Copiar total (texto plano)" aria-label="Copiar total">
                <svg class="ico"><use href="#ico-copy" /></svg>
              </button>
            </span>
            <span class="meta-item">
              Razón social: <strong>{{ inv.razon_social || '—' }}</strong>
              <button v-if="inv.razon_social" class="copy-btn"
                      @click="copyPlain('razon_social', inv.razon_social)"
                      title="Copiar razón social" aria-label="Copiar razón social">
                <svg class="ico"><use href="#ico-copy" /></svg>
              </button>
            </span>
            <span v-if="inv.category" class="muted">{{ inv.category }}</span>
          </div>
          <div class="inv-actions">
            <button class="btn btn-outline btn-sm" @click="startEdit(inv)">Editar</button>
            <button
              class="btn btn-sm"
              :class="inv.sync_status === 'synced' ? 'btn-outline' : 'btn-primary'"
              @click="toggleSync(inv)"
            >
              {{ inv.sync_status === 'synced' ? 'Marcar pendiente' : 'Marcar sincronizada' }}
            </button>
            <button class="btn btn-danger btn-sm" @click="remove(inv.id)">Eliminar</button>
          </div>
        </div>

        <!-- Inline edit form -->
        <div v-else class="inv-edit">
          <div class="edit-grid">
            <div class="form-group">
              <label>CUIT</label>
              <input v-model="editForm.cuit" placeholder="20-12345678-9" />
            </div>
            <div class="form-group">
              <label>Fecha</label>
              <input v-model="editForm.invoice_date" type="date" />
            </div>
            <div class="form-group">
              <label>Nro. comprobante</label>
              <input v-model="editForm.invoice_number" placeholder="0001-00012345" />
            </div>
            <div class="form-group">
              <label>Total</label>
              <input v-model="editForm.total_amount" type="number" step="0.01" />
            </div>
            <div class="form-group">
              <label>Categoría</label>
              <input v-model="editForm.category" />
            </div>
          </div>
          <div class="inv-actions">
            <button class="btn btn-outline btn-sm" @click="editing = null">Cancelar</button>
            <button class="btn btn-primary btn-sm" @click="saveEdit(inv.id)">Guardar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Ephemeral copy confirmation -->
    <Transition name="toast-fade">
      <div v-if="copiedMsg" class="copy-toast">✓ {{ copiedMsg }}</div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listInvoices, updateInvoice, deleteInvoice, setInvoiceSyncStatus } from '../api'

const invoices = ref([])
const loading  = ref(true)
const filterStatus = ref('')
const editing  = ref(null)
const editForm = reactive({})

const search   = ref('')
const filterCuit  = ref('')
const filterRazon = ref('')
const sortField = ref('invoice_date')
const sortDir   = ref('desc')
const copiedMsg = ref('')
let copyTimer = null

// Confirmation text per field (Spanish gender agreement)
const COPY_LABELS = {
  cuit:           'CUIT copiado',
  invoice_number: 'Comprobante copiado',
  total_amount:   'Total copiado',
  invoice_date:   'Fecha copiada',
  razon_social:   'Razón social copiada',
}

function matchesSearch(inv) {
  const term = search.value.trim().toLowerCase()
  if (!term) return true
  const termDigits = term.replace(/\D/g, '')
  const cuit = (inv.cuit || '').toLowerCase()
  const cuitDigits = (inv.cuit || '').replace(/\D/g, '')
  const fecha = (inv.invoice_date || '').toLowerCase()
  const razon = (inv.razon_social || '').toLowerCase()
  return (
    cuit.includes(term) ||
    (termDigits && cuitDigits.includes(termDigits)) ||
    fecha.includes(term) ||
    razon.includes(term)
  )
}

// Apply search + facet filters. Skip a facet to compute that facet's own
// options (so it always lists values that still yield results).
function filterRows(rows, { skipCuit = false, skipRazon = false } = {}) {
  return rows.filter((inv) => {
    if (!matchesSearch(inv)) return false
    if (!skipCuit && filterCuit.value && inv.cuit !== filterCuit.value) return false
    if (!skipRazon && filterRazon.value && (inv.razon_social || '') !== filterRazon.value) return false
    return true
  })
}

const visibleInvoices = computed(() => {
  const rows = filterRows(invoices.value)
  const dir = sortDir.value === 'asc' ? 1 : -1
  const field = sortField.value
  return [...rows].sort((a, b) => {
    const av = (a[field] ?? '').toString().toLowerCase()
    const bv = (b[field] ?? '').toString().toLowerCase()
    if (av === bv) return 0
    if (av === '') return 1   // empty values always last
    if (bv === '') return -1
    return av < bv ? -dir : dir
  })
})

// Faceted options — derived from the data, narrowed by the OTHER active
// filters, so every listed value is guaranteed to return at least one result.
const cuitOptions = computed(() => {
  const map = new Map()
  for (const inv of filterRows(invoices.value, { skipCuit: true })) {
    if (inv.cuit && !map.has(inv.cuit)) map.set(inv.cuit, inv.razon_social || '')
  }
  return [...map.entries()]
    .map(([cuit, razon]) => ({ cuit, razon }))
    .sort((a, b) => (a.razon || a.cuit).localeCompare(b.razon || b.cuit))
})

const razonOptions = computed(() => {
  const set = new Set()
  for (const inv of filterRows(invoices.value, { skipRazon: true })) {
    if (inv.razon_social) set.add(inv.razon_social)
  }
  return [...set].sort((a, b) => a.localeCompare(b))
})

// True when any filter or search term narrows the list
const isFiltered = computed(() =>
  !!filterStatus.value || !!search.value.trim() || !!filterCuit.value || !!filterRazon.value
)

// Sum of the currently-visible (filtered) invoice totals
const filteredTotal = computed(() =>
  visibleInvoices.value.reduce((sum, inv) => sum + (Number(inv.total_amount) || 0), 0)
)

function plainValue(field, value) {
  if (value == null) return ''
  switch (field) {
    case 'cuit':
    case 'invoice_number':
      return String(value).replace(/\D/g, '')        // digits only
    case 'total_amount':
      return Number(value).toFixed(2)                 // e.g. "704578.52", no thousands sep
    default:
      return String(value)                            // date, razón social as-is
  }
}

async function copyPlain(field, value) {
  const text = plainValue(field, value)
  try {
    await navigator.clipboard.writeText(text)
    copiedMsg.value = COPY_LABELS[field] || 'Copiado'
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedMsg.value = '' }, 1600)
  } catch {
    // Clipboard API unavailable (e.g. insecure context) — silently ignore
  }
}

async function load() {
  loading.value = true
  const res = await listInvoices(filterStatus.value ? { status: filterStatus.value } : {})
  invoices.value = res.data
  loading.value = false
}

function startEdit(inv) {
  editing.value = inv.id
  Object.assign(editForm, {
    cuit: inv.cuit, invoice_date: inv.invoice_date,
    invoice_number: inv.invoice_number, total_amount: inv.total_amount,
    category: inv.category || '',
  })
}

async function saveEdit(id) {
  await updateInvoice(id, {
    cuit: editForm.cuit,
    invoice_date: editForm.invoice_date,
    invoice_number: editForm.invoice_number,
    total_amount: parseFloat(editForm.total_amount),
    category: editForm.category || null,
  })
  editing.value = null
  await load()
}

async function toggleSync(inv) {
  const next = inv.sync_status === 'synced' ? 'pending' : 'synced'
  const res = await setInvoiceSyncStatus(inv.id, next)
  // Patch in place so the list order/scroll doesn't jump
  Object.assign(inv, res.data)
}

async function remove(id) {
  if (!confirm('¿Eliminar esta factura?')) return
  await deleteInvoice(id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; }
.list-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.header-right { display: flex; align-items: center; gap: 1rem; }
.total-summary { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.15; }
.total-label { font-size: .72rem; color: #888; text-transform: uppercase; letter-spacing: .02em; }
.total-amount { font-size: 1.25rem; font-weight: 700; color: #1a7f37; }
.filters { padding: .75rem 1rem; display: flex; flex-wrap: wrap; gap: .6rem 1rem; align-items: center; }
.filters select { padding: .45rem .7rem; border-radius: 8px; border: 1.5px solid #d0d7de; font-size: .9rem; }
.facet-select { max-width: 240px; }
.search-box { flex: 1 1 240px; padding: .45rem .7rem; border-radius: 8px; border: 1.5px solid #d0d7de; font-size: .9rem; }
.sort-control { display: flex; align-items: center; gap: .4rem; }
.sort-label { font-size: .85rem; color: #555; }
.sort-dir { padding: .35rem .6rem; }
.invoice-row { margin-bottom: .75rem; }
.inv-main { display: flex; align-items: center; gap: .5rem; margin-bottom: .4rem; }
.inv-number { font-weight: 700; font-size: 1rem; }
.inv-meta { display: flex; flex-wrap: wrap; gap: .75rem 1.5rem; font-size: .88rem; color: #555; margin-bottom: .5rem; }
.meta-item { display: inline-flex; align-items: center; gap: .35rem; }
.inv-actions { display: flex; gap: .5rem; flex-wrap: wrap; }
.btn-sm { padding: .3rem .75rem; font-size: .8rem; }
.muted { color: #888; }
.center { text-align: center; padding: 2rem; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: .5rem 1rem; margin-bottom: .75rem; }
.edit-grid .form-group { margin-bottom: 0; }
.svg-defs { position: absolute; width: 0; height: 0; overflow: hidden; }
.copy-btn {
  display: inline-flex; align-items: center; justify-content: center;
  border: none; background: transparent; cursor: pointer;
  padding: .15rem; border-radius: 5px; color: #6b7280;
  opacity: .75; transition: opacity .15s, background .15s, color .15s;
}
.copy-btn:hover { opacity: 1; background: #eef1f4; color: #1f6feb; }
.copy-btn .ico { width: 15px; height: 15px; display: block; }

/* Ephemeral copy confirmation toast */
.copy-toast {
  position: fixed; left: 50%; bottom: 1.5rem; transform: translateX(-50%);
  background: #e6f4ea; color: #1a7f37; border: 1px solid #a6d9b6;
  padding: .5rem .9rem; border-radius: 999px; font-size: .85rem; font-weight: 600;
  box-shadow: 0 4px 14px rgba(0,0,0,.12); z-index: 1000; pointer-events: none;
}
.toast-fade-enter-active, .toast-fade-leave-active { transition: opacity .25s, transform .25s; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }
</style>
