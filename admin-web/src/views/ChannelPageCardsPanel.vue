<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

// 频道页活动卡片（13.2）：/minihome/<channel_code> 品类卡下方的活动卡片，
// 与首页活动卡片/频道页 banner 不是一个模型/接口，这里是同一管理页里的独立子面板。
// 跳转链接按 13.8 规则存原值：http(s)://、//、www. 开头视为外链原样跳转，
// 否则视为站内路径（判定在购物端消费 helper）。

const LINK_RULE_HINT =
  '以 http(s):// 或 www. 开头按外链原样跳转，否则视为站内路径（如 /c/electronics）。'

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
  linkUrl: '',
  sortOrder: '',
  isActive: true,
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
    const payload = await apiRequest('/channel-page-cards/channels')
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
      `/channel-page-cards?channel_code=${encodeURIComponent(state.channelCode)}`,
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
  editor.linkUrl = ''
  editor.sortOrder = ''
  editor.isActive = true
  editorError.value = ''
  editorOpen.value = true
}

function openEdit(row) {
  editorId.value = row.id
  editor.image = row.image_url || ''
  editor.linkUrl = row.link_url || ''
  editor.sortOrder = String(row.sort_order ?? '')
  editor.isActive = Boolean(row.is_active)
  editorError.value = ''
  editorOpen.value = true
}

function closeEditor() {
  if (editorBusy.value) return
  editorOpen.value = false
}

async function saveCard() {
  editorBusy.value = true
  editorError.value = ''
  const body = {
    channel_code: state.channelCode,
    image_url: editor.image,
    link_url: editor.linkUrl,
    is_active: editor.isActive,
  }
  // 新增时留空 = 后端追加到该频道末尾；编辑时必须带上当前值。
  if (editorId.value || editor.sortOrder !== '') {
    body.sort_order = editor.sortOrder
  }
  try {
    if (editorId.value) {
      await adminWrite(`/channel-page-cards/${editorId.value}`, body, 'PATCH')
      state.notice = '活动卡片已更新，购物端频道页即时生效。'
    } else {
      await adminWrite('/channel-page-cards', body)
      state.notice = '活动卡片已新增。'
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
    await adminWrite(`/channel-page-cards/${removeTarget.value.id}`, null, 'DELETE')
    state.notice = '已删除该活动卡片。'
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
    await adminWrite(`/channel-page-cards/${row.id}/actions`, {
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
    await adminWrite(`/channel-page-cards/${row.id}/actions`, { action: 'toggle' })
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
              新增卡片
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
              :class="{ 'row--off': !row.is_active }"
            >
              <td>
                <img :src="row.image_url" alt="" class="card-thumb" />
              </td>
              <td class="mono">{{ row.link_url || '—' }}</td>
              <td>
                <button
                  type="button"
                  class="tag"
                  :class="row.is_active ? 'tag--ok' : 'tag--warn'"
                  @click="toggle(row)"
                >
                  {{ row.is_active ? '启用中' : '已停用' }}
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
        <p v-else class="empty-state">该频道还没有活动卡片，频道页对应位置不会显示卡片区。</p>
      </div>
    </div>

    <AppModal
      :open="editorOpen"
      :title="editorId ? '编辑活动卡片' : '新增活动卡片'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="closeEditor"
      @confirm="saveCard"
    >
      <p class="modal-lead">
        当前频道：<b>{{ channelLabel }}</b>
      </p>

      <ImageUploader
        v-model="editor.image"
        purpose="channel_page_card"
        :max-size-mb="2"
        label="卡片图"
        hint="建议与真站卡片比例一致的横图；仅支持本站上传（本地托管）。"
      />

      <div class="form-grid" style="margin-top: 12px">
        <label class="field">
          <span class="field__label">跳转链接（选填）</span>
          <input v-model="editor.linkUrl" type="text" placeholder="/c/electronics 或 https://…" />
          <span class="field__hint">{{ LINK_RULE_HINT }}留空则卡片不可点。</span>
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
        <input v-model="editor.isActive" type="checkbox" /> 保存后立即启用
      </label>

      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
    </AppModal>

    <AppModal
      :open="Boolean(removeTarget)"
      title="确认删除活动卡片"
      confirm-text="确认删除"
      :busy="removing"
      @cancel="closeRemove"
      @confirm="confirmRemove"
    >
      <p class="modal-lead">确定删除这张活动卡片？删除后该频道页立即少一张卡片，此操作不可撤销。</p>
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

.card-thumb {
  display: block;
  width: 150px;
  height: 60px;
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
