<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { navigateTo, useFetch, useHead, useRequestHeaders, useRuntimeConfig } from '#imports'
import { useLocale } from '../../composables/useLocale'
import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useMerchantEntry } from '../../composables/useMerchantEntry'

const { t } = useLocale()

// 购物端「申请店铺」：无申请 → 表单；PENDING → 审核中；APPROVED → 成功卡
// （PENDING_DEPOSIT 提示缴保证金）；REJECTED → 驳回原因 + 重新申请。
// 2026-11-17 表单 7 项：店铺logo、用户名字、店铺名、手机号码、邀请码（选填）、
// 个人证件（类型三选一 + 照片）、个人居住地址。图片走买家侧上传接口
// （/account/merchant-application/media，purpose=shop_application，2MB）。
const { isAuthenticated, refresh: refreshSession } = useBuyerAuth()
const { switching: merchantSwitching, openMerchantConsole } = useMerchantEntry()

const config = useRuntimeConfig()

const url = computed(() =>
  import.meta.server
    ? `${config.apiBaseInternal}/account/merchant-application`
    : '/api/v1/account/merchant-application',
)

const { data, refresh } = await useFetch(url, {
  key: 'merchant-application',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const application = computed(() => data.value?.application || null)
const status = computed(() => application.value?.status || null)
const merchant = computed(() => application.value?.merchant || null)

// 表单态 = 从未申请，或被驳回后点了「重新申请」（editing）。
const editing = ref(false)
const showForm = computed(
  () => status.value === null || (status.value === 'REJECTED' && editing.value),
)

// ---- 表单 7 项（按用户要求的顺序）----
const logoUrl = ref('')
const logoPreview = ref('')
const userName = ref('')
const shopName = ref('')
const phone = ref('')
const referrerCode = ref('')
const idDocumentType = ref('ID_CARD')
const docUrl = ref('')
const docPreview = ref('')
const residentialAddress = ref('')

const submitting = ref(false)
const formError = ref('')
const fieldErrors = ref({})
const logoUploading = ref(false)
const logoUploadError = ref('')
const docUploading = ref(false)
const docUploadError = ref('')

// 与后端 store_upload / PHONE_PATTERN 同口径（客户端预检，服务端为准）。
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024
const PHONE_PATTERN = /^\+?\d{6,20}$/

const idDocumentTypes = computed(() => [
  { value: 'ID_CARD', label: t('shopApply.idTypeIdCard') },
  { value: 'PASSPORT', label: t('shopApply.idTypePassport') },
  { value: 'DRIVER_LICENSE', label: t('shopApply.idTypeDriverLicense') },
])

function docTypeLabel(value) {
  const found = idDocumentTypes.value.find((item) => item.value === value)
  return found ? found.label : value || '—'
}

function revokePreview(preview) {
  if (preview && preview.startsWith('blob:')) URL.revokeObjectURL(preview)
}

// 上传单张申请图（logo / 证件照共用）：类型与大小预检 → 买家会话 + CSRF。
async function uploadApplicationImage(file, { uploading, uploadError, onUploaded }) {
  uploadError.value = ''
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    uploadError.value = t('shopApply.errImageType')
    return false
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    uploadError.value = t('shopApply.errImageSize')
    return false
  }
  uploading.value = true
  try {
    // 与 useBuyerAuth 同款：先取 csrf_token 再带 X-CSRFToken 提交。
    const fresh = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
    const body = new FormData()
    body.append('file', file)
    body.append('purpose', 'shop_application')
    const response = await $fetch('/api/v1/account/merchant-application/media', {
      method: 'POST',
      body,
      headers: { 'X-CSRFToken': fresh?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      uploadError.value = response.error?.message || t('shopApply.uploadFailed')
      return false
    }
    onUploaded(response?.media?.url || '')
    return true
  } catch {
    uploadError.value = t('shopApply.uploadFailed')
    return false
  } finally {
    uploading.value = false
  }
}

function onLogoChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const preview = URL.createObjectURL(file)
  uploadApplicationImage(file, {
    uploading: logoUploading,
    uploadError: logoUploadError,
    onUploaded: (url) => {
      revokePreview(logoPreview.value)
      logoUrl.value = url
      logoPreview.value = preview
      fieldErrors.value = { ...fieldErrors.value, logo: '' }
    },
  }).then((ok) => {
    if (!ok) revokePreview(preview)
  })
  event.target.value = ''
}

function onDocChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const preview = URL.createObjectURL(file)
  uploadApplicationImage(file, {
    uploading: docUploading,
    uploadError: docUploadError,
    onUploaded: (url) => {
      revokePreview(docPreview.value)
      docUrl.value = url
      docPreview.value = preview
      fieldErrors.value = { ...fieldErrors.value, doc: '' }
    },
  }).then((ok) => {
    if (!ok) revokePreview(preview)
  })
  event.target.value = ''
}

function validateForm() {
  const errors = {}
  if (!logoUrl.value) errors.logo = t('shopApply.errLogoRequired')
  if (!userName.value.trim()) errors.userName = t('shopApply.errRequired')
  if (!shopName.value.trim()) errors.shopName = t('shopApply.errRequired')
  const rawPhone = phone.value.replace(/[\s\-()]/g, '')
  if (!rawPhone) errors.phone = t('shopApply.errRequired')
  else if (!PHONE_PATTERN.test(rawPhone)) errors.phone = t('shopApply.errPhoneInvalid')
  if (!docUrl.value) errors.doc = t('shopApply.errDocRequired')
  if (!residentialAddress.value.trim()) errors.residentialAddress = t('shopApply.errRequired')
  return errors
}

// 用户补填后清掉对应字段的行内错误，避免「已填仍报错」的陈旧提示。
function clearFieldError(key) {
  if (fieldErrors.value[key]) fieldErrors.value = { ...fieldErrors.value, [key]: '' }
}

watch(userName, () => clearFieldError('userName'))
watch(shopName, () => clearFieldError('shopName'))
watch(phone, () => clearFieldError('phone'))
watch(residentialAddress, () => clearFieldError('residentialAddress'))
watch(idDocumentType, () => clearFieldError('doc'))

// 服务端业务错误码 → 双语文案键（未映射的回退原始 message / 通用失败）。
const SERVER_ERROR_KEYS = {
  USER_NAME_REQUIRED: 'shopApply.errRequired',
  SHOP_NAME_REQUIRED: 'shopApply.errRequired',
  PHONE_REQUIRED: 'shopApply.errRequired',
  RESIDENTIAL_ADDRESS_REQUIRED: 'shopApply.errRequired',
  USER_NAME_TOO_LONG: 'shopApply.errTooLong',
  SHOP_NAME_TOO_LONG: 'shopApply.errTooLong',
  RESIDENTIAL_ADDRESS_TOO_LONG: 'shopApply.errTooLong',
  REFERRER_CODE_TOO_LONG: 'shopApply.errTooLong',
  PHONE_INVALID: 'shopApply.errPhoneInvalid',
  ID_DOCUMENT_TYPE_INVALID: 'shopApply.errDocTypeInvalid',
  LOGO_IMAGE_INVALID: 'shopApply.errLogoInvalid',
  LOGO_IMAGE_NOT_FOUND: 'shopApply.errLogoInvalid',
  ID_DOCUMENT_IMAGE_INVALID: 'shopApply.errDocInvalid',
  ID_DOCUMENT_IMAGE_NOT_FOUND: 'shopApply.errDocInvalid',
}

async function submitApplication() {
  fieldErrors.value = validateForm()
  if (Object.keys(fieldErrors.value).length > 0) return
  submitting.value = true
  formError.value = ''
  try {
    // 与 useBuyerAuth 同款：先取 csrf_token 再带 X-CSRFToken 提交。
    const fresh = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
    const response = await $fetch('/api/v1/account/merchant-application', {
      method: 'POST',
      body: {
        user_name: userName.value.trim(),
        shop_name: shopName.value.trim(),
        phone: phone.value.trim(),
        referrer_code: referrerCode.value.trim(),
        id_document_type: idDocumentType.value,
        residential_address: residentialAddress.value.trim(),
        logo_image_url: logoUrl.value,
        id_document_image_url: docUrl.value,
      },
      headers: { 'X-CSRFToken': fresh?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      const key = SERVER_ERROR_KEYS[response.error?.code]
      formError.value = key ? t(key) : response.error?.message || t('shopApply.submitFailed')
      return
    }
    editing.value = false
    await refresh()
  } catch {
    formError.value = t('shopApply.submitFailed')
  } finally {
    submitting.value = false
  }
}

function startReApply() {
  // 被驳回重新申请：表单回填上一轮旧值（含两张图）。
  userName.value = application.value?.user_name || ''
  shopName.value = application.value?.shop_name || ''
  phone.value = application.value?.phone || ''
  referrerCode.value = application.value?.referrer_code || ''
  idDocumentType.value = application.value?.id_document_type || 'ID_CARD'
  residentialAddress.value = application.value?.residential_address || ''
  logoUrl.value = application.value?.logo_image_url || ''
  logoPreview.value = logoUrl.value
  docUrl.value = application.value?.id_document_image_url || ''
  docPreview.value = docUrl.value
  formError.value = ''
  fieldErrors.value = {}
  logoUploadError.value = ''
  docUploadError.value = ''
  editing.value = true
}

// 未登录守卫：会话就绪后仍未见登录态则跳登录页（客户端执行）。
onMounted(async () => {
  await refreshSession()
  if (!isAuthenticated.value) navigateTo('/auth/login')
})
watch(isAuthenticated, (authed) => {
  if (!authed) navigateTo('/auth/login')
})

function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

const statusLabel = computed(() => {
  if (status.value === 'PENDING') return t('shopApply.statusPending')
  if (status.value === 'APPROVED') return t('shopApply.statusApproved')
  if (status.value === 'REJECTED') return t('shopApply.statusRejected')
  return ''
})

useHead({ title: t('shopApply.title') })
</script>

<template>
  <AppContainer narrow>
    <section class="shop-apply" aria-labelledby="shop-apply-title">
      <h1 id="shop-apply-title">{{ t('shopApply.title') }}</h1>

      <template v-if="isAuthenticated">
        <form
          v-if="showForm"
          class="shop-apply__panel shop-apply__form"
          novalidate
          @submit.prevent="submitApplication"
        >
          <p class="shop-apply__subtitle">{{ t('shopApply.subtitle') }}</p>

          <p v-if="status === 'REJECTED' && editing" class="shop-apply__rejected-note" role="alert">
            {{ t('shopApply.rejectedTitle') }}：
            {{ application?.reject_reason || '—' }}
          </p>

          <!-- 1. 店铺 logo -->
          <div class="shop-apply__field">
            <label for="shop-apply-logo">{{ t('shopApply.shopLogo') }}</label>
            <div class="shop-apply__upload">
              <img
                v-if="logoPreview"
                :src="logoPreview"
                :alt="t('shopApply.shopLogo')"
                class="shop-apply__upload-preview"
              />
              <input
                id="shop-apply-logo"
                class="shop-apply__file"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                :disabled="logoUploading"
                :aria-label="t('shopApply.uploadLogo')"
                @change="onLogoChange"
              />
            </div>
            <span class="shop-apply__hint">{{ t('shopApply.uploadHint') }}</span>
            <span v-if="logoUploading" class="shop-apply__hint">{{
              t('shopApply.uploading')
            }}</span>
            <span v-if="logoUploadError || fieldErrors.logo" class="shop-apply__error" role="alert">
              {{ logoUploadError || fieldErrors.logo }}
            </span>
          </div>

          <!-- 2. 用户名字 -->
          <div class="shop-apply__field">
            <label for="shop-apply-user-name">{{ t('shopApply.userName') }}</label>
            <input
              id="shop-apply-user-name"
              v-model="userName"
              type="text"
              maxlength="60"
              required
              :placeholder="t('shopApply.userNamePlaceholder')"
              :aria-label="t('shopApply.userName')"
            />
            <span v-if="fieldErrors.userName" class="shop-apply__error" role="alert">
              {{ fieldErrors.userName }}
            </span>
          </div>

          <!-- 3. 店铺名 -->
          <div class="shop-apply__field">
            <label for="shop-apply-name">{{ t('shopApply.shopName') }}</label>
            <input
              id="shop-apply-name"
              v-model="shopName"
              type="text"
              maxlength="60"
              required
              :placeholder="t('shopApply.shopNamePlaceholder')"
              :aria-label="t('shopApply.shopName')"
            />
            <span v-if="fieldErrors.shopName" class="shop-apply__error" role="alert">
              {{ fieldErrors.shopName }}
            </span>
          </div>

          <!-- 4. 手机号码 -->
          <div class="shop-apply__field">
            <label for="shop-apply-phone">{{ t('shopApply.phone') }}</label>
            <input
              id="shop-apply-phone"
              v-model="phone"
              type="tel"
              maxlength="32"
              required
              :placeholder="t('shopApply.phonePlaceholder')"
              :aria-label="t('shopApply.phone')"
            />
            <span v-if="fieldErrors.phone" class="shop-apply__error" role="alert">
              {{ fieldErrors.phone }}
            </span>
          </div>

          <!-- 5. 邀请码（选填） -->
          <div class="shop-apply__field">
            <label for="shop-apply-referrer">{{ t('shopApply.referrerCode') }}</label>
            <input
              id="shop-apply-referrer"
              v-model="referrerCode"
              type="text"
              maxlength="32"
              :placeholder="t('shopApply.referrerCodePlaceholder')"
              :aria-label="t('shopApply.referrerCode')"
            />
            <span class="shop-apply__hint">{{ t('shopApply.referrerCodeHint') }}</span>
          </div>

          <!-- 6. 个人证件：类型三选一 + 证件照片 -->
          <div class="shop-apply__field">
            <span class="shop-apply__field-label">{{ t('shopApply.idDocument') }}</span>
            <div
              class="shop-apply__radios"
              role="radiogroup"
              :aria-label="t('shopApply.idDocumentType')"
            >
              <label v-for="item in idDocumentTypes" :key="item.value" class="shop-apply__radio">
                <input
                  v-model="idDocumentType"
                  type="radio"
                  name="shop-apply-id-document-type"
                  :value="item.value"
                />
                {{ item.label }}
              </label>
            </div>

            <label for="shop-apply-doc" class="shop-apply__sublabel">
              {{ t('shopApply.idDocumentImage') }}
            </label>
            <div class="shop-apply__upload">
              <img
                v-if="docPreview"
                :src="docPreview"
                :alt="t('shopApply.idDocumentImage')"
                class="shop-apply__upload-preview shop-apply__upload-preview--doc"
              />
              <input
                id="shop-apply-doc"
                class="shop-apply__file"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                :disabled="docUploading"
                :aria-label="t('shopApply.uploadDocImage')"
                @change="onDocChange"
              />
            </div>
            <span class="shop-apply__hint">{{ t('shopApply.uploadHint') }}</span>
            <span v-if="docUploading" class="shop-apply__hint">{{ t('shopApply.uploading') }}</span>
            <span v-if="docUploadError || fieldErrors.doc" class="shop-apply__error" role="alert">
              {{ docUploadError || fieldErrors.doc }}
            </span>
          </div>

          <!-- 7. 个人居住地址 -->
          <div class="shop-apply__field">
            <label for="shop-apply-address">{{ t('shopApply.residentialAddress') }}</label>
            <textarea
              id="shop-apply-address"
              v-model="residentialAddress"
              class="shop-apply__textarea"
              rows="3"
              maxlength="255"
              required
              :placeholder="t('shopApply.residentialAddressPlaceholder')"
              :aria-label="t('shopApply.residentialAddress')"
            ></textarea>
            <span v-if="fieldErrors.residentialAddress" class="shop-apply__error" role="alert">
              {{ fieldErrors.residentialAddress }}
            </span>
          </div>

          <p v-if="formError" class="shop-apply__error" role="alert">{{ formError }}</p>

          <BaseButton variant="primary" size="lg" type="submit" :disabled="submitting">
            {{ submitting ? t('shopApply.submitting') : t('shopApply.submit') }}
          </BaseButton>
        </form>

        <div v-else-if="status === 'PENDING'" class="shop-apply__panel">
          <p class="shop-apply__badge shop-apply__badge--pending" role="status">
            {{ statusLabel }}
          </p>
          <p class="shop-apply__note">{{ t('shopApply.underReviewNote') }}</p>

          <dl class="shop-apply__details">
            <div>
              <dt>{{ t('shopApply.shopLogo') }}</dt>
              <dd>
                <img
                  v-if="application?.logo_image_url"
                  :src="application.logo_image_url"
                  :alt="t('shopApply.shopLogo')"
                  class="shop-apply__thumb"
                />
                <template v-else>—</template>
              </dd>
            </div>
            <div>
              <dt>{{ t('shopApply.userName') }}</dt>
              <dd>{{ application?.user_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.shopName') }}</dt>
              <dd>{{ application?.shop_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.phone') }}</dt>
              <dd>{{ application?.phone || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.idDocument') }}</dt>
              <dd>
                {{ docTypeLabel(application?.id_document_type) }}
                <img
                  v-if="application?.id_document_image_url"
                  :src="application.id_document_image_url"
                  :alt="t('shopApply.idDocumentImage')"
                  class="shop-apply__thumb shop-apply__thumb--doc"
                />
              </dd>
            </div>
            <div>
              <dt>{{ t('shopApply.residentialAddress') }}</dt>
              <dd>{{ application?.residential_address || '—' }}</dd>
            </div>
            <div v-if="application?.referrer_code">
              <dt>{{ t('shopApply.referrerCode') }}</dt>
              <dd>{{ application.referrer_code }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.submittedAt') }}</dt>
              <dd>{{ formatTime(application?.submitted_at) }}</dd>
            </div>
          </dl>
        </div>

        <div v-else-if="status === 'APPROVED'" class="shop-apply__panel">
          <p class="shop-apply__badge shop-apply__badge--approved" role="status">
            {{ t('shopApply.approvedTitle') }}
          </p>
          <p class="shop-apply__note">{{ t('shopApply.approvedNote') }}</p>
          <p
            v-if="merchant?.onboarding_status === 'PENDING_DEPOSIT'"
            class="shop-apply__deposit-note"
            role="status"
          >
            {{ t('shopApply.pendingDepositNote') }}
          </p>

          <dl class="shop-apply__details">
            <div>
              <dt>{{ t('shopApply.shopLogo') }}</dt>
              <dd>
                <img
                  v-if="application?.logo_image_url"
                  :src="application.logo_image_url"
                  :alt="t('shopApply.shopLogo')"
                  class="shop-apply__thumb"
                />
                <template v-else>—</template>
              </dd>
            </div>
            <div>
              <dt>{{ t('shopApply.userName') }}</dt>
              <dd>{{ application?.user_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.shopName') }}</dt>
              <dd>{{ application?.shop_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.phone') }}</dt>
              <dd>{{ application?.phone || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.idDocument') }}</dt>
              <dd>
                {{ docTypeLabel(application?.id_document_type) }}
                <img
                  v-if="application?.id_document_image_url"
                  :src="application.id_document_image_url"
                  :alt="t('shopApply.idDocumentImage')"
                  class="shop-apply__thumb shop-apply__thumb--doc"
                />
              </dd>
            </div>
            <div>
              <dt>{{ t('shopApply.residentialAddress') }}</dt>
              <dd>{{ application?.residential_address || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.statusLabel') }}</dt>
              <dd>{{ statusLabel }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.reviewedAt') }}</dt>
              <dd>{{ formatTime(application?.reviewed_at) }}</dd>
            </div>
          </dl>

          <BaseButton
            variant="primary"
            size="lg"
            :disabled="merchantSwitching"
            @click="openMerchantConsole"
          >
            {{ merchantSwitching ? t('merchantEntry.opening') : t('shopApply.goMerchantCenter') }}
          </BaseButton>
        </div>

        <div v-else-if="status === 'REJECTED'" class="shop-apply__panel">
          <p class="shop-apply__badge shop-apply__badge--rejected" role="alert">
            {{ t('shopApply.rejectedTitle') }}
          </p>
          <p class="shop-apply__reject-reason">
            <strong>{{ t('shopApply.rejectReason') }}：</strong>
            {{ application?.reject_reason || '—' }}
          </p>
          <p class="shop-apply__note">{{ t('shopApply.rejectedNote') }}</p>

          <dl class="shop-apply__details">
            <div>
              <dt>{{ t('shopApply.shopLogo') }}</dt>
              <dd>
                <img
                  v-if="application?.logo_image_url"
                  :src="application.logo_image_url"
                  :alt="t('shopApply.shopLogo')"
                  class="shop-apply__thumb"
                />
                <template v-else>—</template>
              </dd>
            </div>
            <div>
              <dt>{{ t('shopApply.userName') }}</dt>
              <dd>{{ application?.user_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.shopName') }}</dt>
              <dd>{{ application?.shop_name || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.phone') }}</dt>
              <dd>{{ application?.phone || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.idDocument') }}</dt>
              <dd>{{ docTypeLabel(application?.id_document_type) }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.residentialAddress') }}</dt>
              <dd>{{ application?.residential_address || '—' }}</dd>
            </div>
            <div v-if="application?.referrer_code">
              <dt>{{ t('shopApply.referrerCode') }}</dt>
              <dd>{{ application.referrer_code }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.submittedAt') }}</dt>
              <dd>{{ formatTime(application?.submitted_at) }}</dd>
            </div>
            <div>
              <dt>{{ t('shopApply.reviewedAt') }}</dt>
              <dd>{{ formatTime(application?.reviewed_at) }}</dd>
            </div>
          </dl>

          <BaseButton variant="primary" size="lg" @click="startReApply">
            {{ t('shopApply.reApply') }}
          </BaseButton>
        </div>
      </template>

      <p v-else class="shop-apply__signedout">{{ t('account.signInPrompt') }}</p>
    </section>
  </AppContainer>
</template>

<style scoped>
.shop-apply {
  max-width: 34rem;
  margin-inline: auto;
  margin-block: var(--space-10);
}

.shop-apply__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-5);
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.shop-apply__subtitle {
  color: var(--colour-text-secondary);
}

.shop-apply__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.shop-apply__field label,
.shop-apply__field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.shop-apply__sublabel {
  margin-top: var(--space-2);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.shop-apply__field input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.shop-apply__file {
  max-width: 100%;
  font-size: var(--font-size-sm);
}

.shop-apply__upload {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.shop-apply__upload-preview {
  width: 72px;
  height: 72px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  object-fit: cover;
}

.shop-apply__upload-preview--doc {
  width: 96px;
}

.shop-apply__radios {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.shop-apply__radio {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 44px;
  font-size: var(--font-size-sm);
}

.shop-apply__textarea {
  min-height: 88px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
  resize: vertical;
}

.shop-apply__hint {
  color: var(--colour-muted);
  font-size: var(--font-size-xs, 12px);
}

.shop-apply__error {
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.shop-apply__badge {
  align-self: flex-start;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-semibold);
}

.shop-apply__badge--pending {
  background: var(--colour-surface-muted);
  color: var(--colour-text);
}

.shop-apply__badge--approved {
  background: color-mix(in srgb, var(--colour-success) 12%, transparent);
  color: var(--colour-success);
}

.shop-apply__badge--rejected {
  background: color-mix(in srgb, var(--colour-error) 12%, transparent);
  color: var(--colour-error);
}

.shop-apply__note {
  color: var(--colour-text-secondary);
}

.shop-apply__reject-reason {
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.shop-apply__deposit-note {
  padding: var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface-muted);
  color: var(--colour-text);
  font-size: var(--font-size-sm);
}

.shop-apply__details {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
}

.shop-apply__details > div {
  display: flex;
  gap: var(--space-3);
}

.shop-apply__details dt {
  min-width: 8rem;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-sm);
}

.shop-apply__details dd {
  margin: 0;
  font-size: var(--font-size-sm);
}

.shop-apply__thumb {
  display: block;
  margin-top: var(--space-1);
  width: 64px;
  height: 64px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  object-fit: cover;
}

.shop-apply__thumb--doc {
  width: 88px;
}

.shop-apply__signedout {
  margin-top: var(--space-5);
  color: var(--colour-text-secondary);
}
</style>
