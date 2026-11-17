<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'
import ChannelBannersPanel from '@/views/ChannelBannersPanel.vue'

const state = reactive({
  section: 'campaign',
  items: [],
  total: 0,
  maxCards: 10,
  loading: true,
  error: '',
  notice: '',
})

// 前两个分区共用一张表与接口（HomeCampaignCard）；「频道页 banner」是独立
// 模型与接口（ChannelBanner，按 channel_code 分组），渲染独立子面板。
const SECTIONS = [
  { key: 'campaign', label: '首页活动卡片', itemWord: '标题' },
  { key: 'discovery', label: '品类发现（Category discovery）', itemWord: '名称' },
]
const CHANNEL_TAB = { key: 'channel', label: '频道页 banner' }
const TABS = [...SECTIONS, CHANNEL_TAB]
const sectionMeta = computed(() => SECTIONS.find((s) => s.key === state.section) || SECTIONS[0])

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({
  title: '',
  title_zh: '',
  subtitle: '',
  subtitle_zh: '',
  image: '',
  href: '',
  enabled: true,
})

const removeTarget = ref(null)
const removing = ref(false)
const movingId = ref('')

async function load() {
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest(`/campaign-cards?section=${state.section}`)
    state.items = payload.items || []
    state.total = payload.total || 0
    state.maxCards = payload.max_cards || 10
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectSection(key) {
  state.section = key
  state.notice = ''
  // 频道页 banner 是独立子面板，自己 onMounted 加载，不共用卡片接口。
  if (key !== CHANNEL_TAB.key) load()
}

function openCreate() {
  editorId.value = ''
  editor.title = ''
  editor.title_zh = ''
  editor.subtitle = ''
  editor.subtitle_zh = ''
  editor.image = ''
  editor.href = ''
  editor.enabled = true
  editorError.value = ''
  editorOpen.value = true
}

function openEdit(row) {
  editorId.value = row.id
  editor.title = row.title
  editor.title_zh = row.title_zh || ''
  editor.subtitle = row.subtitle || ''
  editor.subtitle_zh = row.subtitle_zh || ''
  editor.image = row.image_url || ''
  editor.href = row.href || ''
  editor.enabled = Boolean(row.enabled)
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
    section: state.section,
    title: editor.title,
    title_zh: editor.title_zh,
    subtitle: editor.subtitle,
    subtitle_zh: editor.subtitle_zh,
    image_url: editor.image,
    href: editor.href,
    enabled: editor.enabled,
  }
  try {
    if (editorId.value) {
      await adminWrite(`/campaign-cards/${editorId.value}`, body, 'PATCH')
      state.notice = '卡片已更新，购物端首页即时生效。'
    } else {
      await adminWrite('/campaign-cards', body)
      state.notice = '卡片已新增。'
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
    await adminWrite(`/campaign-cards/${removeTarget.value.id}`, null, 'DELETE')
    state.notice = `已移除「${removeTarget.value.title}」。`
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
    await adminWrite(`/campaign-cards/${row.id}/actions`, {
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
    await adminWrite(`/campaign-cards/${row.id}/actions`, { action: 'toggle' })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>活动卡片</h1>
        <p>
          首页搜索框下方的活动卡片/品类发现，以及频道页顶部的 banner
          轮播。改动保存后，购物端下次打开对应页面即生效。
        </p>
      </div>
      <div v-if="state.section !== CHANNEL_TAB.key" class="page-intro__actions">
        <span class="tag">{{ state.total }} / {{ state.maxCards }}</span>
        <button
          type="button"
          class="btn btn--primary"
          :disabled="state.total >= state.maxCards"
          @click="openCreate"
        >
          新增卡片
        </button>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.section === tab.key }"
        @click="selectSection(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <ChannelBannersPanel v-if="state.section === CHANNEL_TAB.key" />

    <p v-if="state.section !== CHANNEL_TAB.key && state.error" class="notice notice--error">
      {{ state.error }}
    </p>
    <p v-if="state.section !== CHANNEL_TAB.key && state.notice" class="notice notice--ok">
      {{ state.notice }}
    </p>
    <p
      v-if="state.section !== CHANNEL_TAB.key && state.total >= state.maxCards"
      class="notice notice--info"
    >
      已达 {{ state.maxCards }} 张上限。要新增请先移除或停用一张。
    </p>

    <div v-if="state.section !== CHANNEL_TAB.key" class="card">
      <div class="card__body">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <table v-else-if="state.items.length" class="data-table">
          <thead>
            <tr>
              <th style="width: 130px">图片</th>
              <th>{{ sectionMeta.itemWord }} / 副标题</th>
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
                <img v-if="row.image_url" :src="row.image_url" alt="" class="campaign-thumb" />
                <span v-else class="campaign-thumb campaign-thumb--empty">无图</span>
              </td>
              <td>
                <div class="cell-strong">{{ row.title }}</div>
                <div v-if="state.section === 'campaign'" class="cell-sub">
                  {{ row.subtitle || '—' }}
                </div>
                <div v-if="row.title_zh" class="cell-sub">
                  中：{{ row.title_zh }} {{ row.subtitle_zh }}
                </div>
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
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">
          还没有卡片。没有启用中的卡片时，购物端首页会回退显示 CMS 快照里的默认内容。
        </p>
      </div>
    </div>

    <AppModal
      :open="editorOpen"
      :title="editorId ? '编辑卡片' : '新增卡片'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="closeEditor"
      @confirm="saveCard"
    >
      <div class="form-grid">
        <label class="field">
          <span class="field__label">{{ sectionMeta.itemWord }}（英文，必填）</span>
          <input v-model="editor.title" type="text" maxlength="60" />
        </label>
        <label class="field">
          <span class="field__label">{{ sectionMeta.itemWord }}（中文，选填）</span>
          <input v-model="editor.title_zh" type="text" maxlength="60" />
        </label>
        <template v-if="state.section === 'campaign'">
          <label class="field">
            <span class="field__label">副标题（英文，选填）</span>
            <input v-model="editor.subtitle" type="text" maxlength="120" />
          </label>
          <label class="field">
            <span class="field__label">副标题（中文，选填）</span>
            <input v-model="editor.subtitle_zh" type="text" maxlength="120" />
          </label>
        </template>
      </div>

      <ImageUploader
        v-model="editor.image"
        purpose="banner"
        :max-size-mb="2"
        label="卡片图"
        hint="竖向构图效果最佳；不上传则购物端显示色块占位。"
      />

      <label class="field" style="margin-top: 12px">
        <span class="field__label">跳转链接（选填）</span>
        <input v-model="editor.href" type="text" placeholder="/c/electronics 或 https://…" />
        <span class="field__hint">留空则卡片不可点击。</span>
      </label>

      <label class="checkline" style="margin-top: 12px">
        <input v-model="editor.enabled" type="checkbox" /> 保存后立即启用
      </label>

      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
    </AppModal>

    <AppModal
      :open="Boolean(removeTarget)"
      title="确认移除卡片"
      confirm-text="确认移除"
      :busy="removing"
      @cancel="closeRemove"
      @confirm="confirmRemove"
    >
      <p class="modal-lead">
        确定移除「<b>{{ removeTarget?.title }}</b
        >」？移除后购物端首页立即少一张卡片，此操作不可撤销。
      </p>
    </AppModal>
  </section>
</template>

<style scoped>
.campaign-thumb {
  display: block;
  width: 104px;
  height: 64px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #fff;
}

.campaign-thumb--empty {
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 11px;
  background: #f2f4f7;
}

.row--off {
  opacity: 0.55;
}

.actions-col .btn + .btn {
  margin-left: 6px;
}
</style>
