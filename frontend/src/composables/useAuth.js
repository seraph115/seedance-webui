import { ref } from 'vue'
import { login as apiLogin, logout as apiLogout, getSession } from '../api'

// 模块级单例：全应用共享同一份登录状态（api.js 的 401 拦截器也会改它）
export const authed = ref(false)
export const ready = ref(false) // 首次会话检查完成前为 false

export function useAuth() {
  async function checkSession() {
    try {
      const { authed: a } = await getSession()
      authed.value = !!a
    } catch {
      authed.value = false
    } finally {
      ready.value = true
    }
  }

  async function login(password) {
    await apiLogin(password)
    authed.value = true
  }

  async function logout() {
    try {
      await apiLogout()
    } finally {
      authed.value = false
    }
  }

  return { authed, ready, checkSession, login, logout }
}
