import { defineStore } from 'pinia'
import * as api from '../api'
import { setToken } from '../lib/native'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    ready: false, // true once we've checked /auth/me at least once
  }),
  getters: {
    isAuthenticated: (s) => !!s.user,
    isAdmin: (s) => !!s.user?.is_admin,
  },
  actions: {
    async fetchMe() {
      try {
        const { data } = await api.fetchMe()
        this.user = data
      } catch {
        this.user = null
      } finally {
        this.ready = true
      }
      return this.user
    },
    async login(identifier, password) {
      const { data } = await api.login(identifier, password)
      // On native, persist the bearer token (web ignores it; uses the cookie).
      await setToken(data.access_token)
      this.user = data
      return data
    },
    async logout() {
      try { await api.logout() } catch { /* ignore */ }
      await setToken(null)
      this.user = null
    },
  },
})
