<script setup>
defineProps({
  history: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
})
const emit = defineEmits(['select', 'remove', 'clear'])

const TERMINAL = ['SUCCESS', 'FAILURE', 'FAILED', 'FAIL']

function tagType(s) {
  if (s === 'SUCCESS') return 'success'
  if (['FAILURE', 'FAILED', 'FAIL'].includes(s)) return 'danger'
  return 'warning' // 非终态一律进行中
}
const isPending = (s) => !TERMINAL.includes(s)
</script>

<template>
  <el-card shadow="never" class="history-card">
    <template #header>
      <div class="header">
        <span class="card-title">历史记录（{{ history.length }}）</span>
        <el-button v-if="history.length" text size="small" @click="emit('clear')">清空</el-button>
      </div>
    </template>

    <el-empty v-if="!history.length" description="暂无记录" :image-size="60" />

    <div v-else class="list">
      <div
        v-for="item in history"
        :key="item.id"
        class="item"
        :class="{ active: item.taskId === activeId }"
        @click="emit('select', item)"
      >
        <div class="line1">
          <el-tag size="small" :type="tagType(item.status)">{{ item.status }}</el-tag>
          <span v-if="isPending(item.status) && item.progress" class="prog">{{ item.progress }}</span>
          <span class="mode">{{ item.mode === 'text' ? '文生' : '图生' }}</span>
          <span class="time">{{ item.time }}</span>
          <el-button
            text
            size="small"
            class="del"
            @click.stop="emit('remove', item.id)"
          >删除</el-button>
        </div>
        <div class="prompt">{{ item.prompt }}</div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font-weight: 600;
}
.list {
  max-height: 520px;
  overflow-y: auto;
}
.item {
  padding: 10px 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
}
.item:hover {
  background: #f5f7fa;
}
.item.active {
  background: #ecf5ff;
  box-shadow: inset 3px 0 0 #409eff;
}
.prog {
  font-size: 12px;
  color: #e6a23c;
  font-weight: 600;
}
.line1 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mode {
  font-size: 12px;
  color: #606266;
}
.time {
  font-size: 12px;
  color: #c0c4cc;
}
.del {
  margin-left: auto;
}
.prompt {
  margin-top: 4px;
  font-size: 13px;
  color: #303133;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
