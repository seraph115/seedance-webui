<script setup>
import { computed } from 'vue'

const props = defineProps({
  taskId: { type: String, default: '' },
  status: { type: String, default: '' }, // QUEUED | NOT_START | IN_PROGRESS | SUCCESS | FAILURE ...
  progress: { type: [Number, String], default: null },
  videoUrl: { type: String, default: '' },
  message: { type: String, default: '' },
  submitError: { type: String, default: '' }, // 提交(调用大模型)失败
  pollError: { type: String, default: '' }, // 轮询查询的后台异常
})

// 终态：只有这两个算“结束”，其余一律视为“进行中”
const isSuccess = computed(() => props.status === 'SUCCESS')
const isFailure = computed(() => ['FAILURE', 'FAILED', 'FAIL'].includes(props.status))
const isPending = computed(
  () => !!props.taskId && !isSuccess.value && !isFailure.value
)

// progress 可能是 "0%" 这样的字符串，统一解析成数字
const pct = computed(() => {
  const n = parseFloat(String(props.progress ?? '').replace('%', ''))
  return Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0
})

// 各状态的中文阶段提示
const phaseLabel = computed(() => {
  const map = {
    QUEUED: '排队中，等待空闲算力…',
    NOT_START: '任务已受理，即将开始…',
    IN_PROGRESS: '正在生成视频…',
    RUNNING: '正在生成视频…',
    PROCESSING: '正在生成视频…',
  }
  return map[props.status] || '处理中…'
})

const tagType = computed(() => {
  if (isSuccess.value) return 'success'
  if (isFailure.value) return 'danger'
  return 'warning'
})
</script>

<template>
  <el-card shadow="never" class="result-card">
    <template #header>
      <div class="card-title">生成结果</div>
    </template>

    <!-- 提交失败：即使还没有 task_id 也固定展示错误 -->
    <el-alert
      v-if="submitError"
      type="error"
      :closable="false"
      show-icon
      title="调用大模型提交失败"
      :description="submitError"
    />

    <el-empty v-else-if="!taskId" description="尚未提交任务" />

    <template v-else>
      <div class="meta">
        <el-tag :type="tagType" effect="dark">{{ status || '—' }}</el-tag>
        <span class="task-id">task_id: {{ taskId }}</span>
      </div>

      <!-- 排队中 / 生成中：都显示进度条 + 阶段提示 -->
      <div v-if="isPending" class="pending">
        <el-alert
          v-if="pollError"
          type="warning"
          :closable="false"
          show-icon
          title="查询后台异常（仍在自动重试）"
          :description="pollError"
          style="margin-bottom: 12px"
        />
        <div class="phase">{{ phaseLabel }}</div>
        <el-progress
          :percentage="pct"
          :duration="10"
          :indeterminate="pct === 0"
          striped
          striped-flow
        />
        <div class="tip">视频生成通常需要几分钟，页面会每 5 秒自动刷新，请保持打开。</div>
      </div>

      <!-- 成功：播放器 -->
      <div v-else-if="isSuccess && videoUrl" class="video-wrap">
        <video :src="videoUrl" controls autoplay loop class="video" />
        <div class="links">
          <el-link type="primary" :href="videoUrl" target="_blank">在新窗口打开</el-link>
          <el-link type="success" :href="videoUrl" download>下载视频</el-link>
        </div>
      </div>

      <!-- 成功但没拿到地址（结构异常）：提示排查 -->
      <el-alert
        v-else-if="isSuccess && !videoUrl"
        type="warning"
        :closable="false"
        title="任务成功但未解析到视频地址，请查看后端日志的原始返回。"
        style="margin-top: 16px"
      />

      <!-- 失败：展示大模型返回的失败原因 -->
      <el-alert
        v-else-if="isFailure"
        type="error"
        :closable="false"
        show-icon
        title="生成失败"
        :description="message || '大模型未返回具体原因'"
        style="margin-top: 16px"
      />
    </template>
  </el-card>
</template>

<style scoped>
.card-title {
  font-weight: 600;
}
.meta {
  display: flex;
  align-items: center;
  gap: 12px;
}
.task-id {
  color: #909399;
  font-size: 12px;
  word-break: break-all;
}
.pending {
  margin-top: 16px;
}
.phase {
  font-size: 14px;
  color: #606266;
  margin-bottom: 10px;
}
.tip {
  margin-top: 10px;
  font-size: 12px;
  color: #c0c4cc;
}
.video-wrap {
  margin-top: 16px;
}
.video {
  width: 100%;
  border-radius: 8px;
  background: #000;
}
.links {
  margin-top: 8px;
  display: flex;
  gap: 16px;
}
</style>
