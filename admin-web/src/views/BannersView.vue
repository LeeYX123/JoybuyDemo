<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  enabled: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
  notice: '',
})

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({ title: '', description: '', image: '', href: '', sort: 0, enabled: true })

const removeTarget = ref(null)
const removing = ref(false)

const previewIndex = ref(0)
const enabledItems = computed(() => state.items.filter((item) => item.enabled))

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.enabled) params.set('enabled', state.enabled)
    const payload = await apiRequest(`/banners?${params}`)
    state.items = payload.items
    state.meta = payload
    if (previewIndex.value >= enabledItems.value.length) previewIndex.value = 0
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function openEditor(row = null) {
  editorId.value = row?.id || ''
  editor.title = row?.title || ''
  editor.description = row?.description || ''
  editor.image = row?.image || ''
  editor.href = row?.href || ''
  editor.sort = row?.sort ?? 0
  editor.enabled = row ? row.enabled : true
  editorError.value = ''
  editorOpen.value = true
}

async function save() {
  editorBusy.value = true
  editorError.value = ''
  const payload = {
    title: editor.title,
    description: editor.description,
    image: editor.image,
    href: editor.href,
    sort: Number(editor.sort),
    enabled: editor.enabled,
  }
  try {
    if (editorId.value) {
      await adminWrite(`/banners/${editorId.value}`, payload, 'PATCH')
    } else {
      await adminWrite('/banners', payload)
    }
    editorOpen.value = false
    state.notice = '轮播图已保存。'
    await load()
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

async function toggle(row) {
  try {
    await adminWrite(`/banners/${row.id}/actions`, {
      action: row.enabled ? 'disable' : 'enable',
    })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

async function confirmRemove() {
  if (!removeTarget.value) return
  removing.value = true
  try {
    await adminWrite(`/banners/${removeTarget.value.id}`, null, 'DELETE')
    removeTarget.value = null
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    removing.value = false
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商城首页轮播图</h1>
        <p>只配置商城顶部轮播，不替代活动中心图片；停用的记录不参与轮播。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="openEditor()">新增轮播图</button>
      </div>
    </div>

    <p v-if="state.notice" class="notice notice--ok" style="margin-bottom: 14px">
      {{ state.notice }}
    </p>
    <p v-if="state.error" class="notice notice--error" style="margin-bottom: 14px">
      {{ state.error }}
    </p>

    <div class="panel">
      <div class="toolbar">
        <select v-model="state.enabled" @change="load(true)">
          <option value="">全部状态</option>
          <option value="1">启用中</option>
          <option value="0">已停用</option>
        </select>
        <button type="button" class="btn" @click="load(true)">刷新</button>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>预览</th>
              <th>标题 / 小字</th>
              <th>跳转链接</th>
              <th>排序</th>
              <th>状态</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td><img v-if="row.image" :src="row.image" alt="" class="thumb" /></td>
              <td>
                <b>{{ row.title }}</b>
                <span v-if="row.description" class="cell-sub">{{ row.description }}</span>
              </td>
              <td class="mono">{{ row.href || '—' }}</td>
              <td class="num">{{ row.sort }}</td>
              <td>
                <span class="tag" :class="row.enabled ? 'tag--ok' : 'tag--gray'">
                  {{ row.enabled ? '启用中' : '已停用' }}
                </span>
              </td>
              <td>{{ formatTime(row.updated_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                  <button type="button" class="btn btn--sm" @click="toggle(row)">
                    {{ row.enabled ? '停用' : '启用' }}
                  </button>
                  <button type="button" class="btn btn--sm btn--danger" @click="removeTarget = row">
                    删除
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">还没有轮播图，先新增一张。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="enabledItems.length" class="panel">
      <div class="panel__head">
        <h2>启用中轮播预览</h2>
        <div class="panel__actions">
          <button
            type="button"
            class="btn btn--sm"
            @click="previewIndex = (previewIndex - 1 + enabledItems.length) % enabledItems.length"
          >
            上一张
          </button>
          <span class="cell-sub">{{ previewIndex + 1 }} / {{ enabledItems.length }}</span>
          <button
            type="button"
            class="btn btn--sm"
            @click="previewIndex = (previewIndex + 1) % enabledItems.length"
          >
            下一张
          </button>
        </div>
      </div>
      <div class="panel__body">
        <div class="banner-preview">
          <img :src="enabledItems[previewIndex].image" alt="" />
          <div class="banner-preview__text">
            <strong>{{ enabledItems[previewIndex].title }}</strong>
            <span>{{ enabledItems[previewIndex].description }}</span>
          </div>
        </div>
      </div>
    </div>

    <AppModal
      v-if="editorOpen"
      :title="editorId ? '编辑轮播图' : '新增轮播图'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="editorOpen = false"
      @confirm="save"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
      <div class="form-grid">
        <div class="field">
          <label for="banner-title">标题（最多 40 字）</label>
          <input id="banner-title" v-model="editor.title" type="text" maxlength="40" />
        </div>
        <div class="field">
          <label for="banner-sort">排序（数字越小越靠前）</label>
          <input id="banner-sort" v-model="editor.sort" type="number" min="0" step="1" />
        </div>
      </div>
      <div class="field" style="margin-top: 12px">
        <label for="banner-desc">小字描述（最多 100 字，选填）</label>
        <input id="banner-desc" v-model="editor.description" type="text" maxlength="100" />
      </div>
      <ImageUploader
        v-model="editor.image"
        purpose="banner"
        :max-size-mb="2"
        label="轮播图图片"
        hint="建议 16:9 横图，上传后存到服务器本地。"
      />
      <div class="field" style="margin-top: 12px">
        <label for="banner-href">跳转链接（选填）</label>
        <input id="banner-href" v-model="editor.href" type="text" />
      </div>
      <label class="checkline" style="margin-top: 12px">
        <input v-model="editor.enabled" type="checkbox" /> 保存后立即启用
      </label>
      <div v-if="editor.image" class="banner-preview" style="margin-top: 14px">
        <img :src="editor.image" alt="" />
        <div class="banner-preview__text">
          <strong>{{ editor.title || '标题' }}</strong>
          <span>{{ editor.description }}</span>
        </div>
      </div>
    </AppModal>

    <AppModal
      v-if="removeTarget"
      title="确认删除轮播图"
      confirm-text="删除"
      :busy="removing"
      @cancel="removeTarget = null"
      @confirm="confirmRemove"
    >
      <p>将删除「{{ removeTarget.title }}」，删除后不可恢复。若只是暂时下线，建议改用「停用」。</p>
    </AppModal>
  </section>
</template>

<style scoped>
.banner-preview {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #f4f7fb;
}

.banner-preview img {
  display: block;
  width: 100%;
  max-height: 260px;
  object-fit: cover;
}

.banner-preview__text {
  position: absolute;
  left: 20px;
  bottom: 18px;
  display: grid;
  gap: 4px;
  color: #ffffff;
  text-shadow: 0 1px 6px rgb(0 0 0 / 45%);
}

.banner-preview__text strong {
  font-size: 18px;
}

.banner-preview__text span {
  font-size: 12px;
}
</style>
