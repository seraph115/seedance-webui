<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../composables/useAuth'

const { login } = useAuth()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  if (!password.value) {
    error.value = '请输入密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await login(password.value)
    ElMessage.success('登录成功')
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">🎬 SeeDance 登录</h2>
      <el-input
        v-model="password"
        type="password"
        placeholder="管理员密码"
        show-password
        size="large"
        @keyup.enter="onSubmit"
      />
      <p v-if="error" class="err">{{ error }}</p>
      <el-button type="primary" size="large" :loading="loading" class="btn" @click="onSubmit">
        登录
      </el-button>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
}
.login-card {
  width: 360px;
}
.title {
  text-align: center;
  margin: 0 0 20px;
}
.btn {
  width: 100%;
  margin-top: 16px;
}
.err {
  color: #f56c6c;
  font-size: 13px;
  margin: 8px 0 0;
}
</style>
