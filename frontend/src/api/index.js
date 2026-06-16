import axios from 'axios'

// withCredentials so the HTTP-only session cookie is sent with every request.
const api = axios.create({ baseURL: '/api', withCredentials: true })

// On 401, bounce to the login page (unless we're already on an auth page or
// just probing /auth/me on startup).
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status
    const url = err?.config?.url || ''
    if (status === 401 && !url.includes('/auth/')) {
      const path = window.location.pathname
      if (path !== '/login' && path !== '/register') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(err)
  },
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const register = (data) => api.post('/auth/register', data)
export const login = (identifier, password) => api.post('/auth/login', { identifier, password })
export const logout = () => api.post('/auth/logout')
export const fetchMe = () => api.get('/auth/me')
export const verifyEmail = (token) => api.get('/auth/verify', { params: { token } })
export const createInvite = (data = {}) => api.post('/auth/invites', data)
export const googleLoginUrl = '/api/auth/google/login'

// ── Invoices ─────────────────────────────────────────────────────────────────

export const detectCodes = (files) => {
  const form = new FormData()
  const list = Array.isArray(files) ? files : [files]
  for (const f of list) form.append('files', f)
  return api.post('/invoices/scan/detect', form)
}

export const scanInvoice = (files) => {
  const form = new FormData()
  const list = Array.isArray(files) ? files : [files]
  for (const f of list) form.append('files', f)
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
export const setInvoiceSyncStatus = (id, sync_status) => api.patch(`/invoices/${id}/sync-status`, { sync_status })
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
export const generateCsr = (force = false) => api.post('/settings/afip/generate-csr', null, { params: force ? { force: true } : {} })
export const downloadCsrUrl = '/api/settings/afip/download-csr'
export const uploadCert = (certPem) => api.post('/settings/afip/upload-cert', { cert_pem: certPem })
export const verifyAfipConnection = () => api.post('/settings/afip/verify-connection')
export const testNotification = () => api.post('/settings/test-notification')

// ── CUIT → Razón Social ──────────────────────────────────────────────────────

export const diagnoseCuit = (cuit) => api.get(`/cuit/${encodeURIComponent(cuit)}/diagnose`)
export const listCuits = () => api.get('/cuits')
