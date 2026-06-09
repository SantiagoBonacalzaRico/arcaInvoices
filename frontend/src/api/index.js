import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── Invoices ─────────────────────────────────────────────────────────────────

export const scanInvoice = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/invoices/scan', form)
}

export const saveImage = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/invoices/scan/save-image', form)
}

export const createInvoice = (data) => api.post('/invoices', data)
export const listInvoices = (params = {}) => api.get('/invoices', { params })
export const getInvoice = (id) => api.get(`/invoices/${id}`)
export const updateInvoice = (id, data) => api.put(`/invoices/${id}`, data)
export const deleteInvoice = (id) => api.delete(`/invoices/${id}`)
export const recordCorrection = (data) => api.post('/invoices/corrections', data)

// ── Sync ──────────────────────────────────────────────────────────────────────

export const triggerSync = () => api.post('/sync/trigger')
export const syncStatus = () => api.get('/sync/status')
export const syncHistory = (limit = 20) => api.get('/sync/history', { params: { limit } })

// ── Settings ─────────────────────────────────────────────────────────────────

export const getSettings = () => api.get('/settings')
export const updateSettings = (data) => api.put('/settings', data)
export const getAfipSetupGuide = () => api.get('/settings/afip-setup-guide')
export const generateCsr = () => api.post('/settings/afip/generate-csr')
export const downloadCsrUrl = '/api/settings/afip/download-csr'
export const uploadCert = (certPem) => api.post('/settings/afip/upload-cert', { cert_pem: certPem })
export const verifyAfipConnection = () => api.post('/settings/afip/verify-connection')
export const testNotification = () => api.post('/settings/test-notification')
