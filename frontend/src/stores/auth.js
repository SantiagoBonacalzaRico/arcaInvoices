import { defineStore } from 'pinia'
import * as api from '../api'

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
      this.user = data
      return data
    },
    async logout() {
      try { await api.logout() } catch { /* ignore */ }
      this.user = null
    },
  },
})
