<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

// 频道页 banner：按 Joybuy minihome 频道（/minihome/<channel_code>）各配一组
// 轮播图。与首页活动卡片不是一个模型/接口，这里是同一管理页里的独立子面板。

const state = reactive({
  channels: [],
  channelCode: '',
  items: [],
  loading: true,
  error: '',
  notice: '',
})

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({
  image: '',
  href: '',
  sortOrder: '',
  enabled: true,
})

const removeTarget = ref(null)
const removing = ref(false)
const movingId = ref('')

const currentChannel = computed(
  () => state.channels.find((item) => item.channel_code === state.channelCode) || null,
)
const channelLabel = computed(() => {
  const channel = currentChannel.value
  if (!channel) return ''
  return channel.name_zh ? `${channel.name_zh}（${channel.name}）` : channel.name
})

async function loadChannels() {
  state.error = ''
  try {
    const payload = await apiRequest('/channel-banners/channels')
    state.channels = payload.items || []
    if (!state.channelCode && state.channels.length) {
      state.channelCode = state.channels[0].channel_code
    }
  } catch (error) {
    state.error = error.message
  }
}

async function load() {
  if (!state.channelCode) {
    state.items = []
    state.loading = false
    return
  }
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest(
      `/channel-banners?channel_code=${encodeURIComponent(state.channelCode)}`,
    )
    state.items = payload.items || []
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectChannel() {
  state.notice = ''
  load()
}

function openCreate() {
  editorId.value = ''
  editor.image = ''
  editor.href = ''
  editor.sortOrder = ''
  editor.enabled = true
  editorError.value = ''
  editorOpen.value = true
}

function openEdit(row) {
  editorId.value = row.id
  editor.image = row.image_url || ''
  editor.href = row.href || ''
  editor.sortOrder = String(row.sort_order ?? '')
  editor.enabled = Boolean(row.enabled)
  editorError.value = ''
  editorOpen.value = true
}

function closeEditor() {
  if (editorBusy.value) return
  editorOpen.value = false
}

async function saveBanner() {
  editorBusy.value = true
  editorError.value = ''
  const body = {
    channel_code: state.channelCode,
    image_url: editor.image,
    href: editor.href,
    enabled: editor.enabled,
  }
  // 新增时留空 = 后端追加到该频道末尾；编辑时必须带上当前值。
  if (editorId.value || editor.sortOrder !== '') {
    body.sort_order = editor.sortOrder
  }
  try {
    if (editorId.value) {
      await adminWrite(`/channel-banners/${editorId.value}`, body, 'PATCH')
      state.notice = '频道 banner 已更新，购物端频道页即时生效。'
    } else {
      await adminWrite('/channel-banners', body)
      state.notice = '频道 banner 已新增。'
    }
    editorOpen.value = false
    await load()
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

function askRemove(row) {
  removeTarget.value = row
  removing.value = false
}

function closeRemove() {
  if (removing.value) return
  removeTarget.value = null
}

async function confirmRemove() {
  if (!removeTarget.value) return
  removing.value = true
  try {
    await adminWrite(`/channel-banners/${removeTarget.value.id}`, null, 'DELETE')
    state.notice = '已删除该频道 banner。'
    removeTarget.value = null
    await load()
  } catch (error) {
    state.error = error.message
    removeTarget.value = null
  } finally {
    removing.value = false
  }
}

async function move(row, direction) {
  movingId.value = row.id
  state.error = ''
  try {
    await adminWrite(`/channel-banners/${row.id}/actions`, {
      action: 'move',
      direction,
    })
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    movingId.value = ''
  }
}

async function toggle(row) {
  state.error = ''
  try {
    await adminWrite(`/channel-banners/${row.id}/actions`, { action: 'toggle' })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

onMounted(async () => {
  await loadChannels()
  await load()
})
</script>

<template>
  <section>
    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="card">
      <div class="card__body">
        <div class="channel-toolbar">
          <label class="channel-picker">
            <span class="field__label">频道</span>
            <select
              v-model="state.channelCode"
              :disabled="!state.channels.length"
              @change="selectChannel"
            >
              <option
                v-for="channel in state.channels"
                :key="channel.channel_code"
                :value="channel.channel_code"
              >
                {{ channel.name_zh ? `${channel.name_zh}（${channel.name}）` : channel.name }} ·
                {{ channel.channel_code }}
              </option>
            </select>
          </label>
          <div class="channel-toolbar__actions">
            <span class="tag">{{ state.items.length }} 张</span>
            <button
              type="button"
              class="btn btn--primary"
              :disabled="!state.channelCode"
              @click="openCreate"
            >
              新增 banner
            </button>
          </div>
        </div>

        <p v-if="!state.channels.length" class="empty-state">
          暂无可配置的频道（一级类目没有 minihome 频道映射）。
        </p>
        <p v-else-if="state.loading" class="inline-loading">加载中…</p>
        <table v-else-if="state.items.length" class="data-table">
          <thead>
            <tr>
              <th style="width: 200px">图片</th>
              <th>跳转链接</th>
              <th style="width: 90px">状态</th>
              <th style="width: 70px">顺序</th>
              <th class="actions-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in state.items"
              :key="row.id"
              :class="{ 'row--off': !row.enabled }"
            >
              <td>
                <img :src="row.image_url" alt="" class="channel-thumb" />
              </td>
              <td class="mono">{{ row.href || '—' }}</td>
              <td>
                <button
                  type="button"
                  class="tag"
                  :class="row.enabled ? 'tag--ok' : 'tag--warn'"
                  @click="toggle(row)"
                >
                  {{ row.enabled ? '启用中' : '已停用' }}
                </button>
              </td>
              <td class="num">{{ index + 1 }}</td>
              <td class="actions-col">
                <button
                  type="button"
                  class="btn btn--sm"
                  :disabled="index === 0 || movingId === row.id"
                  @click="move(row, 'up')"
                >
                  上移
                </button>
                <button
                  type="button"
                  class="btn btn--sm"
                  :disabled="index === state.items.length - 1 || movingId === row.id"
                  @click="move(row, 'down')"
                >
                  下移
                </button>
                <button type="button" class="btn btn--sm" @click="openEdit(row)">编辑</button>
                <button type="button" class="btn btn--sm btn--danger" @click="askRemove(row)">
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">该频道还没有 banner，频道页会显示默认渐变占位。</p>
      </div>
    </div>

    <AppModal
      :open="editorOpen"
      :title="editorId ? '编辑频道 banner' : '新增频道 banner'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="closeEditor"
      @confirm="saveBanner"
    >
      <p class="modal-lead">
        当前频道：<b>{{ channelLabel }}</b>
      </p>

      <ImageUploader
        v-model="editor.image"
        purpose="channel_banner"
        :max-size-mb="2"
        label="banner 图"
        hint="建议 1264×280（频道页与内容区同宽、高 280px）；仅支持本站上传。"
      />

      <div class="form-grid" style="margin-top: 12px">
        <label class="field">
          <span class="field__label">跳转链接（选填）</span>
          <input v-model="editor.href" type="text" placeholder="/c/kitchen 或 https://…" />
          <span class="field__hint">
            以 http(s):// 或 www. 开头按外链原样跳转，否则视为站内路径。留空则整张 banner 不可点。
          </span>
        </label>
        <label class="field">
          <span class="field__label">排序（选填）</span>
          <input
            v-model="editor.sortOrder"
            type="number"
            min="0"
            max="9999"
            placeholder="留空则排到最后"
          />
          <span class="field__hint">数字越小越靠前。</span>
        </label>
      </div>

      <label class="checkline" style="margin-top: 12px">
        <input v-model="editor.enabled" type="checkbox" /> 保存后立即启用
      </label>

      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
    </AppModal>

    <AppModal
      :open="Boolean(removeTarget)"
      title="确认删除频道 banner"
      confirm-text="确认删除"
      :busy="removing"
      @cancel="closeRemove"
      @confirm="confirmRemove"
    >
      <p class="modal-lead">
        确定删除这张 banner？删除后频道页立即少一屏，该频道没有 banner 时回退为默认渐变占位。
      </p>
    </AppModal>
  </section>
</template>

<style scoped>
.channel-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.channel-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 320px;
}

.channel-picker select {
  min-height: 36px;
}

.channel-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.channel-thumb {
  display: block;
  width: 188px;
  height: 42px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #fff;
}

.row--off {
  opacity: 0.55;
}

.actions-col .btn + .btn {
  margin-left: 6px;
}
</style>
