<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile address book (docs/20 §5.4): delivery/pickup tabs (same semantics as
// the desktop page), one card per address (default marker, copy, edit,
// delete) and the add/edit form rendered inline with the same fields and
// validation ownership as the desktop modal — the page keeps the reactive
// form and the validation/save logic, the component forwards field edits as
// `field` events and submits via `save` (ADR 0001: desktop template
// untouched).
defineProps({
  signedIn: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  tab: { type: String, default: 'delivery' },
  tabs: { type: Array, default: () => [] },
  addresses: { type: Array, default: () => [] },
  showForm: { type: Boolean, default: false },
  formTitle: { type: String, default: '' },
  form: { type: Object, required: true },
  formError: { type: String, default: '' },
  saving: { type: Boolean, default: false },
  addButtonLabel: { type: String, default: '' },
  deleteTarget: { type: Object, default: null },
  deleting: { type: Boolean, default: false },
})

const emit = defineEmits([
  'tab',
  'add',
  'edit',
  'copy',
  'setDefault',
  'requestDelete',
  'confirmDelete',
  'cancelDelete',
  'closeForm',
  'save',
  'field',
  'back',
])

const { t } = useLocale()

function onField(name, event) {
  const target = event.target
  emit('field', name, target.type === 'checkbox' ? target.checked : target.value)
}
</script>

<template>
  <div class="m-addr">
    <MobilePageHeader :title="t('addresses.title')" @back="emit('back')" />

    <!-- Signed out -->
    <div v-if="!signedIn" class="m-addr__empty" role="status">
      <p class="m-addr__empty-title">{{ t('addresses.signInRequired') }}</p>
      <p class="m-addr__empty-note">{{ t('addresses.signInNote') }}</p>
      <NuxtLink class="m-addr__signin" to="/auth/login">{{ t('header.signIn') }}</NuxtLink>
    </div>

    <template v-else>
      <!-- Tab row + add button -->
      <nav class="m-addr__tabs" :aria-label="t('addressDrawer.tabsLabel')">
        <button
          v-for="item in tabs"
          :key="item.key"
          class="m-addr__tab"
          :class="{ 'm-addr__tab--active': item.key === tab }"
          type="button"
          @click="emit('tab', item.key)"
        >
          {{ item.label }}
        </button>
      </nav>

      <!-- Pickup tab: honest empty state, same copy as the desktop. -->
      <div v-if="tab === 'pickup'" class="m-addr__empty" role="status">
        <p class="m-addr__empty-title">{{ t('addresses.pickupEmpty') }}</p>
      </div>

      <template v-else>
        <!-- Add/edit form (inline card) -->
        <section v-if="showForm" class="m-addr__form-card">
          <header class="m-addr__form-head">
            <h2 class="m-addr__form-title">{{ formTitle }}</h2>
            <button
              type="button"
              class="m-addr__form-close"
              :aria-label="t('addresses.close')"
              :disabled="saving"
              @click="emit('closeForm')"
            >
              ×
            </button>
          </header>

          <form class="m-addr__form" novalidate @submit.prevent="emit('save')">
            <p v-if="formError" class="m-addr__form-error" role="alert">{{ formError }}</p>

            <label class="m-addr__field">
              <span>{{ t('addresses.fullName') }} *</span>
              <input
                type="text"
                autocomplete="name"
                :value="form.full_name"
                required
                @input="onField('full_name', $event)"
              />
            </label>

            <label class="m-addr__field">
              <span>{{ t('addresses.phone') }} *</span>
              <input
                type="tel"
                autocomplete="tel"
                :value="form.phone"
                required
                @input="onField('phone', $event)"
              />
            </label>

            <label class="m-addr__field">
              <span>{{ t('addresses.line1') }} *</span>
              <input
                type="text"
                autocomplete="address-line1"
                :value="form.line1"
                required
                @input="onField('line1', $event)"
              />
            </label>

            <label class="m-addr__field">
              <span>{{ t('addresses.line2') }}</span>
              <input
                type="text"
                autocomplete="address-line2"
                :value="form.line2"
                @input="onField('line2', $event)"
              />
            </label>

            <div class="m-addr__field-row">
              <label class="m-addr__field">
                <span>{{ t('addresses.city') }} *</span>
                <input
                  type="text"
                  autocomplete="address-level2"
                  :value="form.city"
                  required
                  @input="onField('city', $event)"
                />
              </label>
              <label class="m-addr__field">
                <span>{{ t('addresses.county') }}</span>
                <input
                  type="text"
                  autocomplete="address-level1"
                  :value="form.county"
                  @input="onField('county', $event)"
                />
              </label>
            </div>

            <label class="m-addr__field">
              <span>{{ t('addresses.postcode') }} *</span>
              <input
                type="text"
                autocomplete="postal-code"
                :value="form.postcode"
                required
                @input="onField('postcode', $event)"
              />
            </label>

            <label class="m-addr__switch">
              <input
                type="checkbox"
                :checked="form.is_default"
                @change="onField('is_default', $event)"
              />
              <span>{{ t('addresses.setDefaultCheckbox') }}</span>
            </label>

            <footer class="m-addr__form-actions">
              <button
                type="button"
                class="m-addr__btn-cancel"
                :disabled="saving"
                @click="emit('closeForm')"
              >
                {{ t('addresses.cancel') }}
              </button>
              <button type="submit" class="m-addr__btn-save" :disabled="saving">
                {{ saving ? t('addresses.saving') : t('addresses.save') }}
              </button>
            </footer>
          </form>
        </section>

        <!-- Add new address -->
        <button type="button" class="m-addr__add" @click="emit('add')">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path
              d="M8.75 3.203a.75.75 0 1 0-1.5 0v4.05H3.2a.75.75 0 0 0 0 1.5h4.05v4.05a.75.75 0 0 0 1.5 0v-4.05h4.05a.75.75 0 0 0 0-1.5H8.75z"
              fill="currentColor"
            />
          </svg>
          {{ addButtonLabel }}
        </button>

        <!-- Loading skeleton -->
        <div v-if="loading" class="m-addr__list" aria-hidden="true">
          <div class="m-addr__card m-addr__card--skeleton">
            <span class="m-addr__sk-line"></span>
            <span class="m-addr__sk-line m-addr__sk-line--short"></span>
          </div>
        </div>

        <!-- Empty state -->
        <div v-else-if="addresses.length === 0" class="m-addr__empty" role="status">
          <p class="m-addr__empty-title">{{ t('addresses.empty') }}</p>
        </div>

        <!-- Address cards -->
        <ul v-else class="m-addr__list">
          <li v-for="address in addresses" :key="address.publicId">
            <article class="m-addr__card" :class="{ 'm-addr__card--default': address.isDefault }">
              <div class="m-addr__card-head">
                <span class="m-addr__name">{{ address.fullName }}</span>
                <span class="m-addr__phone">{{ address.phone }}</span>
                <span v-if="address.isDefault" class="m-addr__default-badge">
                  {{ t('addresses.defaultAddress') }}
                </span>
              </div>
              <p class="m-addr__lines">{{ address.lines }}</p>
              <p v-if="!address.isServiceable" class="m-addr__warning">
                {{ t('addresses.notServiceable') }}
              </p>
              <footer class="m-addr__card-foot">
                <button
                  type="button"
                  class="m-addr__card-action"
                  :disabled="address.isDefault"
                  @click="emit('setDefault', address)"
                >
                  {{
                    address.isDefault ? t('addresses.defaultAddress') : t('addresses.setDefault')
                  }}
                </button>
                <div class="m-addr__card-actions">
                  <button
                    type="button"
                    class="m-addr__icon-btn"
                    :aria-label="t('addresses.copy')"
                    @click="emit('copy', address)"
                  >
                    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                      <path
                        d="M5 2h7a1 1 0 0 1 1 1v8h-1.5V3.5H5V2Zm-2 3h7a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.3"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="m-addr__icon-btn"
                    :aria-label="t('addresses.edit')"
                    @click="emit('edit', address)"
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
                    type="button"
                    class="m-addr__icon-btn"
                    :aria-label="t('addresses.delete')"
                    @click="emit('requestDelete', address)"
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
    </template>

    <!-- Delete confirmation -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="m-addr__modal" @click.self="emit('cancelDelete')">
        <div class="m-addr__modal-panel" role="dialog" aria-modal="true">
          <h2 class="m-addr__modal-title">{{ t('addresses.deleteTitle') }}</h2>
          <p class="m-addr__modal-text">
            {{ t('addresses.deleteConfirm').replace('{name}', deleteTarget.fullName) }}
          </p>
          <footer class="m-addr__form-actions">
            <button type="button" class="m-addr__btn-cancel" @click="emit('cancelDelete')">
              {{ t('addresses.cancel') }}
            </button>
            <button
              type="button"
              class="m-addr__btn-save m-addr__btn-save--danger"
              :disabled="deleting"
              @click="emit('confirmDelete')"
            >
              {{ deleting ? t('addresses.deleting') : t('addresses.delete') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.m-addr {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

/* Tab row */
.m-addr__tabs {
  display: flex;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
}

.m-addr__tab {
  min-height: 44px;
  flex: 1;
  padding: 0 14px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  cursor: pointer;
}

.m-addr__tab--active {
  font-weight: var(--font-weight-bold);
  border-bottom-color: #1a1a1a;
}

/* Add button */
.m-addr__add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: calc(100% - 32px);
  min-height: 44px;
  margin: 12px 16px 0;
  border: 1px dashed #e1251b;
  border-radius: 12px;
  background: #ffffff;
  color: #e1251b;
  font: inherit;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

/* Cards */
.m-addr__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 12px 16px 0;
  padding: 0;
  list-style: none;
}

.m-addr__card {
  border-radius: 12px;
  background: #ffffff;
  padding: 14px;
}

.m-addr__card--default {
  box-shadow: inset 0 0 0 1.5px #e1251b;
}

.m-addr__card--skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.m-addr__sk-line {
  height: 16px;
  width: 55%;
  border-radius: 4px;
  background: #eceef1;
}

.m-addr__sk-line--short {
  width: 40%;
}

.m-addr__card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.m-addr__name {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

.m-addr__phone {
  color: #55565b;
  font-size: 14px;
}

.m-addr__default-badge {
  display: inline-flex;
  align-items: center;
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fdeaea;
  color: #e1251b;
  font-size: 12px;
  font-weight: var(--font-weight-semibold);
}

.m-addr__lines {
  margin: 8px 0 0;
  color: #55565b;
  font-size: 14px;
  line-height: 20px;
  word-break: break-all;
}

.m-addr__warning {
  margin: 8px 0 0;
  color: #995c00;
  font-size: 13px;
}

.m-addr__card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.m-addr__card-action {
  min-height: 32px;
  padding: 0 4px;
  border: 0;
  background: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.m-addr__card-action:disabled {
  color: #e1251b;
  font-weight: var(--font-weight-semibold);
  cursor: default;
}

.m-addr__card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.m-addr__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
}

.m-addr__icon-btn:hover {
  background: #f5f6fa;
}

/* Form card */
.m-addr__form-card {
  margin: 12px 16px 0;
  padding: 14px;
  border-radius: 12px;
  background: #ffffff;
}

.m-addr__form-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.m-addr__form-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

.m-addr__form-close {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #55565b;
  font-size: 20px;
  cursor: pointer;
}

.m-addr__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.m-addr__form-error {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fdeaea;
  color: #e1251b;
  font-size: 13px;
}

.m-addr__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #55565b;
}

.m-addr__field-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.m-addr__field input {
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid #e0e1e5;
  border-radius: 8px;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 15px;
}

.m-addr__field input:focus {
  border-color: #1a1a1a;
  outline: none;
}

.m-addr__switch {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  color: #1a1a1a;
  font-size: 14px;
}

.m-addr__switch input {
  width: 18px;
  height: 18px;
  accent-color: #1a1a1a;
}

.m-addr__form-actions {
  display: flex;
  gap: 12px;
  padding-top: 4px;
}

.m-addr__btn-cancel,
.m-addr__btn-save {
  min-height: 44px;
  flex: 1;
  border-radius: 22px;
  font: inherit;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.m-addr__btn-cancel {
  border: 1px solid #1a1a1a;
  background: #ffffff;
  color: #1a1a1a;
}

.m-addr__btn-save {
  border: 1px solid #1a1a1a;
  background: #1a1a1a;
  color: #ffffff;
}

.m-addr__btn-save--danger {
  border-color: #e1251b;
  background: #e1251b;
}

.m-addr__btn-save:disabled {
  opacity: 0.6;
  cursor: progress;
}

/* Empty / signed-out */
.m-addr__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
  text-align: center;
}

.m-addr__empty-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}

.m-addr__empty-note {
  margin: 8px 0 0;
  color: #7a7d85;
  font-size: 14px;
  line-height: 1.5;
}

.m-addr__signin {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  margin-top: 16px;
  padding: 0 24px;
  border-radius: 22px;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

/* Delete modal */
.m-addr__modal {
  position: fixed;
  inset: 0;
  z-index: 1600;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.5);
}

.m-addr__modal-panel {
  width: min(20rem, 100%);
  padding: 20px;
  border-radius: 12px;
  background: #ffffff;
}

.m-addr__modal-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 17px;
  font-weight: var(--font-weight-bold);
}

.m-addr__modal-text {
  margin: 10px 0 16px;
  color: #55565b;
  font-size: 14px;
  line-height: 1.5;
}

.m-addr__form-actions + * {
  margin-top: 0;
}
</style>
