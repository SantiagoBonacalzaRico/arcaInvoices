<template>
  <div>
    <div class="list-header">
      <h1 class="page-title">Facturas</h1>
      <router-link to="/capture" class="btn btn-primary">+ Nueva</router-link>
    </div>

    <div class="filters card">
      <select v-model="filterStatus" @change="load">
        <option value="">Todos los estados</option>
        <option value="pending">Pendiente</option>
        <option value="synced">Sincronizado</option>
        <option value="error">Error</option>
      </select>
    </div>

    <div v-if="loading" class="center muted">Cargando…</div>

    <div v-else-if="invoices.length === 0" class="card center muted">
      No hay facturas. <router-link to="/capture">Escaneá una.</router-link>
    </div>

    <div v-else>
      <div class="card invoice-row" v-for="inv in invoices" :key="inv.id">
        <div v-if="editing !== inv.id" class="inv-view">
          <div class="inv-main">
            <span class="inv-number">{{ inv.invoice_number }}</span>
            <span :class="['badge', `badge-${inv.sync_status}`]">{{ inv.sync_status }}</span>
          </div>
          <div class="inv-meta">
            <span>CUIT: <strong>{{ inv.cuit }}</strong></span>
            <span>Fecha: <strong>{{ inv.invoice_date }}</strong></span>
            <span>Total: <strong>${{ Number(inv.total_amount).toLocaleString('es-AR', {minimumFractionDigits:2}) }}</strong></span>
            <span v-if="inv.category" class="muted">{{ inv.category }}</span>
          </div>
          <div class="inv-actions">
            <button class="btn btn-outline btn-sm" @click="startEdit(inv)">Editar</button>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { listInvoices, updateInvoice, deleteInvoice } from '../api'

const invoices = ref([])
const loading  = ref(true)
const filterStatus = ref('')
const editing  = ref(null)
const editForm = reactive({})

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

async function remove(id) {
  if (!confirm('¿Eliminar esta factura?')) return
  await deleteInvoice(id)
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; }
.list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.filters { padding: .75rem 1rem; }
.filters select { padding: .45rem .7rem; border-radius: 8px; border: 1.5px solid #d0d7de; font-size: .9rem; }
.invoice-row { margin-bottom: .75rem; }
.inv-main { display: flex; align-items: center; gap: .75rem; margin-bottom: .4rem; }
.inv-number { font-weight: 700; font-size: 1rem; }
.inv-meta { display: flex; flex-wrap: wrap; gap: .75rem 1.5rem; font-size: .88rem; color: #555; margin-bottom: .5rem; }
.inv-actions { display: flex; gap: .5rem; }
.btn-sm { padding: .3rem .75rem; font-size: .8rem; }
.muted { color: #888; }
.center { text-align: center; padding: 2rem; }
.edit-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: .5rem 1rem; margin-bottom: .75rem; }
.edit-grid .form-group { margin-bottom: 0; }
</style>
