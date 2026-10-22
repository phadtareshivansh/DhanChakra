import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { TokenResponse } from '../types/api'

const baseURL = import.meta.env.VITE_API_URL

if (!baseURL) {
  throw new Error(
    'VITE_API_URL is not set. Define it in .env (e.g. http://localhost:8000/api/v1) — see .env.example.'
  )
}

const TOKEN_KEY = 'dhanchakra_token'
const REFRESH_KEY = 'dhanchakra_refresh_token'
const USER_KEY = 'dhanchakra_user'

const api = axios.create({
  baseURL,
  timeout: 60000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// A refresh is shared by every request that arrives while it is in flight,
// so a page that fires six calls at once does not fire six refreshes (the
// refresh token is single-use, and the second attempt would be refused).
let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return null
  try {
    const res = await axios.post<TokenResponse>(
      `${baseURL}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 30000 }
    )
    const token = res.data.access_token
    localStorage.setItem(TOKEN_KEY, token)
    if (res.data.refresh_token) {
      localStorage.setItem(REFRESH_KEY, res.data.refresh_token)
    }
    if (res.data.user) {
      localStorage.setItem(USER_KEY, JSON.stringify(res.data.user))
    }
    return token
  } catch {
    return null
  }
}

function endSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login'
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    const status = error.response?.status
    const url = original?.url || ''

    // The access token is short-lived. On a 401 that is not itself an
    // auth endpoint, try to refresh it once and replay the request, so a
    // working session is not thrown out every few minutes.
    const isAuthCall = url.includes('/auth/login') || url.includes('/auth/refresh')
    if (status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true
      if (!refreshInFlight) {
        refreshInFlight = refreshAccessToken().finally(() => {
          refreshInFlight = null
        })
      }
      const token = await refreshInFlight
      if (token) {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      }
    }

    if (status === 401) {
      endSession()
    }
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export default api
