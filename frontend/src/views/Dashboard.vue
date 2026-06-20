<template>
  <div>
    <h1 class="page-title">Dashboard</h1>

    <div class="stats-grid">
      <div class="card stat-card">
        <div class="stat-number">{{ stats.pending }}</div>
        <div class="stat-label">Facturas por cargar</div>
      </div>
      <div class="card stat-card">
        <div class="stat-number">{{ stats.synced }}</div>
        <div class="stat-label">Cargadas en SiRADIG</div>
      </div>
      <div class="card stat-card highlight" v-if="status">
        <div class="stat-number">{{ formatDate(status.next_sync_date) }}</div>
        <div class="stat-label">Fecha objetivo de carga</div>
      </div>
    </div>

    <div class="card actions">
      <router-link to="/capture" class="btn btn-primary">+ Escanear factura</router-link>
      <router-link v-if="!native" to="/siradig" class="btn btn-outline">Cargar en SiRADIG →</router-link>
    </div>

    <div class="card" v-if="warning">
      <p class="warning-msg">{{ warning }}</p>
    </div>

    <div class="card" v-if="auth.isAdmin">
      <h2>Invitaciones (admin)</h2>
      <p class="muted small">Generá un código para invitar a un nuevo usuario.</p>
      <div class="invite-row">
        <input v-model="inviteEmail" type="email" placeholder="email del invitado (opcional)" />
        <button class="btn btn-outline" @click="makeInvite" :disabled="inviting">
          {{ inviting ? 'Generando…' : 'Generar invitación' }}
        </button>
      </div>
      <div v-if="inviteUrl" class="invite-result">
        <p class="small">Enviá este enlace al invitado:</p>
        <code class="invite-link">{{ inviteUrl }}</code>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { syncStatus, listInvoices, createInvite } from '../api'
import { useAuthStore } from '../stores/auth'
import { isNative } from '../lib/native'

const auth = useAuthStore()
const native = isNative()
const status = ref(null)
const invoices = ref([])

const inviteEmail = ref('')
const inviteUrl = ref('')
const inviting = ref(false)

async function makeInvite() {
  inviting.value = true
  inviteUrl.value = ''
  try {
    const body = inviteEmail.value.trim() ? { email: inviteEmail.value.trim() } : {}
    const { data } = await createInvite(body)
    inviteUrl.value = data.url
  } catch (e) {
    inviteUrl.value = ''
    alert(e?.response?.data?.detail || 'No se pudo generar la invitación.')
  } finally {
    inviting.value = false
  }
}

const stats = computed(() => ({
  pending: invoices.value.filter(i => i.sync_status === 'pending').length,
  synced:  invoices.value.filter(i => i.sync_status === 'synced').length,
}))

const warning = computed(() => {
  if (!status.value) return null
  const daysLeft = status.value.next_sync_date
    ? Math.ceil((new Date(status.value.next_sync_date) - new Date()) / 86400000)
    : null
  if (daysLeft !== null && daysLeft <= 7 && stats.value.pending > 0)
    return `⚠️ Faltan ${daysLeft} días para la fecha objetivo y tenés ${stats.value.pending} factura(s) por cargar en SiRADIG.`
  return null
})

const formatDate = (d) => d ? new Date(d).toLocaleDateString('es-AR') : '—'

async function load() {
  const [s, inv] = await Promise.all([syncStatus(), listInvoices()])
  status.value = s.data
  invoices.value = inv.data
}

onMounted(load)
</script>

<style scoped>
.page-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 1.25rem; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
.stat-card { text-align: center; }
.stat-card.highlight { border-left: 4px solid #1976d2; }
.stat-number { font-size: 2rem; font-weight: 800; color: #1976d2; }
.stat-label  { font-size: .8rem; color: #666; margin-top: .3rem; }
.muted { color: #888; }
.actions { display: flex; gap: 1rem; flex-wrap: wrap; }
.warning-msg { color: #e65100; font-weight: 600; }
h2 { font-size: 1rem; margin-bottom: .5rem; color: #333; }
.small { font-size: .8rem; }
.invite-row { display: flex; gap: .5rem; margin-top: .5rem; flex-wrap: wrap; }
.invite-row input { flex: 1; min-width: 200px; padding: .55rem .8rem; border: 1.5px solid #d0d7de; border-radius: 8px; }
.invite-result { margin-top: .75rem; }
.invite-link { display: block; word-break: break-all; background: #f5f7fa; padding: .5rem .7rem; border-radius: 6px; font-size: .8rem; }
</style>
