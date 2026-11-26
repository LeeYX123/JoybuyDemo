<script setup>
import { useLocale } from '../../composables/useLocale'

import ShopApplicationDetails from '../account/ShopApplicationDetails.vue'

// m. host（ADR 0001）申请开店页。视觉依据：申请开店页面/申请开店-手机版.html
// 与 待审核-手机版.html——480px 居中单列、卡片 14px 圆角/16px 内边距、
// 字号 13/28、按钮与选择项 44px 触控高度。表单状态（7 项字段、上传、
// 提交、驳回重申）由 pages/account/apply-shop.vue 持有，本组件只负责
// 展示与把编辑动作回传（与 MobileAddresses 同款 props/emit 约定）。
defineProps({
  signedIn: { type: Boolean, default: false },
  showForm: { type: Boolean, default: false },
  status: { type: String, default: '' },
  application: { type: Object, default: null },
  form: { type: Object, required: true },
  submitting: { type: Boolean, default: false },
  formError: { type: String, default: '' },
  fieldErrors: { type: Object, default: () => ({}) },
  logoUploading: { type: Boolean, default: false },
  logoUploadError: { type: String, default: '' },
  docUploading: { type: Boolean, default: false },
  docUploadError: { type: String, default: '' },
  idDocumentTypes: { type: Array, default: () => [] },
  documentTypeLabel: { type: String, default: '—' },
  statusLabel: { type: String, default: '' },
  merchantSwitching: { type: Boolean, default: false },
  merchantPendingDeposit: { type: Boolean, default: false },
})

const emit = defineEmits(['field', 'logo-file', 'doc-file', 'submit', 'reapply', 'open-merchant'])

const { t } = useLocale()

function onInput(name, event) {
  emit('field', name, event.target.value)
}

function onFile(kind, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) emit(kind, file)
}
</script>

<template>
  <section class="m-apply" aria-labelledby="m-apply-title">
    <div class="m-apply__card">
      <h1 id="m-apply-title" class="m-apply__title">{{ t('shopApply.title') }}</h1>

      <p v-if="!signedIn" class="m-apply__signedout">{{ t('account.signInPrompt') }}</p>

      <template v-else>
        <p v-if="showForm" class="m-apply__subtitle">{{ t('shopApply.subtitle') }}</p>

        <form
          v-if="showForm"
          class="m-apply__panel m-apply__form"
          novalidate
          @submit.prevent="emit('submit')"
        >
          <p v-if="status === 'REJECTED'" class="m-apply__alert" role="alert">
            {{ t('shopApply.rejectedTitle') }}：{{ application?.reject_reason || '—' }}
          </p>

          <!-- 1. 店铺logo -->
          <div class="m-apply__field">
            <span id="m-apply-logo-label" class="m-apply__label">
              {{ t('shopApply.shopLogo') }}<b aria-hidden="true">*</b>
            </span>
            <label class="m-apply__upload" for="m-apply-logo">
              <img
                v-if="form.logoPreview"
                class="m-apply__upload-preview"
                :src="form.logoPreview"
                :alt="t('shopApply.shopLogo')"
              />
              <span aria-hidden="true">↑</span>
              {{ logoUploading ? t('shopApply.uploading') : t('shopApply.chooseImage') }}
              <input
                id="m-apply-logo"
                class="m-apply__file"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                :disabled="logoUploading"
                aria-required="true"
                aria-describedby="m-apply-logo-hint"
                :aria-label="t('shopApply.uploadLogo')"
                @change="onFile('logo-file', $event)"
              />
            </label>
            <small id="m-apply-logo-hint" class="m-apply__hint">{{
              t('shopApply.uploadHint')
            }}</small>
            <p v-if="logoUploadError || fieldErrors.logo" class="m-apply__error" role="alert">
              {{ logoUploadError || fieldErrors.logo }}
            </p>
          </div>

          <!-- 2. 用户名字 -->
          <div class="m-apply__field">
            <label class="m-apply__label" for="m-apply-user-name">
              {{ t('shopApply.userName') }}<b aria-hidden="true">*</b>
            </label>
            <input
              id="m-apply-user-name"
              class="m-apply__input"
              type="text"
              maxlength="60"
              required
              aria-required="true"
              :value="form.userName"
              :placeholder="t('shopApply.userNamePlaceholder')"
              @input="onInput('userName', $event)"
            />
            <p v-if="fieldErrors.userName" class="m-apply__error" role="alert">
              {{ fieldErrors.userName }}
            </p>
          </div>

          <!-- 3. 店铺名称 -->
          <div class="m-apply__field">
            <label class="m-apply__label" for="m-apply-shop-name">
              {{ t('shopApply.shopName') }}<b aria-hidden="true">*</b>
            </label>
            <input
              id="m-apply-shop-name"
              class="m-apply__input"
              type="text"
              maxlength="60"
              required
              aria-required="true"
              :value="form.shopName"
              :placeholder="t('shopApply.shopNamePlaceholder')"
              @input="onInput('shopName', $event)"
            />
            <p v-if="fieldErrors.shopName" class="m-apply__error" role="alert">
              {{ fieldErrors.shopName }}
            </p>
          </div>

          <!-- 4. 手机号码 -->
          <div class="m-apply__field">
            <label class="m-apply__label" for="m-apply-phone">
              {{ t('shopApply.phone') }}<b aria-hidden="true">*</b>
            </label>
            <input
              id="m-apply-phone"
              class="m-apply__input"
              type="tel"
              maxlength="32"
              required
              aria-required="true"
              :value="form.phone"
              :placeholder="t('shopApply.phonePlaceholder')"
              @input="onInput('phone', $event)"
            />
            <p v-if="fieldErrors.phone" class="m-apply__error" role="alert">
              {{ fieldErrors.phone }}
            </p>
          </div>

          <!-- 5. 邀请码（选填） -->
          <div class="m-apply__field">
            <label class="m-apply__label" for="m-apply-referrer">
              {{ t('shopApply.referrerCode') }}
            </label>
            <input
              id="m-apply-referrer"
              class="m-apply__input"
              type="text"
              maxlength="32"
              :value="form.referrerCode"
              :placeholder="t('shopApply.referrerCodePlaceholder')"
              aria-describedby="m-apply-referrer-hint"
              @input="onInput('referrerCode', $event)"
            />
            <small id="m-apply-referrer-hint" class="m-apply__hint">
              {{ t('shopApply.referrerCodeHint') }}
            </small>
          </div>

          <!-- 6. 个人证件（类型三选一 + 证件照片） -->
          <div class="m-apply__identity" role="group" :aria-label="t('shopApply.idDocumentsGroup')">
            <fieldset class="m-apply__field m-apply__fieldset">
              <legend class="m-apply__label">
                {{ t('shopApply.idDocument') }}<b aria-hidden="true">*</b>
              </legend>
              <div
                class="m-apply__choices"
                role="radiogroup"
                :aria-label="t('shopApply.idDocumentType')"
              >
                <label
                  v-for="item in idDocumentTypes"
                  :key="item.value"
                  class="m-apply__choice"
                  :class="{ 'is-selected': form.idDocumentType === item.value }"
                >
                  <input
                    class="m-apply__radio"
                    type="radio"
                    name="m-apply-id-document-type"
                    :value="item.value"
                    :checked="form.idDocumentType === item.value"
                    @change="emit('field', 'idDocumentType', item.value)"
                  />
                  <span class="m-apply__choice-mark" aria-hidden="true"></span>
                  <span>{{ item.label }}</span>
                </label>
              </div>
              <p v-if="fieldErrors.doc" class="m-apply__error" role="alert">
                {{ fieldErrors.doc }}
              </p>
            </fieldset>

            <div class="m-apply__field">
              <span id="m-apply-doc-label" class="m-apply__label">
                {{ t('shopApply.idDocumentImage') }}<b aria-hidden="true">*</b>
              </span>
              <label class="m-apply__upload" for="m-apply-doc">
                <img
                  v-if="form.docPreview"
                  class="m-apply__upload-preview"
                  :src="form.docPreview"
                  :alt="t('shopApply.idDocumentImage')"
                />
                <span aria-hidden="true">↑</span>
                {{ docUploading ? t('shopApply.uploading') : t('shopApply.chooseImage') }}
                <input
                  id="m-apply-doc"
                  class="m-apply__file"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  :disabled="docUploading"
                  aria-required="true"
                  aria-describedby="m-apply-doc-hint"
                  :aria-label="t('shopApply.uploadDocImage')"
                  @change="onFile('doc-file', $event)"
                />
              </label>
              <small id="m-apply-doc-hint" class="m-apply__hint">{{
                t('shopApply.uploadHint')
              }}</small>
              <p v-if="docUploadError || fieldErrors.doc" class="m-apply__error" role="alert">
                {{ docUploadError || fieldErrors.doc }}
              </p>
            </div>
          </div>

          <!-- 7. 个人居住地址 -->
          <div class="m-apply__field">
            <label class="m-apply__label" for="m-apply-address">
              {{ t('shopApply.residentialAddress') }}<b aria-hidden="true">*</b>
            </label>
            <textarea
              id="m-apply-address"
              class="m-apply__input m-apply__address"
              rows="2"
              maxlength="255"
              required
              aria-required="true"
              :value="form.residentialAddress"
              :placeholder="t('shopApply.residentialAddressPlaceholder')"
              @input="onInput('residentialAddress', $event)"
            ></textarea>
            <p v-if="fieldErrors.residentialAddress" class="m-apply__error" role="alert">
              {{ fieldErrors.residentialAddress }}
            </p>
          </div>

          <p v-if="formError" class="m-apply__error" role="alert">{{ formError }}</p>

          <div class="m-apply__actions">
            <button class="m-apply__submit" type="submit" :disabled="submitting">
              {{ submitting ? t('shopApply.submitting') : t('shopApply.submit') }}
            </button>
          </div>
        </form>

        <template v-else-if="status === 'PENDING'">
          <div class="m-apply__status m-apply__status--pending" role="status">
            <span class="m-apply__icon" aria-hidden="true">
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
            mobile
            :application="application"
            :document-type-label="documentTypeLabel"
          />
        </template>

        <template v-else-if="status === 'APPROVED'">
          <div class="m-apply__status m-apply__status--approved" role="status">
            <span class="m-apply__icon" aria-hidden="true">
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
            mobile
            :application="application"
            :document-type-label="documentTypeLabel"
            :status-label="statusLabel"
            show-status
            show-reviewed-at
          />

          <div class="m-apply__actions">
            <button
              class="m-apply__submit"
              type="button"
              :disabled="merchantSwitching"
              @click="emit('open-merchant')"
            >
              {{ merchantSwitching ? t('merchantEntry.opening') : t('shopApply.goMerchantCenter') }}
            </button>
          </div>
        </template>

        <template v-else-if="status === 'REJECTED'">
          <div class="m-apply__status m-apply__status--rejected" role="alert">
            <span class="m-apply__icon" aria-hidden="true">
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
            mobile
            :application="application"
            :document-type-label="documentTypeLabel"
            :status-label="statusLabel"
            show-status
            show-reviewed-at
          />

          <div class="m-apply__actions">
            <button class="m-apply__submit" type="button" @click="emit('reapply')">
              {{ t('shopApply.reApply') }}
            </button>
          </div>
        </template>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* 设计稿数值：申请开店-手机版.html / 待审核-手机版.html */
.m-apply {
  width: 100%;
  max-width: 480px;
  margin: 0 auto;
  padding: 12px;
  background: #edf0f4;
  color: #191e2b;
  font:
    14px/1.5 'Microsoft YaHei',
    'PingFang SC',
    sans-serif;
}

.m-apply__card {
  padding: 16px;
  border: 1px solid #dce0e7;
  border-radius: 14px;
  background: #f5f6f8;
  box-shadow: 0 10px 30px #161b2620;
}

.m-apply__title {
  margin: 0 0 5px;
  color: #191e2b;
  font-size: 28px;
  font-weight: 720;
  line-height: 1.2;
}

.m-apply__subtitle,
.m-apply__signedout {
  margin: 0;
  color: #5a6373;
  font-size: 13px;
}

.m-apply__panel {
  margin-top: 15px;
  padding: 22px 14px;
  border: 1px solid #dce0e7;
  border-radius: 15px;
  background: #ffffff;
}

.m-apply__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.m-apply__field {
  display: block;
  min-width: 0;
}

.m-apply__fieldset {
  margin: 0;
  padding: 0;
  border: 0;
}

.m-apply__label {
  display: block;
  margin: 0 0 4px;
  padding: 0;
  color: #191e2b;
  font-size: 13px;
  font-weight: 650;
}

.m-apply__label b {
  color: #bd113b;
}

.m-apply__input {
  width: 100%;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  background: #ffffff;
  color: #191e2b;
  font: inherit;
  font-size: 13px;
}

.m-apply__input::placeholder {
  color: #5a6373;
}

.m-apply__address {
  min-height: 58px;
  resize: vertical;
}

.m-apply__upload {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  width: 100%;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px dashed #dce0e7;
  border-radius: 8px;
  background: #fff5f7;
  color: #bd113b;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

.m-apply__upload:focus-within {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.m-apply__upload-preview {
  width: 28px;
  height: 28px;
  border: 1px solid #dce0e7;
  border-radius: 6px;
  object-fit: cover;
}

/* 视觉隐藏但仍可聚焦：键盘可跳到「选择图片」并回车打开文件框。 */
.m-apply__file {
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

.m-apply__hint {
  display: block;
  margin-top: 3px;
  color: #5a6373;
  font-size: 11px;
}

.m-apply__error {
  margin: 3px 0 0;
  color: #b42318;
  font-size: 12px;
}

.m-apply__alert {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  background: #fff5f7;
  color: #bd113b;
  font-size: 13px;
}

.m-apply__choices {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.m-apply__choice {
  position: relative;
  display: inline-flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  color: #5a6373;
  font-size: 13px;
  text-align: center;
  white-space: nowrap;
  cursor: pointer;
}

.m-apply__choice.is-selected {
  border-color: #bd113b;
  background: #fff5f7;
  color: #bd113b;
}

.m-apply__choice:focus-within {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.m-apply__radio {
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

.m-apply__choice-mark::before {
  content: '○';
  margin-right: 4px;
}

.m-apply__choice.is-selected .m-apply__choice-mark::before {
  content: '◉';
}

.m-apply__identity {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  padding-block: 16px;
  padding-inline: 0;
  border-block: 1px solid #dce0e7;
}

.m-apply__actions {
  display: block;
  padding-top: 14px;
  border-top: 1px solid #dce0e7;
}

.m-apply__submit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 44px;
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

.m-apply__submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.m-apply__submit:focus-visible {
  outline: 2px solid #175cd3;
  outline-offset: 2px;
}

.m-apply__status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 15px;
  padding: 14px;
  border-radius: 14px;
  background: #fff3df;
  color: #753d00;
}

.m-apply__status strong {
  font-size: 18px;
  font-weight: 700;
}

.m-apply__status p {
  margin: 2px 0 0;
  color: inherit;
  font-size: 13px;
}

.m-apply__status--approved {
  background: #e7f6ec;
  color: #0e7a3d;
}

.m-apply__status--rejected {
  background: #fdecea;
  color: #b42318;
}

.m-apply__icon {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  padding: 8px;
  border-radius: 11px;
  background: #f8dfb1;
  color: inherit;
}

.m-apply__status--approved .m-apply__icon {
  background: #cbeed8;
}

.m-apply__status--rejected .m-apply__icon {
  background: #f8d3ce;
}
</style>
