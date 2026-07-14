import axios from 'axios'

// 与后端同源；开发时由 Vite proxy 转发到 :8008。带上 Cookie 以携带会话。
const http = axios.create({ baseURL: '/api', timeout: 200000, withCredentials: true })

// 统一错误信息；遇到 401 把全局登录态切回未登录（动态 import 避免与 useAuth 循环依赖）
http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      import('./composables/useAuth').then((m) => {
        m.authed.value = false
      })
    }
    const detail = err?.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(detail))
  }
)

export function fetchOptions() {
  return http.get('/models').then((r) => r.data)
}

// payload: { mode, prompt, duration, resolution, model, first_frame?, last_frame?, images? }
export function generate(payload) {
  return http.post('/generate', payload).then((r) => r.data)
}

export function fetchStatus(taskId) {
  return http.get(`/status/${taskId}`).then((r) => r.data)
}

// ---- 鉴权 ----
export function login(username, password) {
  return http.post('/login', { username, password }).then((r) => r.data)
}

export function logout() {
  return http.post('/logout').then((r) => r.data)
}

export function getSession() {
  return http.get('/session').then((r) => r.data)
}

// ---- 设置 ----
export function getSettings() {
  return http.get('/settings').then((r) => r.data)
}

export function saveSettings(payload) {
  return http.put('/settings', payload).then((r) => r.data)
}
