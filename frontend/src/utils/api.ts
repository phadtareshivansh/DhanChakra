import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL

if (!baseURL) {
  throw new Error(
    'VITE_API_URL is not set. Define it in .env (e.g. http://localhost:8000/api/v1) — see .env.example.'
  )
}

const api = axios.create({
  baseURL,
  timeout: 60000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('dhanchakra_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('dhanchakra_token')
      localStorage.removeItem('dhanchakra_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export default api
