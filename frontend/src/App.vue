<script setup>
import { ref, computed, onUnmounted, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GenerateForm from './components/GenerateForm.vue'
import ResultPanel from './components/ResultPanel.vue'
import HistoryList from './components/HistoryList.vue'
import LoginView from './components/LoginView.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { useAuth } from './composables/useAuth'
import { generate, fetchStatus } from './api'
import { useHistory } from './composables/useHistory'

const { history, add, update, remove, clear } = useHistory()
const { authed, ready, checkSession, logout } = useAuth()
const showSettings = ref(false)

const POLL_MS = 5000
// 终态：其余一律视为“进行中”，需要继续轮询
const TERMINAL = ['SUCCESS', 'FAILURE', 'FAILED', 'FAIL']
const isTerminal = (s) => TERMINAL.includes(s)

const loading = ref(false)
const selectedId = ref('') // 当前在结果区查看的 taskId
const submitError = ref('') // 提交(调用大模型)失败的错误信息

// 结果区数据响应式派生自 history，任务在后台被更新时会自动反映
const current = computed(
  () => history.value.find((h) => h.taskId === selectedId.value) || null
)

// 每个任务一个独立轮询器：taskId -> intervalId（非响应式）
const pollers = {}

function startPolling(taskId) {
  if (pollers[taskId]) return // 已在轮询，避免重复
  const poll = async () => {
    try {
      const res = await fetchStatus(taskId)
      // 查询成功：清除上一次的查询异常
      const patch = { status: res.status, progress: res.progress, message: res.message, pollError: '' }
      if (res.status === 'SUCCESS') patch.videoUrl = res.video_url || ''
      update(taskId, patch)
      if (isTerminal(res.status)) {
        stopPolling(taskId)
        // 仅对当前查看的任务弹提示，避免后台任务打扰
        if (selectedId.value === taskId) {
          if (res.status === 'SUCCESS') ElMessage.success('视频生成完成')
          else ElMessage.error(res.message || '生成失败')
        }
      }
    } catch (e) {
      // 单次查询失败不中断轮询，但把后台异常写到该任务上，展示到面板
      console.warn('查询失败：', taskId, e.message)
      update(taskId, { pollError: e.message })
    }
  }
  poll()
  pollers[taskId] = setInterval(poll, POLL_MS)
}

function stopPolling(taskId) {
  if (pollers[taskId]) {
    clearInterval(pollers[taskId])
    delete pollers[taskId]
  }
}

function stopAll() {
  Object.keys(pollers).forEach(stopPolling)
}

function nowStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function onSubmit(payload) {
  loading.value = true
  submitError.value = ''
  try {
    const { task_id } = await generate(payload)
    add({
      taskId: task_id,
      time: nowStr(),
      mode: payload.mode,
      prompt: payload.prompt,
      model: payload.model || '',
      status: 'IN_PROGRESS',
      progress: '0%',
      videoUrl: '',
      message: '',
    })
    selectedId.value = task_id
    ElMessage.success(`任务已提交：${task_id}`)
    startPolling(task_id) // 后台并行轮询，不影响其他任务
  } catch (e) {
    // 调用大模型提交失败：既弹提示，也固定展示到结果面板
    submitError.value = e.message
    selectedId.value = ''
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// 点历史：切换查看的任务；非终态则确保其轮询在跑
function onSelect(item) {
  submitError.value = '' // 切到具体任务时清掉提交错误
  selectedId.value = item.taskId
  if (!isTerminal(item.status)) startPolling(item.taskId)
}

function onRemove(id) {
  stopPolling(id) // useHistory 中 id === taskId
  remove(id)
}

function onClear() {
  stopAll()
  clear()
}

// 恢复历史中未完成任务的轮询（startPolling 自带去重，重复调用安全）
function resumePolling() {
  history.value.forEach((h) => {
    if (!isTerminal(h.status)) startPolling(h.taskId)
  })
}

// 登录态 false→true 时恢复轮询：覆盖“加载时已登录”与“会话内登录”两种情况
watch(authed, (now, prev) => {
  if (now && !prev) resumePolling()
})

// 挂载时确认会话；已登录会触发上面的 watch 从而恢复轮询
onMounted(checkSession)

onUnmounted(stopAll)
</script>

<template>
  <LoginView v-if="ready && !authed" />

  <el-container v-else-if="ready && authed" class="app">
    <el-header class="header">
      <span class="logo">🎬 SeeDance 视频生成测试台</span>
      <span class="sub">输入提示词，测试 dreamina-seedance 视频生成（多任务并行）</span>
      <span class="spacer" />
      <el-button text @click="showSettings = true">⚙️ 设置</el-button>
      <el-button text @click="logout">退出登录</el-button>
    </el-header>

    <el-main>
      <div class="grid">
        <div class="left">
          <GenerateForm :loading="loading" @submit="onSubmit" />
        </div>
        <div class="middle">
          <ResultPanel
            :task-id="current?.taskId || ''"
            :status="current?.status || ''"
            :progress="current?.progress"
            :video-url="current?.videoUrl || ''"
            :message="current?.message || ''"
            :submit-error="submitError"
            :poll-error="current?.pollError || ''"
          />
        </div>
        <div class="right">
          <HistoryList
            :history="history"
            :active-id="selectedId"
            @select="onSelect"
            @remove="onRemove"
            @clear="onClear"
          />
        </div>
      </div>
    </el-main>

    <SettingsDialog v-model="showSettings" />
  </el-container>
</template>

<style scoped>
.app {
  min-height: 100vh;
}
.header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  border-bottom: 1px solid #ebeef5;
}
.logo {
  font-size: 20px;
  font-weight: 700;
}
.sub {
  color: #909399;
  font-size: 13px;
}
.spacer {
  flex: 1;
}
.grid {
  display: grid;
  /* 左（生成参数）与右（历史记录）同宽，中间结果区自适应 */
  grid-template-columns: 340px 1fr 340px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1100px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
