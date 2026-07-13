import axios from 'axios'

// 与后端同源；开发时由 Vite proxy 转发到 :8000
const http = axios.create({ baseURL: '/api', timeout: 200000 })

// 统一把后端 detail 错误信息抛出来，方便页面提示
http.interceptors.response.use(
  (r) => r,
  (err) => {
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
