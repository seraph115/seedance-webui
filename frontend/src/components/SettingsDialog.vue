<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getSettings, saveSettings, fetchOptions } from '../api'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const info = ref({ api_key_masked: '', api_key_source: 'unset', api_base: '' })
const newKey = ref('')
const apiBase = ref('')

const SOURCE_LABEL = { file: '文件', env: '环境变量', unset: '未配置' }

async function load() {
  loading.value = true
  try {
    info.value = await getSettings()
    apiBase.value = info.value.api_base || ''
    newKey.value = ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) load()
  }
)

async function onSave() {
  saving.value = true
  try {
    const payload = { api_base: apiBase.value }
    if (newKey.value.trim()) payload.api_key = newKey.value.trim()
    info.value = await saveSettings(payload)
    apiBase.value = info.value.api_base || ''
    newKey.value = ''
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  try {
    await fetchOptions()
    ElMessage.success('连接正常')
  } catch (e) {
    ElMessage.error('连接失败：' + e.message)
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="设置"
    width="480px"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-form v-loading="loading" label-width="90px">
      <el-form-item label="当前 Key">
        <span>{{ info.api_key_masked || '（未配置）' }}</span>
        <el-tag size="small" style="margin-left: 8px">{{ SOURCE_LABEL[info.api_key_source] }}</el-tag>
      </el-form-item>
      <el-form-item label="新 API_KEY">
        <el-input v-model="newKey" type="password" show-password placeholder="留空则不修改" />
      </el-form-item>
      <el-form-item label="API_BASE">
        <el-input v-model="apiBase" placeholder="https://token.manateeai.com" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :loading="testing" @click="onTest">测试连接</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>
