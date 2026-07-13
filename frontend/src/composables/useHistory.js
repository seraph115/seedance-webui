import { ref } from 'vue'

// 历史记录持久化到 localStorage。
// 记录结构：{ id, time, mode, prompt, model, taskId, videoUrl, status }
const STORAGE_KEY = 'seedance_history'

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

const history = ref(load())

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value))
}

export function useHistory() {
  // 新任务提交时先插入一条 IN_PROGRESS 记录，返回其 id 便于后续更新
  function add(record) {
    const entry = { id: `${record.taskId}`, status: 'IN_PROGRESS', ...record }
    history.value.unshift(entry)
    if (history.value.length > 50) history.value.pop()
    persist()
    return entry.id
  }

  function update(id, patch) {
    const item = history.value.find((h) => h.id === id)
    if (item) {
      Object.assign(item, patch)
      persist()
    }
  }

  function remove(id) {
    history.value = history.value.filter((h) => h.id !== id)
    persist()
  }

  function clear() {
    history.value = []
    persist()
  }

  return { history, add, update, remove, clear }
}
