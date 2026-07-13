<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchOptions } from '../api'

const props = defineProps({
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const options = ref({ models: [], resolutions: ['480p', '720p', '1080p'], durations: [5, 10] })

const form = reactive({
  mode: 'text',
  prompt:
    '一只戴着红色皮夹克的卡通角色在河边钓鱼，费了好大劲钓上一条大鱼，立刻引来一大群人围观。',
  duration: 5,
  resolution: '720p',
  model: '',
  first_frame: '',
  last_frame: '',
  imagesText: '', // 每行一个 asset id
})

onMounted(async () => {
  try {
    const data = await fetchOptions()
    options.value = data
    form.model = data.models?.[0] || ''
  } catch (e) {
    ElMessage.warning(`加载模型列表失败：${e.message}`)
  }
})

function onSubmit() {
  if (!form.prompt.trim()) {
    ElMessage.warning('请输入提示词')
    return
  }
  const payload = {
    mode: form.mode,
    prompt: form.prompt.trim(),
    duration: form.duration,
    resolution: form.resolution,
    model: form.model || undefined,
  }
  if (form.mode === 'image') {
    payload.first_frame = form.first_frame.trim() || undefined
    payload.last_frame = form.last_frame.trim() || undefined
    const images = form.imagesText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    if (images.length) payload.images = images
  }
  emit('submit', payload)
}
</script>

<template>
  <el-card shadow="never" class="form-card">
    <template #header>
      <div class="card-title">生成参数</div>
    </template>

    <el-form label-position="top">
      <el-form-item label="生成模式">
        <el-radio-group v-model="form.mode">
          <el-radio-button label="text">文生视频</el-radio-button>
          <el-radio-button label="image">图生视频 / 首尾帧</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="提示词 Prompt">
        <el-input
          v-model="form.prompt"
          type="textarea"
          :rows="5"
          placeholder="描述你想生成的视频画面……"
        />
      </el-form-item>

      <div class="row">
        <el-form-item label="时长（秒）" class="col">
          <el-select v-model="form.duration">
            <el-option v-for="d in options.durations" :key="d" :label="`${d}s`" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="分辨率" class="col">
          <el-select v-model="form.resolution">
            <el-option v-for="r in options.resolutions" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型" class="col">
          <el-select v-model="form.model">
            <el-option v-for="m in options.models" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
      </div>

      <template v-if="form.mode === 'image'">
        <el-divider content-position="left">图像引导（可选）</el-divider>
        <el-form-item label="首帧图 URL (first_frame)">
          <el-input v-model="form.first_frame" placeholder="https://... 公网图片地址" />
        </el-form-item>
        <el-form-item label="尾帧图 URL (last_frame)">
          <el-input v-model="form.last_frame" placeholder="https://... 公网图片地址" />
        </el-form-item>
        <el-form-item label="素材 asset id（每行一个，images）">
          <el-input
            v-model="form.imagesText"
            type="textarea"
            :rows="2"
            placeholder="asset://asset-xxxx"
          />
          <div class="hint">需先通过中转方上传接口获取 asset id；本地上传暂未接入。</div>
        </el-form-item>
      </template>

      <el-button type="primary" size="large" :loading="props.loading" @click="onSubmit">
        {{ props.loading ? '生成中…' : '提交生成' }}
      </el-button>
    </el-form>
  </el-card>
</template>

<style scoped>
.card-title {
  font-weight: 600;
}
.row {
  display: flex;
  gap: 12px;
}
.col {
  flex: 1;
}
.hint {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
</style>
