<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useFetch, useHead, useRequestHeaders, useRouter, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'
import { useUiToast } from '../../composables/useUiToast'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'
import AccountTabs from '../../components/account/AccountTabs.vue'

// Saved addresses rebuilt from joybuy.co.uk/profile/my-address: title + tabs
// (Delivery / Pickup), "+ Add new address" in the top-right, and one card per
// address with the default badge and edit/delete actions. The real site uses
// an address autocomplete; this repo's backend stores structured UK fields,
// so the modal asks for recipient, phone, address lines, city/county/postcode
// and a default switch. Address mutations require the CSRF token from the
// buyer session endpoint, same as the checkout/cart flows.
const { t } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const { show } = useUiToast()
const config = useRuntimeConfig()
// ADR 0001: on the m. host the same payload renders the mobile address book
// (docs/20 §5.4); the desktop AccountShell below is untouched.
const { isMobileHost } = useMobileView()
const router = useRouter()

const addressesUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/addresses` : '/api/v1/addresses',
)

const { data, status, refresh } = await useFetch(addressesUrl, {
  key: 'account-addresses',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const addresses = computed(() => (Array.isArray(data.value?.addresses) ? data.value.addresses : []))

const tab = ref('delivery')
// 用户决定（2026-11-25）：账户地址页去掉「自提」tab，只保留配送地址；
// 真站虽有 配送/自提 两个 tab，但本项目无自提点业务，不虚设。
const tabs = computed(() => [{ key: 'delivery', label: t('addresses.tabDelivery') }])

const showForm = ref(false)
const editingId = ref('')
const saving = ref(false)
const formError = ref('')
const deleteTarget = ref(null)
const deleting = ref(false)

const EMPTY_FORM = {
  full_name: '',
  phone: '',
  line1: '',
  line2: '',
  city: '',
  county: '',
  postcode: '',
  is_default: false,
}

const form = reactive({ ...EMPTY_FORM })

const formTitle = computed(() =>
  editingId.value ? t('addresses.editTitle') : t('addresses.addTitle'),
)

// The toolbar button no longer switches with a tab: only delivery addresses
// are manageable here (pickup tab removed, user decision 2026-11-25).
const addButtonLabel = computed(() => t('addresses.addNew'))

function resetForm() {
  Object.assign(form, EMPTY_FORM)
  formError.value = ''
}

function openCreate() {
  editingId.value = ''
  resetForm()
  form.is_default = addresses.value.length === 0
  showForm.value = true
}

function openEdit(address) {
  editingId.value = address.public_id
  formError.value = ''
  Object.assign(form, {
    full_name: address.full_name || '',
    phone: address.phone || '',
    line1: address.line1 || '',
    line2: address.line2 || '',
    city: address.city || '',
    county: address.county || '',
    postcode: address.postcode || '',
    is_default: Boolean(address.is_default),
  })
  showForm.value = true
}

function closeForm() {
  if (saving.value) return
  showForm.value = false
}

// Storefront validation mirrors the backend's required fields and UK postcode
// rule so the user sees a field-level message before the round-trip.
const POSTCODE_PATTERN = /^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$/
const PHONE_PATTERN = /^[+0-9()\s-]{7,20}$/

function validate() {
  if (!form.full_name.trim()) return t('addresses.errorFullName')
  if (!PHONE_PATTERN.test(form.phone.trim())) return t('addresses.errorPhone')
  if (!form.line1.trim()) return t('addresses.errorLine1')
  if (!form.city.trim()) return t('addresses.errorCity')
  if (!POSTCODE_PATTERN.test(form.postcode.trim())) return t('addresses.errorPostcode')
  return ''
}

async function csrfToken() {
  const session = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
  return session?.csrf_token || ''
}

function serverErrorKey(response) {
  const code = response?.error?.code
  if (code === 'ADDRESS_INCOMPLETE') return 'addresses.errorFullName'
  if (code === 'ADDRESS_UNSUPPORTED') return 'addresses.errorPostcode'
  if (code === 'ADDRESS_NOT_FOUND') return 'addresses.errorNotFound'
  return 'addresses.errorSave'
}

async function save() {
  formError.value = ''
  const validation = validate()
  if (validation) {
    formError.value = validation
    return
  }
  saving.value = true
  try {
    const token = await csrfToken()
    const response = await $fetch('/api/v1/addresses', {
      method: editingId.value ? 'PATCH' : 'POST',
      body: {
        ...(editingId.value ? { public_id: editingId.value } : {}),
        full_name: form.full_name.trim(),
        phone: form.phone.trim(),
        line1: form.line1.trim(),
        line2: form.line2.trim(),
        city: form.city.trim(),
        county: form.county.trim(),
        postcode: form.postcode.trim().toUpperCase(),
        is_default: form.is_default,
      },
      headers: { 'X-CSRFToken': token },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      formError.value = t(serverErrorKey(response))
      return
    }
    showForm.value = false
    await refresh()
    show(editingId.value ? t('addresses.updated') : t('addresses.saved'), { type: 'success' })
  } catch {
    formError.value = t('addresses.errorSave')
  } finally {
    saving.value = false
  }
}

async function setDefault(address) {
  if (address.is_default) return
  try {
    const token = await csrfToken()
    const response = await $fetch('/api/v1/addresses', {
      method: 'PATCH',
      body: { public_id: address.public_id, is_default: true },
      headers: { 'X-CSRFToken': token },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      show(t(serverErrorKey(response)), { type: 'error' })
      return
    }
    await refresh()
    show(t('addresses.defaultUpdated'), { type: 'success' })
  } catch {
    show(t('addresses.errorSave'), { type: 'error' })
  }
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const token = await csrfToken()
    const response = await $fetch(
      `/api/v1/addresses?public_id=${encodeURIComponent(deleteTarget.value.public_id)}`,
      {
        method: 'DELETE',
        headers: { 'X-CSRFToken': token },
        credentials: 'include',
        ignoreResponseError: true,
      },
    )
    if (response?.error) {
      show(t(serverErrorKey(response)), { type: 'error' })
      return
    }
    deleteTarget.value = null
    await refresh()
    show(t('addresses.deleted'), { type: 'success' })
  } catch {
    show(t('addresses.errorSave'), { type: 'error' })
  } finally {
    deleting.value = false
  }
}

function addressLines(address) {
  return [address.line1, address.line2, address.city, address.county, address.postcode]
    .filter(Boolean)
    .join(', ')
}

// Joybuy cards carry a "复制" link next to the address; keep it, with a toast
// instead of silently writing to the clipboard.
async function copyAddress(address) {
  try {
    await navigator.clipboard.writeText(addressLines(address))
    show(t('addresses.copied'), { type: 'success' })
  } catch {
    show(t('addresses.copyFailed'), { type: 'error' })
  }
}

function handleKeydown(event) {
  if (event.key !== 'Escape') return
  if (deleteTarget.value) {
    deleteTarget.value = null
    return
  }
  if (showForm.value) closeForm()
}

// --- Mobile address book (docs/20 §5.4) -------------------------------------
// The mobile component is presentational: cards carry the same resolved
// fields, the form forwards its edits as `field` events into the same
// reactive form, and every mutation reuses the desktop handlers above.
const mobileAddresses = computed(() =>
  addresses.value.map((address) => ({
    // Keep the raw payload spread in so edit/setDefault receive the same
    // object shape as the desktop handlers (full_name/line1/...).
    ...address,
    publicId: address.public_id,
    fullName: address.full_name || '',
    phone: address.phone || '',
    lines: addressLines(address),
    isDefault: Boolean(address.is_default),
    isServiceable: address.is_serviceable !== false,
  })),
)

const mobileDeleteTarget = computed(() =>
  deleteTarget.value
    ? {
        ...deleteTarget.value,
        fullName: deleteTarget.value.full_name || '',
      }
    : null,
)

function setMobileField(name, value) {
  form[name] = value
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})

useHead(() => ({ title: t('addresses.title') }))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.4 mobile address book;
       the desktop AccountShell below is untouched. -->
  <MobileAddresses
    v-if="isMobileHost"
    :signed-in="isAuthenticated"
    :loading="status === 'pending'"
    :tab="tab"
    :tabs="tabs"
    :addresses="mobileAddresses"
    :show-form="showForm"
    :form-title="formTitle"
    :form="form"
    :form-error="formError"
    :saving="saving"
    :add-button-label="addButtonLabel"
    :delete-target="mobileDeleteTarget"
    :deleting="deleting"
    @tab="tab = $event"
    @add="openCreate"
    @edit="openEdit"
    @copy="copyAddress"
    @set-default="setDefault"
    @request-delete="deleteTarget = $event"
    @confirm-delete="confirmDelete"
    @cancel-delete="deleteTarget = null"
    @close-form="closeForm"
    @save="save"
    @field="setMobileField"
    @back="router.back()"
  />
  <AccountShell v-else :title="t('addresses.title')">
    <template #tabs>
      <div class="addresses-toolbar">
        <AccountTabs v-model="tab" :tabs="tabs" />
        <button v-if="isAuthenticated" class="address-add" type="button" @click="openCreate">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path
              d="M8.75 3.203a.75.75 0 1 0-1.5 0v4.05H3.2a.75.75 0 0 0 0 1.5h4.05v4.05a.75.75 0 0 0 1.5 0v-4.05h4.05a.75.75 0 0 0 0-1.5H8.75z"
              fill="currentColor"
            />
          </svg>
          {{ addButtonLabel }}
        </button>
      </div>
    </template>

    <div v-if="!isAuthenticated" class="addresses-signed-out">
      <AccountEmpty
        :message="t('addresses.signInRequired')"
        :note="t('addresses.signInNote')"
        compact
      />
      <div class="addresses-signed-out__actions">
        <NuxtLink to="/auth/login"
          ><BaseButton variant="primary">{{ t('header.signIn') }}</BaseButton></NuxtLink
        >
      </div>
    </div>

    <template v-else>
      <div v-if="status === 'pending'" class="addresses-list" aria-hidden="true">
        <div class="address-card address-card--skeleton">
          <BaseSkeleton variant="text" />
          <BaseSkeleton variant="text" />
          <BaseSkeleton variant="text" />
        </div>
      </div>

      <AccountEmpty v-else-if="addresses.length === 0" :message="t('addresses.empty')" />

      <ul
        v-else
        class="addresses-list"
        :class="{ 'addresses-list--single': addresses.length === 1 }"
      >
        <li v-for="address in addresses" :key="address.public_id">
          <article class="address-card" :class="{ 'address-card--default': address.is_default }">
            <div class="address-card__top">
              <div class="address-card__identity">
                <h2 class="address-card__name">{{ address.full_name }}</h2>
                <span class="address-card__phone">{{ address.phone }}</span>
              </div>
              <div class="address-card__address-row">
                <p class="address-card__lines">{{ addressLines(address) }}</p>
                <button class="address-card__copy" type="button" @click="copyAddress(address)">
                  {{ t('addresses.copy') }}
                </button>
              </div>
              <p v-if="!address.is_serviceable" class="address-card__warning">
                {{ t('addresses.notServiceable') }}
              </p>
            </div>
            <footer class="address-card__foot">
              <label class="address-card__default">
                <input
                  class="address-card__radio"
                  type="radio"
                  name="default-address"
                  :checked="address.is_default"
                  @change="setDefault(address)"
                />
                <span>
                  {{
                    address.is_default ? t('addresses.defaultAddress') : t('addresses.setDefault')
                  }}
                </span>
              </label>
              <div class="address-card__actions">
                <button
                  class="address-card__action"
                  type="button"
                  :aria-label="t('addresses.edit')"
                  @click="openEdit(address)"
                >
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                    <path
                      d="M3.4 11.7 11.1 4a1.4 1.4 0 0 1 2 0l.9.9a1.4 1.4 0 0 1 0 2l-7.7 7.7-3.1.9 1.1-2.8Z"
                      fill="none"
                      stroke="currentColor"
                      stroke-linejoin="round"
                      stroke-width="1.4"
                    />
                  </svg>
                </button>
                <button
                  class="address-card__action"
                  type="button"
                  :aria-label="t('addresses.delete')"
                  @click="deleteTarget = address"
                >
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                    <path
                      d="M2.8 4.2h10.4M6 4.2V2.9h4v1.3m-5.4 0 .5 8.2h5.8l.5-8.2M6.7 6.3v4.4M9.3 6.3v4.4"
                      fill="none"
                      stroke="currentColor"
                      stroke-linecap="round"
                      stroke-width="1.4"
                    />
                  </svg>
                </button>
              </div>
            </footer>
          </article>
        </li>
      </ul>
    </template>

    <!-- Add / edit address modal (joybuy uses a centred modal too). -->
    <div v-if="showForm" class="address-modal" @click.self="closeForm">
      <div
        class="address-modal__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="address-form-title"
      >
        <header class="address-modal__head">
          <h2 id="address-form-title">{{ formTitle }}</h2>
          <button
            class="address-modal__close"
            type="button"
            :aria-label="t('addresses.close')"
            @click="closeForm"
          >
            ×
          </button>
        </header>

        <form class="address-form" novalidate @submit.prevent="save">
          <p v-if="formError" class="address-form__error" role="alert">{{ formError }}</p>

          <label class="address-form__field">
            <span>{{ t('addresses.fullName') }} *</span>
            <input v-model="form.full_name" type="text" autocomplete="name" required />
          </label>

          <label class="address-form__field">
            <span>{{ t('addresses.phone') }} *</span>
            <input v-model="form.phone" type="tel" autocomplete="tel" required />
          </label>

          <label class="address-form__field">
            <span>{{ t('addresses.line1') }} *</span>
            <input v-model="form.line1" type="text" autocomplete="address-line1" required />
          </label>

          <label class="address-form__field">
            <span>{{ t('addresses.line2') }}</span>
            <input v-model="form.line2" type="text" autocomplete="address-line2" />
          </label>

          <div class="address-form__row">
            <label class="address-form__field">
              <span>{{ t('addresses.city') }} *</span>
              <input v-model="form.city" type="text" autocomplete="address-level2" required />
            </label>
            <label class="address-form__field">
              <span>{{ t('addresses.county') }}</span>
              <input v-model="form.county" type="text" autocomplete="address-level1" />
            </label>
          </div>

          <label class="address-form__field">
            <span>{{ t('addresses.postcode') }} *</span>
            <input v-model="form.postcode" type="text" autocomplete="postal-code" required />
          </label>

          <label class="address-form__switch">
            <input v-model="form.is_default" type="checkbox" />
            <span>{{ t('addresses.setDefaultCheckbox') }}</span>
          </label>

          <footer class="address-form__actions">
            <button class="address-form__cancel" type="button" @click="closeForm">
              {{ t('addresses.cancel') }}
            </button>
            <button class="address-form__save" type="submit" :disabled="saving">
              {{ saving ? t('addresses.saving') : t('addresses.save') }}
            </button>
          </footer>
        </form>
      </div>
    </div>

    <!-- Delete confirmation: no native confirm(), so it is fully bilingual. -->
    <div v-if="deleteTarget" class="address-modal" @click.self="deleteTarget = null">
      <div
        class="address-modal__panel address-modal__panel--narrow"
        role="dialog"
        aria-modal="true"
        aria-labelledby="address-delete-title"
      >
        <header class="address-modal__head">
          <h2 id="address-delete-title">{{ t('addresses.deleteTitle') }}</h2>
          <button
            class="address-modal__close"
            type="button"
            :aria-label="t('addresses.close')"
            @click="deleteTarget = null"
          >
            ×
          </button>
        </header>
        <p class="address-delete__text">
          {{ t('addresses.deleteConfirm').replace('{name}', deleteTarget.full_name) }}
        </p>
        <footer class="address-form__actions">
          <button class="address-form__cancel" type="button" @click="deleteTarget = null">
            {{ t('addresses.cancel') }}
          </button>
          <button
            class="address-form__save address-form__save--danger"
            type="button"
            :disabled="deleting"
            @click="confirmDelete"
          >
            {{ deleting ? t('addresses.deleting') : t('addresses.delete') }}
          </button>
        </footer>
      </div>
    </div>
  </AccountShell>
</template>

<style scoped>
.addresses-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

/* joybuy.co.uk 实测：卡片两列（仅 1 条时通栏），列/行间距 8px，
   卡片 1px 边框、4px 圆角、12px 内边距，默认地址红色边框 #CC0C1C。 */
.addresses-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: var(--space-4) 0 0;
  padding: 0;
  list-style: none;
}

.addresses-list--single {
  grid-template-columns: minmax(0, 1fr);
}

.address-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  border: 1px solid #e0e1e5;
  border-radius: 4px;
  background: transparent;
}

.address-card--default {
  border-color: #cc0c1c;
}

.address-card--skeleton {
  gap: var(--space-3);
}

.address-card__top {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.address-card__identity {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.address-card__name {
  max-width: 150px;
  margin: 0;
  overflow: hidden;
  color: #000;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.address-card__phone {
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-regular);
  line-height: 18px;
  white-space: nowrap;
}

.address-card__address-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}

.address-card__lines {
  display: -webkit-box;
  flex: 1;
  margin: 8px 0 0;
  overflow: hidden;
  color: #505259;
  font-size: 14px;
  font-weight: var(--font-weight-regular);
  line-height: 18px;
  word-break: break-all;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.address-card__copy {
  margin: 8px 0 0 5px;
  padding: 0;
  border: 0;
  background: none;
  color: #1869f5;
  font-size: 14px;
  line-height: 18px;
  white-space: nowrap;
  cursor: pointer;
}

.address-card__copy:hover {
  text-decoration: underline;
}

.address-card__warning {
  margin: 8px 0 0;
  color: #995c00;
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  line-height: 20px;
}

.address-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: auto;
  padding-top: 8px;
}

.address-card__default {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 18px;
  cursor: pointer;
}

.address-card__radio {
  width: 18px;
  height: 18px;
  margin: 0 0 0 -2px;
  accent-color: #1a1a1a;
  cursor: pointer;
}

.address-card__radio:disabled {
  cursor: default;
}

.address-card__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.address-card__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
}

.address-card__action:hover {
  background: var(--colour-hover);
}

.address-add {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 5px 8px;
  border: 1px solid #cc0c1c;
  border-radius: 4px;
  background: transparent;
  color: #cc0c1c;
  font-size: 12px;
  font-weight: var(--font-weight-regular);
  line-height: 16px;
  cursor: pointer;
}

.address-add:hover {
  background: var(--colour-accent-soft);
}

.addresses-signed-out {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.addresses-signed-out__actions {
  padding-bottom: var(--space-8);
}

.addresses-signed-out__actions :deep(a) {
  text-decoration: none;
}

.address-modal {
  position: fixed;
  inset: 0;
  z-index: var(--z-skip-link);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  background: rgb(23 32 42 / 50%);
}

.address-modal__panel {
  width: min(34rem, 100%);
  max-height: calc(100vh - 2rem);
  overflow: auto;
  border-radius: 8px;
  background: var(--colour-surface);
  box-shadow: var(--shadow-overlay);
}

.address-modal__panel--narrow {
  width: min(28rem, 100%);
}

.address-modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--colour-border);
}

.address-modal__head h2 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

.address-modal__close {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text-secondary);
  font-size: 1.25rem;
  cursor: pointer;
}

.address-modal__close:hover {
  background: var(--colour-surface-muted);
}

.address-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-5);
}

.address-form__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.address-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--colour-text-secondary);
}

.address-form__field input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border-strong);
  border-radius: 2px;
  background: var(--colour-surface);
  color: var(--colour-text);
  font-size: var(--font-size-md);
}

.address-form__field input:focus {
  border-color: var(--colour-focus-ring);
  outline: 2px solid var(--colour-info-soft);
}

.address-form__switch {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 40px;
  color: var(--colour-text);
  font-size: var(--font-size-md);
}

.address-form__switch input {
  width: 18px;
  height: 18px;
  accent-color: var(--colour-accent);
}

.address-form__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: 2px;
  background: var(--colour-error-soft);
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.address-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding-top: var(--space-2);
}

.address-form__cancel,
.address-form__save {
  min-height: 44px;
  padding: 0 var(--space-5);
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
}

.address-form__cancel {
  border: 1px solid var(--colour-border-strong);
  background: var(--colour-surface);
  color: var(--colour-text);
}

.address-form__save {
  border: 1px solid var(--colour-text);
  background: var(--colour-text);
  color: var(--colour-white);
}

.address-form__save--danger {
  border-color: var(--colour-error);
  background: var(--colour-error);
}

.address-form__save:disabled {
  cursor: progress;
  opacity: 0.6;
}

.address-delete__text {
  margin: 0;
  padding: var(--space-5) var(--space-5) 0;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
}

.address-delete__text + .address-form__actions {
  padding: 0 var(--space-5) var(--space-5);
}

/* 768px 视口下右侧面板只有约 400px，两列会把姓名/地址截断成几个字，
   因此低于 960px 时改为单列（真实站只有 PC 布局，这里是响应式修正）。 */
@media (max-width: 60rem) {
  .addresses-list {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 47.999rem) {
  .addresses-list {
    grid-template-columns: minmax(0, 1fr);
  }

  .address-form__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
