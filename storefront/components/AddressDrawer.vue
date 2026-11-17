<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'
import { MARKET_OPTIONS } from '../composables/useMarketLocale'

// Deliver-to drawer, rebuilt 1:1 against joybuy.co.uk (probe 2026-11-16).
// Measured on the live site at 1440x900: paper 616px wide / full height,
// backdrop rgba(0,0,0,.5), 225ms translateX slide-in, top bar 24px padding,
// country select 240x40, tabs 90x44 with a 3px #19191B indicator, 1px
// #F5F6FA divider, postcode input 40px tall with #CCCED2 border, 4px radius,
// and a full-width 40px #CC0C1C apply button inset 24px.
//
// The country/region control is a custom listbox, not a native <select>:
// native option elements cannot render the local CSS flags, so the expanded
// list lost the flag-before-name order. Real site metrics (probe 2026-11-16):
// trigger 240x40, flag 24x16 inset 16px, 8px gap to a 14px/400 name, 16px
// chevron inset 16px; menu 240px wide flush under the trigger, max-height
// 250px (scrolls), 8px vertical padding, 4px radius, elevation-8 shadow,
// items 44px tall with 16px horizontal padding, hover rgba(0,0,0,.04) and a
// 20px #1A1A1A check on the selected row.
//
// The drawer owns a DRAFT selection: clicking an address or typing a postcode
// never changes the header until the user presses Apply. The parent persists
// and closes on the apply event.
const props = defineProps({
  open: { type: Boolean, default: false },
  authenticated: { type: Boolean, default: false },
  addresses: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  appliedMode: { type: String, default: '' },
  appliedPostcode: { type: String, default: '' },
  country: { type: String, default: 'GB' },
  loading: { type: Boolean, default: false },
  error: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'apply', 'country-change'])

const { t } = useLocale()

const panel = ref(null)
const closeButton = ref(null)
const postcodeInput = ref(null)
const countryWrap = ref(null)
const countryTrigger = ref(null)
const countryMenu = ref(null)

const countryOpen = ref(false)
const countryActiveIndex = ref(0)

const activeTab = ref('delivery')
const mode = ref('')
const draftAddressId = ref('')
const draftPostcode = ref('')
const draftCountry = ref(props.country || 'GB')
const validationError = ref('')

let previousActiveElement = null
let previousBodyOverflow = ''
let scrollLocked = false

const TITLE_ID = 'address-drawer-title'
const DELIVERY_PANEL_ID = 'address-drawer-delivery'
const PICKUP_PANEL_ID = 'address-drawer-pickup'
const COUNTRY_LISTBOX_ID = 'address-drawer-country-listbox'

// Loose UK postcode shape (EC1A 1BB / SW1A 1AA / M1 1AE), per requirement.
const UK_POSTCODE = /^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/

function countryName(code) {
  return t(`addressDrawer.countries.${code}`)
}

function countryIndex(code) {
  const index = MARKET_OPTIONS.findIndex((option) => option.code === code)
  return index < 0 ? 0 : index
}

function countryOptionElements() {
  return countryMenu.value ? [...countryMenu.value.querySelectorAll('[role="option"]')] : []
}

function focusCountryOption(index) {
  const options = countryOptionElements()
  if (!options.length) return
  const bounded = (index + options.length) % options.length
  countryActiveIndex.value = bounded
  const option = options[bounded]
  if (!option) return
  // Keep the highlighted row inside the 250px scroll box (real site scrolls
  // to the selected country when the menu opens).
  const menu = countryMenu.value
  if (menu) {
    const desired = option.offsetTop + option.offsetHeight - menu.clientHeight
    if (desired > 0) menu.scrollTop = desired
  }
  option.focus?.()
}

function openCountry(index = countryIndex(draftCountry.value)) {
  if (countryOpen.value) return
  countryOpen.value = true
  nextTick(() => focusCountryOption(index))
}

function closeCountry({ restoreFocus = true } = {}) {
  if (!countryOpen.value) return
  countryOpen.value = false
  if (restoreFocus) countryTrigger.value?.focus?.()
}

function toggleCountry() {
  if (countryOpen.value) closeCountry()
  else openCountry()
}

function selectCountry(code) {
  if (code !== draftCountry.value) {
    draftCountry.value = code
    validationError.value = ''
    emit('country-change', code)
  }
  closeCountry()
}

function onCountryTriggerKeydown(event) {
  if (event.key === 'Escape' && countryOpen.value) {
    event.preventDefault()
    event.stopPropagation()
    closeCountry()
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return
  event.preventDefault()
  openCountry(
    event.key === 'ArrowUp' ? MARKET_OPTIONS.length - 1 : countryIndex(draftCountry.value),
  )
}

function onCountryMenuKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeCountry()
    return
  }
  if (event.key === 'Tab') {
    // Let focus leave the menu; the focusout handler closes it without
    // stealing the user's next tab stop.
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    focusCountryOption(countryActiveIndex.value + (event.key === 'ArrowDown' ? 1 : -1))
    return
  }
  if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault()
    focusCountryOption(event.key === 'Home' ? 0 : MARKET_OPTIONS.length - 1)
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    const option = MARKET_OPTIONS[countryActiveIndex.value]
    if (option) selectCountry(option.code)
  }
}

function onCountryMenuFocusOut(event) {
  if (countryWrap.value?.contains(event.relatedTarget)) return
  closeCountry({ restoreFocus: false })
}

function onDocumentPointerDown(event) {
  if (!countryOpen.value) return
  if (countryWrap.value?.contains(event.target)) return
  closeCountry({ restoreFocus: false })
}

watch(countryOpen, (isOpen) => {
  if (typeof document === 'undefined') return
  if (isOpen) document.addEventListener('pointerdown', onDocumentPointerDown, true)
  else document.removeEventListener('pointerdown', onDocumentPointerDown, true)
})

function normalizePostcode(value) {
  return String(value || '')
    .trim()
    .toUpperCase()
    .replace(/\s+/g, ' ')
}

function addressLineOne(address) {
  return [address.line1, address.line2, address.city].filter(Boolean).join(', ')
}

function addressLineTwo(address) {
  return [address.county, address.postcode].filter(Boolean).join(' ')
}

function addressLabel(address) {
  return [address.full_name, addressLineOne(address), addressLineTwo(address)]
    .filter(Boolean)
    .join(', ')
}

function resetDraft() {
  activeTab.value = 'delivery'
  draftCountry.value = props.country || 'GB'
  draftAddressId.value = props.selectedId || ''
  draftPostcode.value = props.appliedMode === 'postcode' ? props.appliedPostcode || '' : ''
  mode.value = props.appliedMode || (props.selectedId ? 'address' : '')
  validationError.value = ''
}

function lockScroll() {
  if (typeof document === 'undefined' || scrollLocked) return
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  scrollLocked = true
}

function unlockScroll() {
  if (typeof document === 'undefined' || !scrollLocked) return
  document.body.style.overflow = previousBodyOverflow
  scrollLocked = false
}

function restoreFocus() {
  const target = previousActiveElement
  previousActiveElement = null
  if (target && typeof target.focus === 'function' && document.contains(target)) {
    target.focus()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (typeof document === 'undefined') return
    if (isOpen) {
      resetDraft()
      previousActiveElement = document.activeElement
      lockScroll()
      await nextTick()
      closeButton.value?.focus?.()
    } else {
      closeCountry({ restoreFocus: false })
      unlockScroll()
      restoreFocus()
    }
  },
)

// Addresses usually arrive after the drawer has opened; adopt the applied
// address when the drawer has no draft of its own yet.
watch(
  () => props.selectedId,
  (selectedId) => {
    if (!props.open || mode.value || !selectedId) return
    mode.value = 'address'
    draftAddressId.value = selectedId
  },
)

watch(
  () => props.country,
  (country) => {
    if (country && country !== draftCountry.value) draftCountry.value = country
  },
)

function onKeydown(event) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = [
    ...panel.value.querySelectorAll(
      'a[href], button:not([disabled]):not([tabindex="-1"]), input:not([disabled])',
    ),
  ]
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointerdown', onDocumentPointerDown, true)
  unlockScroll()
})

function setTab(nextTab) {
  if (activeTab.value === nextTab) return
  activeTab.value = nextTab
  validationError.value = ''
}

function onTabKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  setTab(activeTab.value === 'delivery' ? 'pickup' : 'delivery')
}

function selectPostcodeMode() {
  mode.value = 'postcode'
  draftAddressId.value = ''
  validationError.value = ''
}

function onPostcodeFocus() {
  if (mode.value !== 'postcode') selectPostcodeMode()
}

function onPostcodeInput(event) {
  if (mode.value !== 'postcode') selectPostcodeMode()
  draftPostcode.value = event.target.value
  validationError.value = ''
}

function selectAddress(publicId) {
  mode.value = 'address'
  draftAddressId.value = publicId
  draftPostcode.value = ''
  validationError.value = ''
}

function focusPostcode() {
  nextTick(() => postcodeInput.value?.focus?.())
}

function applySelection() {
  if (activeTab.value !== 'delivery') return

  if (mode.value === 'address') {
    if (!draftAddressId.value) {
      validationError.value = t('addressDrawer.selectAddressError')
      return
    }
    emit('apply', {
      mode: 'address',
      addressId: draftAddressId.value,
      postcode: '',
      country: draftCountry.value,
    })
    return
  }

  if (mode.value !== 'postcode') selectPostcodeMode()

  const postcode = normalizePostcode(draftPostcode.value)
  if (!postcode) {
    validationError.value = t('addressDrawer.postcodeRequired')
    focusPostcode()
    return
  }
  if (draftCountry.value === 'GB' && !UK_POSTCODE.test(postcode)) {
    validationError.value = t('addressDrawer.postcodeInvalid')
    focusPostcode()
    return
  }

  emit('apply', {
    mode: 'postcode',
    addressId: '',
    postcode,
    country: draftCountry.value,
  })
}
</script>

<template>
  <Transition name="drawer">
    <div v-if="open" class="address-drawer">
      <div class="address-drawer__backdrop" @click="emit('close')"></div>
      <section
        ref="panel"
        class="address-drawer__panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="TITLE_ID"
      >
        <h2 :id="TITLE_ID" class="visually-hidden">{{ t('addressDrawer.title') }}</h2>

        <!-- Top bar: custom country/region listbox (flag left, name right) + X. -->
        <div class="address-drawer__top">
          <div ref="countryWrap" class="country-select-wrap">
            <button
              ref="countryTrigger"
              class="country-select"
              :class="{ 'country-select--open': countryOpen }"
              type="button"
              aria-haspopup="listbox"
              :aria-expanded="countryOpen"
              :aria-controls="COUNTRY_LISTBOX_ID"
              :aria-label="`${t('addressDrawer.country')}: ${countryName(draftCountry)}`"
              @click="toggleCountry"
              @keydown="onCountryTriggerKeydown"
            >
              <span
                class="country-flag"
                :class="`country-flag--${draftCountry.toLowerCase()}`"
                aria-hidden="true"
              ></span>
              <span class="country-select__name">{{ countryName(draftCountry) }}</span>
              <svg
                class="country-select__chevron"
                :class="{ 'country-select__chevron--open': countryOpen }"
                viewBox="0 0 16 16"
                aria-hidden="true"
              >
                <path
                  d="m4 6 4 4 4-4"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
            <div
              v-if="countryOpen"
              :id="COUNTRY_LISTBOX_ID"
              ref="countryMenu"
              class="country-menu"
              role="listbox"
              :aria-label="t('addressDrawer.country')"
              @keydown="onCountryMenuKeydown"
              @focusout="onCountryMenuFocusOut"
            >
              <button
                v-for="(option, index) in MARKET_OPTIONS"
                :key="option.code"
                class="country-menu__option"
                :class="{ 'country-menu__option--selected': option.code === draftCountry }"
                type="button"
                role="option"
                :aria-selected="option.code === draftCountry"
                tabindex="-1"
                @mouseenter="countryActiveIndex = index"
                @click="selectCountry(option.code)"
              >
                <span
                  class="country-flag"
                  :class="`country-flag--${option.code.toLowerCase()}`"
                  aria-hidden="true"
                ></span>
                <span class="country-menu__name">{{ countryName(option.code) }}</span>
                <svg
                  v-if="option.code === draftCountry"
                  class="country-menu__check"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="currentColor" />
                </svg>
              </button>
            </div>
          </div>
          <button
            ref="closeButton"
            class="address-drawer__close"
            type="button"
            :aria-label="t('addressDrawer.close')"
            @click="emit('close')"
          >
            <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
              <path
                d="m5.832 5.833 8.333 8.334m-8.333 0 8.333-8.334"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>

        <!-- Tabs left, pencil "Manage" link pinned right on the same row. -->
        <div class="address-drawer__tab-row">
          <div
            class="address-drawer__tabs"
            role="tablist"
            :aria-label="t('addressDrawer.tabsLabel')"
          >
            <button
              :id="`${DELIVERY_PANEL_ID}-tab`"
              class="address-drawer__tab"
              :class="{ 'address-drawer__tab--active': activeTab === 'delivery' }"
              type="button"
              role="tab"
              :aria-selected="activeTab === 'delivery'"
              :aria-controls="DELIVERY_PANEL_ID"
              :tabindex="activeTab === 'delivery' ? 0 : -1"
              @click="setTab('delivery')"
              @keydown="onTabKeydown"
            >
              {{ t('addressDrawer.tabDelivery') }}
            </button>
            <button
              :id="`${PICKUP_PANEL_ID}-tab`"
              class="address-drawer__tab"
              :class="{ 'address-drawer__tab--active': activeTab === 'pickup' }"
              type="button"
              role="tab"
              :aria-selected="activeTab === 'pickup'"
              :aria-controls="PICKUP_PANEL_ID"
              :tabindex="activeTab === 'pickup' ? 0 : -1"
              @click="setTab('pickup')"
              @keydown="onTabKeydown"
            >
              {{ t('addressDrawer.tabPickup') }}
            </button>
          </div>
          <NuxtLink
            v-if="activeTab === 'delivery'"
            class="address-drawer__manage"
            to="/account/addresses"
            @click="emit('close')"
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <path
                d="M10.786 1.008a2.46 2.46 0 0 1 3.388 3.565l-8.72 8.309a.67.67 0 0 1-.46.184H2.396a.727.727 0 0 1-.727-.727v-2.26a1 1 0 0 1 .312-.726zm-6.058 10.725H3v-1.51l6.446-6.109 1.51 1.51z"
                fill="currentColor"
              />
            </svg>
            {{ t('addressDrawer.manage') }}
          </NuxtLink>
        </div>

        <div class="address-drawer__divider" aria-hidden="true"></div>

        <div
          v-if="activeTab === 'delivery'"
          :id="DELIVERY_PANEL_ID"
          class="address-drawer__body"
          role="tabpanel"
          :aria-labelledby="`${DELIVERY_PANEL_ID}-tab`"
        >
          <div class="address-drawer__options">
            <!-- Real site: greyed out and not actionable in the UK. -->
            <div class="address-drawer__location" aria-disabled="true">
              <span class="radio-dot radio-dot--disabled" aria-hidden="true"></span>
              <span>{{ t('addressDrawer.useMyLocation') }}</span>
            </div>

            <div class="address-drawer__postcode-row">
              <label class="address-drawer__postcode-toggle">
                <input
                  class="visually-hidden"
                  type="radio"
                  name="delivery-method"
                  value="postcode"
                  :checked="mode === 'postcode'"
                  @change="selectPostcodeMode"
                />
                <span
                  class="radio-dot"
                  :class="{ 'radio-dot--checked': mode === 'postcode' }"
                  aria-hidden="true"
                ></span>
                <span class="address-drawer__postcode-label">{{
                  t('addressDrawer.postcode')
                }}</span>
              </label>
              <input
                ref="postcodeInput"
                class="address-drawer__postcode-input"
                :class="{ 'address-drawer__postcode-input--invalid': validationError }"
                type="text"
                autocomplete="off"
                maxlength="10"
                :value="draftPostcode"
                :placeholder="t('addressDrawer.postcodePlaceholder')"
                :aria-invalid="Boolean(validationError)"
                :aria-describedby="validationError ? 'address-drawer-postcode-error' : undefined"
                @focus="onPostcodeFocus"
                @input="onPostcodeInput"
                @keydown.enter.prevent="applySelection"
              />
            </div>
            <p
              v-if="validationError"
              id="address-drawer-postcode-error"
              class="address-drawer__error"
              role="alert"
            >
              {{ validationError }}
            </p>
          </div>

          <!-- Signed out: keep the real site's prompt, but still allow a
               postcode-only delivery lookup (no saved addresses on the wire). -->
          <div v-if="!authenticated" class="address-drawer__signin">
            <svg class="address-drawer__signin-icon" viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="52" fill="#f0f1f2" />
              <path
                d="M60 30a20 20 0 0 1 20 20c0 7-3.4 12.9-9 16.3L60 88l-11-21.7c-5.6-3.4-9-9.3-9-16.3a20 20 0 0 1 20-20Z"
                fill="#c2c4cc"
              />
              <circle cx="60" cy="50" r="7" fill="#fff" />
            </svg>
            <p class="address-drawer__signin-text">{{ t('addressDrawer.signInPrompt') }}</p>
            <NuxtLink class="address-drawer__signin-link" to="/auth/login" @click="emit('close')">{{
              t('header.signIn')
            }}</NuxtLink>
          </div>

          <template v-else>
            <p v-if="loading" class="address-drawer__status" role="status">
              {{ t('common.loading') }}
            </p>
            <p
              v-else-if="error"
              class="address-drawer__status address-drawer__status--error"
              role="alert"
            >
              {{ t('addressDrawer.loadFailed') }}
            </p>
            <template v-else>
              <h3 class="address-drawer__section-title">{{ t('addressDrawer.myAddresses') }}</h3>
              <ul
                v-if="addresses.length"
                class="address-drawer__list"
                role="radiogroup"
                :aria-label="t('addressDrawer.selectAddress')"
              >
                <li v-for="address in addresses" :key="address.public_id">
                  <button
                    class="address-drawer__address"
                    :class="{
                      'address-drawer__address--selected':
                        mode === 'address' && address.public_id === draftAddressId,
                    }"
                    type="button"
                    role="radio"
                    :aria-checked="mode === 'address' && address.public_id === draftAddressId"
                    :aria-label="addressLabel(address)"
                    @click="selectAddress(address.public_id)"
                  >
                    <span
                      class="radio-dot"
                      :class="{
                        'radio-dot--checked':
                          mode === 'address' && address.public_id === draftAddressId,
                      }"
                      aria-hidden="true"
                    ></span>
                    <span class="address-drawer__address-body">
                      <span class="address-drawer__address-name">{{ address.full_name }}</span>
                      <span class="address-drawer__address-line">{{
                        addressLineOne(address)
                      }}</span>
                      <span class="address-drawer__address-line">{{
                        addressLineTwo(address)
                      }}</span>
                    </span>
                  </button>
                </li>
              </ul>
              <p v-else class="address-drawer__status" role="status">
                {{ t('addresses.empty') }}
              </p>
            </template>
          </template>
        </div>

        <div
          v-else
          :id="PICKUP_PANEL_ID"
          class="address-drawer__body address-drawer__body--pickup"
          role="tabpanel"
          :aria-labelledby="`${PICKUP_PANEL_ID}-tab`"
        >
          <div class="address-drawer__pickup-empty">
            <svg class="address-drawer__pickup-icon" viewBox="0 0 64 64" aria-hidden="true">
              <rect x="10" y="18" width="44" height="30" rx="3" fill="#f0f1f2" />
              <path d="M18 18v-5h28v5" fill="none" stroke="#c2c4cc" stroke-width="2" />
              <path d="M26 30h12" stroke="#c2c4cc" stroke-width="2" stroke-linecap="round" />
            </svg>
            <p class="address-drawer__pickup-title">{{ t('addressDrawer.pickupEmpty') }}</p>
            <p class="address-drawer__pickup-hint">{{ t('addressDrawer.pickupHint') }}</p>
          </div>
        </div>

        <!-- Apply is the only commit action: draft -> header + storage + close. -->
        <footer v-if="activeTab === 'delivery'" class="address-drawer__footer">
          <button class="address-drawer__apply" type="button" @click="applySelection">
            {{ t('addressDrawer.apply') }}
          </button>
        </footer>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.visually-hidden {
  position: absolute;
  overflow: hidden;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  border: 0;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.address-drawer {
  position: fixed;
  inset: 0;
  z-index: 1200; /* Above the sticky header (--z-header: 50), like MUI's drawer. */
  display: flex;
  justify-content: flex-end;
}

.address-drawer__backdrop {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 50%);
}

/* Real joybuy: 616px at 1440, full-height white panel from the right edge. */
.address-drawer__panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(38.5rem, 100%);
  height: 100%;
  background: var(--colour-surface);
  box-shadow:
    rgb(0 0 0 / 20%) 0 8px 10px -5px,
    rgb(0 0 0 / 14%) 0 16px 24px 2px,
    rgb(0 0 0 / 12%) 0 6px 30px 5px;
}

/* 24px top inset, 240x40 outlined country select, 20px X 34px from the edge. */
.address-drawer__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  box-sizing: border-box;
  height: 60px; /* real header bar is 60px tall; the 40px select overflows 4px */
  padding: 24px 12px 0 24px;
}

.country-select-wrap {
  position: relative;
  width: 240px;
  max-width: calc(100% - 44px);
}

.country-select {
  display: flex;
  align-items: center;
  gap: 8px;
  box-sizing: border-box;
  width: 100%;
  height: 40px;
  padding: 0 16px;
  border: 1px solid #ccced2;
  border-radius: 4px;
  background: var(--colour-surface);
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  text-align: left;
}

.country-select:hover {
  border-color: #b9bcc4;
}

.country-select:focus-visible {
  outline: 2px solid #1a1a1a;
  outline-offset: 1px;
}

.country-select--open {
  border-color: #1a1a1a;
}

.country-select__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  line-height: 20px;
}

.country-select__chevron {
  flex: 0 0 16px;
  width: 16px;
  height: 16px;
  color: #1a1a1a;
  transition: transform 150ms ease;
}

.country-select__chevron--open {
  transform: rotate(180deg);
}

/* Expanded listbox: 240px wide, flush under the trigger, 250px tall scroll
   box, 8px vertical padding, elevation-8 shadow (real site measurements). */
.country-menu {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 30;
  box-sizing: border-box;
  width: 100%;
  max-height: 250px;
  padding: 8px 0;
  overflow-y: auto;
  border-radius: 4px;
  background: var(--colour-surface);
  box-shadow:
    rgb(0 0 0 / 20%) 0 5px 5px -3px,
    rgb(0 0 0 / 14%) 0 8px 10px 1px,
    rgb(0 0 0 / 12%) 0 3px 14px 2px;
}

.country-menu__option {
  display: flex;
  align-items: center;
  gap: 8px;
  box-sizing: border-box;
  width: 100%;
  height: 44px;
  padding: 0 16px;
  border: 0;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.country-menu__option:hover,
.country-menu__option:focus-visible {
  background: rgb(0 0 0 / 4%);
  outline: none;
}

.country-menu__name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  line-height: 20px;
}

.country-menu__check {
  flex: 0 0 20px;
  width: 20px;
  height: 20px;
  color: #1a1a1a;
}

.country-flag {
  flex: 0 0 24px;
  width: 24px;
  height: 16px;
  border-radius: 2px;
  box-shadow: inset 0 0 0 1px rgb(0 0 0 / 8%);
}

/* Local CSS flags (no CDN): approximate Union Jack + flat tricolours. */
.country-flag--gb {
  background:
    linear-gradient(
      90deg,
      transparent 0 40%,
      #fff 40% 44%,
      #c8102e 44% 56%,
      #fff 56% 60%,
      transparent 60%
    ),
    linear-gradient(
      180deg,
      transparent 0 35%,
      #fff 35% 42%,
      #c8102e 42% 58%,
      #fff 58% 65%,
      transparent 65%
    ),
    linear-gradient(45deg, transparent 46%, #fff 46% 50%, #c8102e 50% 54%, transparent 54%),
    linear-gradient(-45deg, transparent 46%, #fff 46% 50%, #c8102e 50% 54%, transparent 54%),
    #012169;
}

.country-flag--fr {
  background: linear-gradient(90deg, #0055a4 0 33.33%, #fff 33.33% 66.66%, #ef4135 66.66%);
}

.country-flag--de {
  background: linear-gradient(180deg, #000 0 33.33%, #dd0000 33.33% 66.66%, #ffce00 66.66%);
}

.country-flag--be {
  background: linear-gradient(90deg, #000 0 33.33%, #fae042 33.33% 66.66%, #ed2939 66.66%);
}

.country-flag--nl {
  background: linear-gradient(180deg, #ae1c28 0 33.33%, #fff 33.33% 66.66%, #21468b 66.66%);
}

.country-flag--lu {
  background: linear-gradient(180deg, #ed2939 0 33.33%, #fff 33.33% 66.66%, #00a1de 66.66%);
}

.address-drawer__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  margin-top: -10px; /* centre the 20px X on the real site's y=37 */
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
}

.address-drawer__close:hover {
  background: var(--colour-hover);
}

/* Tabs row: 90x44 tabs, 3px black indicator, Manage link at the right. */
.address-drawer__tab-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  margin-top: 16px;
  padding: 0 24px;
}

.address-drawer__tabs {
  display: flex;
  align-self: stretch;
}

.address-drawer__tab {
  position: relative;
  width: 90px;
  height: 44px;
  padding: 12px 16px;
  border: 0;
  background: transparent;
  color: #888b94;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  cursor: pointer;
}

.address-drawer__tab--active {
  color: #1a1a1a;
  font-weight: 700;
}

.address-drawer__tab--active::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: #19191b;
  content: '';
}

.address-drawer__manage {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  line-height: 21px;
  text-decoration: none;
  white-space: nowrap;
}

.address-drawer__manage:hover {
  text-decoration: underline;
}

.address-drawer__divider {
  height: 1px;
  margin-top: 4px;
  background: #f5f6fa;
}

.address-drawer__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow-y: auto;
  padding: 0 24px;
}

/* Location + postcode block, 24px inset, 36px and 40px rows. */
.address-drawer__options {
  flex-shrink: 0;
}

.address-drawer__location {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  color: #c2c4cc;
  font-size: 16px;
  line-height: 24px;
  cursor: default;
}

.address-drawer__postcode-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
}

.address-drawer__postcode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  cursor: pointer;
}

.address-drawer__postcode-label {
  margin-right: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
}

.radio-dot {
  display: inline-block;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: 1px solid #888b94;
  border-radius: 50%;
  background: var(--colour-surface);
}

.radio-dot--checked {
  border-color: #19191b;
  background: #19191b;
  box-shadow: inset 0 0 0 4px var(--colour-surface);
}

.radio-dot--disabled {
  border-color: #d5d7dc;
  background: var(--colour-surface);
}

.address-drawer__postcode-input {
  flex: 1;
  min-width: 0;
  height: 40px;
  padding: 8.5px 14px;
  border: 1px solid #ccced2;
  border-radius: 4px;
  background: var(--colour-surface);
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  line-height: 23px;
}

.address-drawer__postcode-input::placeholder {
  color: #888b94;
}

.address-drawer__postcode-input:focus {
  border-color: #19191b;
  outline: none;
}

.address-drawer__postcode-input--invalid,
.address-drawer__postcode-input--invalid:focus {
  border-color: #cc0c1c;
}

.address-drawer__error {
  margin: 8px 0 0 100px;
  color: #cc0c1c;
  font-size: 14px;
  line-height: 20px;
}

/* Signed-in address list: no cards, generous vertical rhythm, bold names. */
.address-drawer__section-title {
  margin: 16px 0 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
}

.address-drawer__list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.address-drawer__address {
  display: flex;
  gap: 8px;
  width: 100%;
  padding: 16px 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.address-drawer__address--selected .address-drawer__address-name {
  color: #1a1a1a;
}

.address-drawer__address-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.address-drawer__address-name {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
}

.address-drawer__address-line {
  overflow-wrap: anywhere;
  color: #5b6673;
  font-size: 14px;
  line-height: 20px;
}

.address-drawer__status {
  margin: 16px 0 0;
  color: var(--colour-muted);
}

.address-drawer__status--error {
  color: var(--colour-error);
}

/* Signed-out prompt mirrors the real site's centred empty state. */
.address-drawer__signin {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 0 96px;
  text-align: center;
}

.address-drawer__signin-icon {
  width: 120px;
  height: 120px;
}

.address-drawer__signin-text {
  margin: 0;
  color: #c2c4cc;
  font-size: 14px;
  line-height: 18px;
}

.address-drawer__signin-link {
  color: #cc0c1c;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
}

.address-drawer__signin-link:hover {
  text-decoration: underline;
}

.address-drawer__body--pickup {
  align-items: center;
  justify-content: center;
}

.address-drawer__pickup-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 0 96px;
  text-align: center;
}

.address-drawer__pickup-icon {
  width: 64px;
  height: 64px;
}

.address-drawer__pickup-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 700;
}

.address-drawer__pickup-hint {
  margin: 0;
  color: #888b94;
  font-size: 14px;
}

.address-drawer__footer {
  flex-shrink: 0;
  padding: 0 24px 24px;
}

/* Measured real button: 568x40, radius 4, #CC0C1C, white 14px label. */
.address-drawer__apply {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 40px;
  padding: 6px 8px;
  border: 0;
  border-radius: 4px;
  background: linear-gradient(90deg, #cc0c1c, #cc0c1c);
  color: var(--colour-white);
  font: inherit;
  font-size: 14px;
  line-height: 18px;
  cursor: pointer;
}

.address-drawer__apply:hover {
  background: #b00a18;
}

.address-drawer__close:focus-visible,
.address-drawer__tab:focus-visible,
.address-drawer__manage:focus-visible,
.address-drawer__address:focus-visible,
.address-drawer__postcode-input:focus-visible,
.address-drawer__apply:focus-visible,
.address-drawer__signin-link:focus-visible {
  outline: 2px solid var(--colour-focus-ring);
  outline-offset: 2px;
}

/* The red border is the error indicator; avoid stacking the blue focus ring. */
.address-drawer__postcode-input--invalid:focus-visible {
  outline: none;
}

/* Slide-in from the right; backdrop fades (real drawer: 225ms). */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 225ms cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-enter-active .address-drawer__panel,
.drawer-leave-active .address-drawer__panel {
  transition: transform 225ms cubic-bezier(0, 0, 0.2, 1);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .address-drawer__panel,
.drawer-leave-to .address-drawer__panel {
  transform: translateX(100%);
}

/* Real site goes full-screen on mobile; we keep full width below 48rem. */
@media (max-width: 48rem) {
  .address-drawer__panel {
    width: 100%;
  }

  .address-drawer__top {
    padding: 16px 8px 0 16px;
  }

  .address-drawer__tab-row,
  .address-drawer__body {
    padding-inline: 16px;
  }

  .address-drawer__footer {
    padding: 0 16px 16px;
  }

  .address-drawer__error {
    margin-left: 0;
  }
}

@media (max-width: 24.375rem) {
  .address-drawer__postcode-row {
    flex-wrap: wrap;
  }

  .address-drawer__postcode-input {
    flex-basis: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active,
  .drawer-leave-active,
  .drawer-enter-active .address-drawer__panel,
  .drawer-leave-active .address-drawer__panel {
    transition: none;
  }
}
</style>
