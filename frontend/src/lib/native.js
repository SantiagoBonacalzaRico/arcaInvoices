// Native-platform helpers (Capacitor). Safe on web: Capacitor.isNativePlatform()
// is false in the browser, where we rely on the HTTP-only session cookie instead
// of a stored bearer token.
import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'

const TOKEN_KEY = 'auth_token'
let _token = null // in-memory cache so axios can read it synchronously

export const isNative = () => Capacitor.isNativePlatform()

// Tag the root element so CSS can target the native apps only (PWA unaffected).
if (typeof document !== 'undefined' && isNative()) {
  document.documentElement.classList.add('native')
}

export function getTokenSync() {
  return _token
}

// Hydrate the token at startup (native only).
export async function loadToken() {
  if (!isNative()) return null
  try {
    const { value } = await Preferences.get({ key: TOKEN_KEY })
    _token = value || null
  } catch {
    _token = null
  }
  return _token
}

// Persist (native) + update the in-memory cache. On web this is a no-op store
// (the cookie is the source of truth) but still clears the cache.
export async function setToken(token) {
  _token = token || null
  if (!isNative()) return
  try {
    if (token) await Preferences.set({ key: TOKEN_KEY, value: token })
    else await Preferences.remove({ key: TOKEN_KEY })
  } catch {
    /* ignore */
  }
}
