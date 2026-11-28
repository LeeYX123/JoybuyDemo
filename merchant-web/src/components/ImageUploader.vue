<script setup>
import { computed, ref } from 'vue'

import { merchantUpload } from '@/lib/api'

const props = defineProps({
  // 单图传字符串，多图传数组；由 multiple 决定形态。
  modelValue: { type: [String, Array], default: '' },
  purpose: { type: String, default: 'product' },
  multiple: { type: Boolean, default: false },
  max: { type: Number, default: 5 },
  maxSizeMb: { type: Number, default: 1 },
  label: { type: String, default: '图片' },
  hint: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const uploading = ref(false)
const error = ref('')
const inputEl = ref(null)

const images = computed(() => {
  if (props.multiple) return Array.isArray(props.modelValue) ? props.modelValue : []
  return props.modelValue ? [props.modelValue] : []
})

const canAdd = computed(() =>
  props.multiple ? images.value.length < props.max : !images.value.length,
)
const accept = 'image/jpeg,image/png,image/webp'

function pick() {
  if (!canAdd.value || uploading.value) return
  inputEl.value?.click()
}

function push(value) {
  if (!props.multiple) {
    emit('update:modelValue', value)
    return
  }
  // 内容寻址存储对相同图片返回同一个 URL，重复追加没有意义，直接跳过。
  if (images.value.includes(value)) return
  emit('update:modelValue', [...images.value, value])
}

function removeAt(index) {
  if (props.multiple) {
    emit(
      'update:modelValue',
      images.value.filter((_, i) => i !== index),
    )
  } else {
    emit('update:modelValue', '')
  }
}

function moveFirst(index) {
  if (!props.multiple || index === 0) return
  const next = [...images.value]
  const [item] = next.splice(index, 1)
  next.unshift(item)
  emit('update:modelValue', next)
}

// 一次选多张就逐张上传：单张失败不影响其他张，错误逐条累积提示。
async function onFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return

  error.value = ''
  uploading.value = true
  const failures = []
  let added = 0
  try {
    for (const file of files) {
      if (props.multiple && images.value.length + added >= props.max) {
        failures.push(`最多 ${props.max} 张，多余的已跳过`)
        break
      }
      if (file.size > props.maxSizeMb * 1024 * 1024) {
        failures.push(`${file.name} 超过 ${props.maxSizeMb}MB`)
        continue
      }
      try {
        const payload = await merchantUpload(file, props.purpose)
        push(payload.media.url)
        added += 1
      } catch (uploadError) {
        failures.push(`${file.name}：${uploadError.message}`)
      }
    }
  } finally {
    uploading.value = false
  }
  if (failures.length) error.value = failures.join('；')
}

defineExpose({ pick })
</script>

<template>
  <div class="uploader">
    <div class="uploader__label">
      <span>{{ label }}</span>
      <small>JPG / PNG / WebP，单张不超过 {{ maxSizeMb }}MB</small>
    </div>

    <div class="uploader__grid">
      <figure v-for="(url, index) in images" :key="url + index" class="uploader__item">
        <img :src="url" :alt="`${label} ${index + 1}`" />
        <span v-if="multiple && index === 0" class="uploader__main">主图</span>
        <div class="uploader__tools">
          <button
            v-if="multiple && index > 0"
            type="button"
            title="设为主图"
            @click="moveFirst(index)"
          >
            主图
          </button>
          <button type="button" title="移除" @click="removeAt(index)">移除</button>
        </div>
      </figure>

      <button v-if="canAdd" type="button" class="uploader__add" :disabled="uploading" @click="pick">
        <template v-if="uploading">上传中…</template>
        <template v-else>+ 上传</template>
      </button>
    </div>

    <input
      ref="inputEl"
      class="uploader__input"
      type="file"
      :accept="accept"
      :multiple="multiple"
      @change="onFiles"
    />

    <p v-if="hint" class="uploader__hint">{{ hint }}</p>
    <p v-if="error" class="notice notice--error">{{ error }}</p>
  </div>
</template>

<style scoped>
.uploader {
  margin-top: 12px;
}

.uploader__label {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}

.uploader__label span {
  font-size: 13px;
  font-weight: 600;
}

.uploader__label small {
  color: var(--muted);
  font-size: 11px;
}

.uploader__grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.uploader__item {
  position: relative;
  margin: 0;
  width: 92px;
  height: 92px;
  border: 1px solid var(--line);
  border-radius: 4px;
  overflow: hidden;
  background: #f6f8fb;
}

.uploader__item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fff;
}

.uploader__main {
  position: absolute;
  top: 0;
  left: 0;
  background: var(--red);
  color: #fff;
  font-size: 10px;
  padding: 1px 5px;
  border-bottom-right-radius: 4px;
}

.uploader__tools {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  justify-content: center;
  gap: 2px;
  background: rgb(12 24 43 / 62%);
  padding: 2px 0;
  opacity: 0;
  transition: opacity 120ms ease;
}

.uploader__item:hover .uploader__tools {
  opacity: 1;
}

.uploader__tools button {
  border: none;
  background: transparent;
  color: #fff;
  font-size: 11px;
  cursor: pointer;
  padding: 1px 4px;
}

.uploader__add {
  width: 92px;
  height: 92px;
  border: 1px dashed var(--line);
  border-radius: 4px;
  background: #fafbfd;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
}

.uploader__add:hover:not(:disabled) {
  border-color: var(--red);
  color: var(--red);
}

.uploader__add:disabled {
  cursor: progress;
  opacity: 0.7;
}

.uploader__input {
  display: none;
}

.uploader__hint {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 11px;
}
</style>
