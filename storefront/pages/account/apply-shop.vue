<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { navigateTo, useFetch, useHead, useRequestHeaders, useRuntimeConfig } from '#imports'
import { useLocale } from '../../composables/useLocale'
import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useMerchantEntry } from '../../composables/useMerchantEntry'
import { useMobileView } from '../../composables/useMobileView'
import { noAutofill } from '../../utils/noAutofill'

import ShopApplicationDetails from '../../components/account/ShopApplicationDetails.vue'

// 购物端「申请店铺」：无申请 → 表单；PENDING → 审核中；APPROVED → 成功卡
// （PENDING_DEPOSIT 提示缴保证金）；REJECTED → 驳回原因 + 重新申请。
// 2026-11-17 表单 7 项：店铺logo、用户名字、店铺名、手机号码、邀请码（选填）、
// 个人证件（类型三选一 + 照片）、个人居住地址。图片走买家侧上传接口
// （/account/merchant-application/media，purpose=shop_application，2MB）。
// 2026-11-26 视觉按用户设计稿重做：桌面 申请开店-电脑版.html /
// 待审核-电脑版.html；m. host 走 MobileApplyShop（申请开店-手机版.html /
// 待审核-手机版.html）。业务逻辑与接口契约不变。
const { t } = useLocale()

const { isAuthenticated, refresh: refreshSession } = useBuyerAuth()
const { switching: merchantSwitching, openMerchantConsole } = useMerchantEntry()
// ADR 0001: m. host 渲染手机版（组件只做展示，状态仍在本页）。
const { isMobileHost } = useMobileView()

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
const merchant = computed(() => data.value?.merchant || null)
const merchantPendingDeposit = computed(
  () => merchant.value?.onboarding_status === 'PENDING_DEPOSIT',
)

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

const documentTypeLabel = computed(() => docTypeLabel(application.value?.id_document_type))

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

function startLogoUpload(file) {
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
}

function startDocUpload(file) {
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
}

function onLogoChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  startLogoUpload(file)
}

function onDocChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  startDocUpload(file)
}

// 手机版组件把编辑动作作为事件回传，这里统一落到同一份状态。
const MOBILE_FIELD_SETTERS = {
  userName,
  shopName,
  phone,
  referrerCode,
  idDocumentType,
  residentialAddress,
}

function onMobileField(name, value) {
  const target = MOBILE_FIELD_SETTERS[name]
  if (target) target.value = value
}

const mobileForm = computed(() => ({
  logoPreview: logoPreview.value,
  userName: userName.value,
  shopName: shopName.value,
  phone: phone.value,
  referrerCode: referrerCode.value,
  idDocumentType: idDocumentType.value,
  docPreview: docPreview.value,
  residentialAddress: residentialAddress.value,
}))

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

const statusLabel = computed(() => {
  if (status.value === 'PENDING') return t('shopApply.statusPending')
  if (status.value === 'APPROVED') return t('shopApply.statusApproved')
  if (status.value === 'REJECTED') return t('shopApply.statusRejected')
  return ''
})

useHead({ title: t('shopApply.title') })
</script>

<template>
  <!-- ADR 0001: m. host 渲染手机版设计稿（480px 单列）；桌面保持独立模板。 -->
  <MobileApplyShop
    v-if="isMobileHost"
    :signed-in="isAuthenticated"
    :show-form="showForm"
    :status="status || ''"
    :application="application"
    :form="mobileForm"
    :submitting="submitting"
    :form-error="formError"
    :field-errors="fieldErrors"
    :logo-uploading="logoUploading"
    :logo-upload-error="logoUploadError"
    :doc-uploading="docUploading"
    :doc-upload-error="docUploadError"
    :id-document-types="idDocumentTypes"
    :document-type-label="documentTypeLabel"
    :status-label="statusLabel"
    :merchant-switching="merchantSwitching"
    :merchant-pending-deposit="merchantPendingDeposit"
    @field="onMobileField"
    @logo-file="startLogoUpload"
    @doc-file="startDocUpload"
    @submit="submitApplication"
    @reapply="startReApply"
    @open-merchant="openMerchantConsole"
  />

  <section v-else class="shop-apply" aria-labelledby="shop-apply-title">
    <div class="shop-apply__card">
      <div class="shop-apply__inner">
        <h1 id="shop-apply-title" class="shop-apply__title">{{ t('shopApply.title') }}</h1>

        <p v-if="!isAuthenticated" class="shop-apply__signedout">
          {{ t('account.signInPrompt') }}
        </p>

        <template v-else>
          <p v-if="showForm" class="shop-apply__subtitle">{{ t('shopApply.subtitle') }}</p>

          <form
            v-if="showForm"
            class="shop-apply__panel shop-apply__form"
            novalidate
            @submit.prevent="submitApplication"
          >
            <p v-if="status === 'REJECTED' && editing" class="shop-apply__alert" role="alert">
              {{ t('shopApply.rejectedTitle') }}：{{ application?.reject_reason || '—' }}
            </p>

            <!-- 1. 店铺logo -->
            <div class="shop-apply__field">
              <span id="shop-apply-logo-label" class="shop-apply__label">
                {{ t('shopApply.shopLogo') }}<b aria-hidden="true">*</b>
              </span>
              <label class="shop-apply__upload" for="shop-apply-logo">
                <img
                  v-if="logoPreview"
                  class="shop-apply__upload-preview"
                  :src="logoPreview"
                  :alt="t('shopApply.shopLogo')"
                />
                <span aria-hidden="true">↑</span>
                {{ logoUploading ? t('shopApply.uploading') : t('shopApply.chooseImage') }}
                <input
                  id="shop-apply-logo"
                  class="shop-apply__file"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  :disabled="logoUploading"
                  aria-required="true"
                  aria-describedby="shop-apply-logo-hint"
                  :aria-label="t('shopApply.uploadLogo')"
                  @change="onLogoChange"
                />
              </label>
              <small id="shop-apply-logo-hint" class="shop-apply__hint">
                {{ t('shopApply.uploadHint') }}
              </small>
              <p v-if="logoUploadError || fieldErrors.logo" class="shop-apply__error" role="alert">
                {{ logoUploadError || fieldErrors.logo }}
              </p>
            </div>

            <!-- 2. 用户名字 -->
            <div class="shop-apply__field">
              <label class="shop-apply__label" for="shop-apply-user-name">
                {{ t('shopApply.userName') }}<b aria-hidden="true">*</b>
              </label>
              <input
                id="shop-apply-user-name"
                v-model="userName"
                class="shop-apply__input"
                type="text"
                v-bind="noAutofill"
                maxlength="60"
                required
                aria-required="true"
              />
              <p v-if="fieldErrors.userName" class="shop-apply__error" role="alert">
                {{ fieldErrors.userName }}
              </p>
            </div>

            <!-- 3. 店铺名称 -->
            <div class="shop-apply__field">
              <label class="shop-apply__label" for="shop-apply-name">
                {{ t('shopApply.shopName') }}<b aria-hidden="true">*</b>
              </label>
              <input
                id="shop-apply-name"
                v-model="shopName"
                class="shop-apply__input"
                type="text"
                v-bind="noAutofill"
                maxlength="60"
                required
                aria-required="true"
              />
              <p v-if="fieldErrors.shopName" class="shop-apply__error" role="alert">
                {{ fieldErrors.shopName }}
              </p>
            </div>

            <!-- 4. 手机号码 -->
            <div class="shop-apply__field">
              <label class="shop-apply__label" for="shop-apply-phone">
                {{ t('shopApply.phone') }}<b aria-hidden="true">*</b>
              </label>
              <input
                id="shop-apply-phone"
                v-model="phone"
                class="shop-apply__input"
                type="tel"
                v-bind="noAutofill"
                maxlength="32"
                required
                aria-required="true"
              />
              <p v-if="fieldErrors.phone" class="shop-apply__error" role="alert">
                {{ fieldErrors.phone }}
              </p>
            </div>

            <!-- 5. 邀请码（选填） -->
            <div class="shop-apply__field shop-apply__field--invitation">
              <label class="shop-apply__label" for="shop-apply-referrer">
                {{ t('shopApply.referrerCode') }}
              </label>
              <input
                id="shop-apply-referrer"
                v-model="referrerCode"
                class="shop-apply__input shop-apply__input--narrow"
                type="text"
                v-bind="noAutofill"
                maxlength="32"
                aria-describedby="shop-apply-referrer-hint"
              />
              <small id="shop-apply-referrer-hint" class="shop-apply__hint">
                {{ t('shopApply.referrerCodeHint') }}
              </small>
            </div>

            <!-- 6. 个人证件（类型三选一 + 证件照片） -->
            <div
              class="shop-apply__identity"
              role="group"
              :aria-label="t('shopApply.idDocumentsGroup')"
            >
              <fieldset class="shop-apply__field shop-apply__fieldset">
                <legend class="shop-apply__label">
                  {{ t('shopApply.idDocument') }}<b aria-hidden="true">*</b>
                </legend>
                <div
                  class="shop-apply__choices"
                  role="radiogroup"
                  :aria-label="t('shopApply.idDocumentType')"
                >
                  <label
                    v-for="item in idDocumentTypes"
                    :key="item.value"
                    class="shop-apply__choice"
                    :class="{ 'is-selected': idDocumentType === item.value }"
                  >
                    <input
                      v-model="idDocumentType"
                      class="shop-apply__radio"
                      type="radio"
                      name="shop-apply-id-document-type"
                      :value="item.value"
                    />
                    <span class="shop-apply__choice-mark" aria-hidden="true"></span>
                    <span>{{ item.label }}</span>
                  </label>
                </div>
                <p v-if="fieldErrors.doc" class="shop-apply__error" role="alert">
                  {{ fieldErrors.doc }}
                </p>
              </fieldset>

              <div class="shop-apply__field">
                <span id="shop-apply-doc-label" class="shop-apply__label">
                  {{ t('shopApply.idDocumentImage') }}<b aria-hidden="true">*</b>
                </span>
                <label class="shop-apply__upload shop-apply__upload--wide" for="shop-apply-doc">
                  <img
                    v-if="docPreview"
                    class="shop-apply__upload-preview"
                    :src="docPreview"
                    :alt="t('shopApply.idDocumentImage')"
                  />
                  <span aria-hidden="true">↑</span>
                  {{ docUploading ? t('shopApply.uploading') : t('shopApply.chooseImage') }}
                  <input
                    id="shop-apply-doc"
                    class="shop-apply__file"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    :disabled="docUploading"
                    aria-required="true"
                    aria-describedby="shop-apply-doc-hint"
                    :aria-labelledby="'shop-apply-doc-label'"
                    :aria-label="t('shopApply.uploadDocImage')"
                    @change="onDocChange"
                  />
                </label>
                <small id="shop-apply-doc-hint" class="shop-apply__hint">
                  {{ t('shopApply.uploadHint') }}
                </small>
                <p v-if="docUploadError || fieldErrors.doc" class="shop-apply__error" role="alert">
                  {{ docUploadError || fieldErrors.doc }}
                </p>
              </div>
            </div>

            <!-- 7. 个人居住地址 -->
            <div class="shop-apply__field shop-apply__field--address">
              <label class="shop-apply__label" for="shop-apply-address">
                {{ t('shopApply.residentialAddress') }}<b aria-hidden="true">*</b>
              </label>
              <textarea
                id="shop-apply-address"
                v-model="residentialAddress"
                class="shop-apply__input shop-apply__address"
                v-bind="noAutofill"
                rows="2"
                maxlength="255"
                required
                aria-required="true"
              ></textarea>
              <p v-if="fieldErrors.residentialAddress" class="shop-apply__error" role="alert">
                {{ fieldErrors.residentialAddress }}
              </p>
            </div>

            <p v-if="formError" class="shop-apply__error shop-apply__error--form" role="alert">
              {{ formError }}
            </p>

            <div class="shop-apply__actions">
              <button class="shop-apply__submit" type="submit" :disabled="submitting">
                {{ submitting ? t('shopApply.submitting') : t('shopApply.submit') }}
              </button>
            </div>
          </form>

          <template v-else-if="status === 'PENDING'">
            <div class="shop-apply__status shop-apply__status--pending" role="status">
              <span class="shop-apply__icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  width="20"
                  height="20"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5.5l3.5 2" stroke-linecap="round" />
                </svg>
              </span>
              <div>
                <strong>{{ t('shopApply.statusPending') }}</strong>
                <p>{{ t('shopApply.underReviewNote') }}</p>
              </div>
            </div>

            <ShopApplicationDetails
              :application="application"
              :document-type-label="documentTypeLabel"
            />
          </template>

          <template v-else-if="status === 'APPROVED'">
            <div class="shop-apply__status shop-apply__status--approved" role="status">
              <span class="shop-apply__icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  width="20"
                  height="20"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M8 12.5l2.8 2.8L16.5 9" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </span>
              <div>
                <strong>{{ t('shopApply.approvedTitle') }}</strong>
                <p>{{ t('shopApply.approvedNote') }}</p>
                <p v-if="merchantPendingDeposit">{{ t('shopApply.pendingDepositNote') }}</p>
              </div>
            </div>

            <ShopApplicationDetails
              :application="application"
              :document-type-label="documentTypeLabel"
              :status-label="statusLabel"
              show-status
              show-reviewed-at
            />

            <div class="shop-apply__actions shop-apply__actions--standalone">
              <button
                class="shop-apply__submit"
                type="button"
                :disabled="merchantSwitching"
                @click="openMerchantConsole"
              >
                {{
                  merchantSwitching ? t('merchantEntry.opening') : t('shopApply.goMerchantCenter')
                }}
              </button>
            </div>
          </template>

          <template v-else-if="status === 'REJECTED'">
            <div class="shop-apply__status shop-apply__status--rejected" role="alert">
              <span class="shop-apply__icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  width="20"
                  height="20"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7.5v5.5M12 16.5v.5" stroke-linecap="round" />
                </svg>
              </span>
              <div>
                <strong>{{ t('shopApply.rejectedTitle') }}</strong>
                <p>{{ t('shopApply.rejectReason') }}：{{ application?.reject_reason || '—' }}</p>
                <p>{{ t('shopApply.rejectedNote') }}</p>
              </div>
            </div>

            <ShopApplicationDetails
              :application="application"
              :document-type-label="documentTypeLabel"
              :status-label="statusLabel"
              show-status
              show-reviewed-at
            />

            <div class="shop-apply__actions shop-apply__actions--standalone">
              <button class="shop-apply__submit" type="button" @click="startReApply">
                {{ t('shopApply.reApply') }}
              </button>
            </div>
          </template>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 设计稿数值：申请开店页面/申请开店-电脑版.html、待审核-电脑版.html
   —— 卡片 1068（1100 − 2×16）居中、14px 圆角、24/32 内边距、内容 840；
   面板白底 15px 圆角、两列 22px 列距；label 13/650、输入 38 高、
   提交按钮 #c5103b 10px 圆角 148 宽；待审核横幅 #fff3df/#753d00。 */
.shop-apply {
  max-width: 1100px;
  margin-block: 24px;
  margin-inline: auto;
  padding: 16px;
  background: #edf0f4;
  color: #191e2b;
  font:
    14px/1.5 'Microsoft YaHei',
    'PingFang SC',
    sans-serif;
}

.shop-apply__card {
  padding: 24px 32px;
  border: 1px solid #dce0e7;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 10px 30px #161b2620;
}

.shop-apply__inner {
  max-width: 840px;
  margin: 0 auto;
}

.shop-apply__title {
  margin: 0 0 5px;
  color: #191e2b;
  font-size: 28px;
  font-weight: 720;
  line-height: 1.2;
}

.shop-apply__subtitle,
.shop-apply__signedout {
  margin: 0;
  color: #5a6373;
  font-size: 13px;
}

.shop-apply__panel {
  margin-top: 15px;
  padding: 22px;
  border: 1px solid #dce0e7;
  border-radius: 15px;
  background: #ffffff;
}

.shop-apply__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 22px;
}

.shop-apply__field {
  display: block;
  min-width: 0;
}

.shop-apply__fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}

.shop-apply__label {
  display: block;
  margin: 0 0 4px;
  padding: 0;
  color: #191e2b;
  font-size: 13px;
  font-weight: 650;
}

.shop-apply__label b {
  color: #bd113b;
}

.shop-apply__input {
  width: 100%;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  background: #ffffff;
  color: #191e2b;
  font: inherit;
  font-size: 13px;
}

.shop-apply__input::placeholder {
  color: #5a6373;
}

.shop-apply__input--narrow {
  max-width: 240px;
}

.shop-apply__address {
  min-height: 58px;
  resize: vertical;
}

/* 邀请码 / 证件 / 地址 / 按钮整行 */
.shop-apply__field--invitation,
.shop-apply__identity,
.shop-apply__field--address,
.shop-apply__actions {
  grid-column: 1 / -1;
}

.shop-apply__upload {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  max-width: 360px;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px dashed #dce0e7;
  border-radius: 8px;
  background: #fff5f7;
  color: #bd113b;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

.shop-apply__upload--wide {
  max-width: none;
}

.shop-apply__upload:focus-within {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.shop-apply__upload-preview {
  width: 28px;
  height: 28px;
  border: 1px solid #dce0e7;
  border-radius: 6px;
  object-fit: cover;
}

/* 视觉隐藏但仍可聚焦：键盘可跳到「选择图片」并回车打开文件框。 */
.shop-apply__file {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.shop-apply__hint {
  display: block;
  margin-top: 3px;
  color: #5a6373;
  font-size: 11px;
}

.shop-apply__error {
  margin: 3px 0 0;
  color: #b42318;
  font-size: 12px;
}

.shop-apply__error--form {
  grid-column: 1 / -1;
  font-size: 13px;
}

.shop-apply__alert {
  grid-column: 1 / -1;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  background: #fff5f7;
  color: #bd113b;
  font-size: 13px;
}

.shop-apply__identity {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 22px;
  padding-block: 16px;
  border-block: 1px solid #dce0e7;
}

.shop-apply__choices {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.shop-apply__choice {
  position: relative;
  display: inline-flex;
  flex: 0 1 auto;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  color: #5a6373;
  font-size: 13px;
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
}

.shop-apply__choice.is-selected {
  border-color: #bd113b;
  background: #fff5f7;
  color: #bd113b;
}

.shop-apply__choice:focus-within {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.shop-apply__radio {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.shop-apply__choice-mark::before {
  content: '○';
  margin-right: 4px;
}

.shop-apply__choice.is-selected .shop-apply__choice-mark::before {
  content: '◉';
}

.shop-apply__actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
  border-top: 1px solid #dce0e7;
}

.shop-apply__actions--standalone {
  margin-top: 15px;
  padding-top: 0;
  border-top: 0;
}

.shop-apply__submit {
  min-width: 148px;
  padding: 9px 16px;
  border: 0;
  border-radius: 10px;
  background: #c5103b;
  color: #ffffff;
  font: inherit;
  font-size: 14px;
  font-weight: 650;
  text-align: center;
  cursor: pointer;
}

.shop-apply__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.shop-apply__submit:focus-visible {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.shop-apply__status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 15px;
  padding: 16px 20px;
  border-radius: 14px;
  background: #fff3df;
  color: #753d00;
}

.shop-apply__status strong {
  font-size: 18px;
  font-weight: 700;
}

.shop-apply__status p {
  margin: 2px 0 0;
  color: inherit;
  font-size: 13px;
}

.shop-apply__status--approved {
  background: #e7f6ec;
  color: #0e7a3d;
}

.shop-apply__status--rejected {
  background: #fdecea;
  color: #b42318;
}

.shop-apply__icon {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  padding: 8px;
  border-radius: 11px;
  background: #f8dfb1;
  color: inherit;
}

.shop-apply__status--approved .shop-apply__icon {
  background: #cbeed8;
}

.shop-apply__status--rejected .shop-apply__icon {
  background: #f8d3ce;
}

/* 设计稿 @media(max-width:590px)：桌面卡片在窄屏（未跳 m. 时）折成单列。 */
@media (max-width: 590px) {
  .shop-apply {
    margin-block: 8px;
    padding: 8px;
  }

  .shop-apply__card {
    padding: 16px;
  }

  .shop-apply__form {
    grid-template-columns: minmax(0, 1fr);
    padding: 14px;
  }

  .shop-apply__identity {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
