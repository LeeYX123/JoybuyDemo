import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileApplyShop from '../components/mobile/MobileApplyShop.vue'
import { messages } from '../locales/messages'

// m. host 申请开店（申请开店页面/申请开店-手机版.html、待审核-手机版.html）：
// 字段顺序、label、状态回显与编辑事件回传（页面持有业务状态）。
const form = {
  logoPreview: '',
  userName: '',
  shopName: '',
  phone: '',
  referrerCode: '',
  idDocumentType: 'ID_CARD',
  docPreview: '',
  residentialAddress: '',
}

const idDocumentTypes = [
  { value: 'ID_CARD', label: 'ID card' },
  { value: 'PASSPORT', label: 'Passport' },
  { value: 'DRIVER_LICENSE', label: 'Driver license' },
]

function mountApply(extraProps = {}) {
  return mount(MobileApplyShop, {
    props: {
      signedIn: true,
      showForm: true,
      status: '',
      application: null,
      form: { ...form },
      submitting: false,
      formError: '',
      fieldErrors: {},
      logoUploading: false,
      logoUploadError: '',
      docUploading: false,
      docUploadError: '',
      idDocumentTypes,
      documentTypeLabel: 'ID card',
      statusLabel: '',
      merchantPendingDeposit: false,
      ...extraProps,
    },
  })
}

const labelTexts = (wrapper, selector) =>
  wrapper.findAll(selector).map((node) => node.text().replace(/\s+/g, ' ').trim())

describe('MobileApplyShop form', () => {
  it('renders the seven fields in the design order', () => {
    const wrapper = mountApply()
    expect(labelTexts(wrapper, '.m-apply__label')).toEqual([
      'Shop logo*',
      'Your name*',
      'Shop name*',
      'Phone number*',
      'Referral code (optional)',
      'Identity document*',
      'Document photo*',
      'Residential address*',
    ])
  })

  it('associates every label with its control', () => {
    const wrapper = mountApply()
    for (const id of [
      'm-apply-user-name',
      'm-apply-shop-name',
      'm-apply-phone',
      'm-apply-referrer',
      'm-apply-address',
    ]) {
      const input = wrapper.find(`#${id}`)
      expect(input.exists()).toBe(true)
      expect(wrapper.find(`label[for="${id}"]`).exists()).toBe(true)
    }
    // 文件选择：label[for] 包裹 input（键盘可聚焦 + 点击整块触发）。
    for (const id of ['m-apply-logo', 'm-apply-doc']) {
      expect(wrapper.find(`label[for="${id}"] input#${id}`).exists()).toBe(true)
    }
  })

  it('forwards text edits as `field` events', async () => {
    const wrapper = mountApply()
    await wrapper.find('#m-apply-shop-name').setValue('Star Electronics')
    expect(wrapper.emitted('field')?.at(-1)).toEqual(['shopName', 'Star Electronics'])
    await wrapper.find('#m-apply-address').setValue('12 Baker Street')
    expect(wrapper.emitted('field')?.at(-1)).toEqual(['residentialAddress', '12 Baker Street'])
  })

  it('forwards the document type radio choice', async () => {
    const wrapper = mountApply()
    const radios = wrapper.findAll('input[name="m-apply-id-document-type"]')
    expect(radios).toHaveLength(3)
    await radios[1].setValue()
    expect(wrapper.emitted('field')?.at(-1)).toEqual(['idDocumentType', 'PASSPORT'])
  })

  it('renders inline errors with role=alert and aria-required fields', () => {
    const wrapper = mountApply({ fieldErrors: { shopName: 'This field is required.' } })
    const alert = wrapper.find('.m-apply__error[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('This field is required.')
    expect(wrapper.find('#m-apply-shop-name').attributes('aria-required')).toBe('true')
  })

  it('shows the upload hint and a live upload state', () => {
    const wrapper = mountApply({ logoUploading: true })
    expect(wrapper.find('#m-apply-logo-hint').text()).toContain('JPG')
    expect(wrapper.find('.m-apply__upload').text()).toContain('Uploading')
  })
})

describe('MobileApplyShop pending state', () => {
  const application = {
    user_name: '王小明',
    shop_name: '星光电子',
    phone: '+447700900123',
    referrer_code: '8452',
    id_document_type: 'ID_CARD',
    residential_address: '12 Baker Street, London',
    logo_image_url: '/media/shop/logo.png',
    id_document_image_url: '/media/shop/doc.png',
    submitted_at: '2026-11-25T14:09:00Z',
  }

  it('lists the review banner and the design row order', () => {
    const wrapper = mountApply({
      showForm: false,
      status: 'PENDING',
      application,
      statusLabel: 'Under review',
    })
    expect(wrapper.find('.m-apply__status[role="status"]').text()).toContain('Under review')
    expect(labelTexts(wrapper, '.shop-details__label')).toEqual([
      'Shop logo*',
      'Your name*',
      'Shop name*',
      'Phone number*',
      'Identity document*',
      'Residential address*',
      'Referral code (optional)',
      'Submitted at',
    ])
    const values = labelTexts(wrapper, '.shop-details__value')
    expect(values[2]).toBe('星光电子')
    expect(values[6]).toBe('8452')
    expect(values[7]).toBe('2026-11-25 14:09')
  })

  it('renders the logo and document thumbnails', () => {
    const wrapper = mountApply({ showForm: false, status: 'PENDING', application })
    const images = wrapper
      .findAll('.shop-details__thumb')
      .filter((node) => node.element.tagName === 'IMG')
    expect(images).toHaveLength(2)
  })

  it('shows the deposit note for an approved application awaiting deposit', () => {
    const wrapper = mountApply({
      showForm: false,
      status: 'APPROVED',
      application,
      statusLabel: 'Approved',
      merchantPendingDeposit: true,
    })
    expect(wrapper.text()).toContain('security deposit')
    // 2026-11-28：通过态不再有「进入商家中心」主 CTA，只保留通过说明 +
    // 指向页头右上角【切换商家端】的提示。
    expect(wrapper.find('.m-apply__submit').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Merchant Center')
    expect(wrapper.text()).toContain('Switch to Seller console')
  })

  it('offers re-apply after a rejection', async () => {
    const wrapper = mountApply({
      showForm: false,
      status: 'REJECTED',
      application: { ...application, reject_reason: 'Blurry document photo' },
      statusLabel: 'Not approved',
    })
    expect(wrapper.find('.m-apply__status[role="alert"]').text()).toContain('Blurry document photo')
    await wrapper.find('.m-apply__submit').trigger('click')
    expect(wrapper.emitted('reapply')).toHaveLength(1)
  })
})

// 五语言键集合一致（至少 shopApply.* 命名空间内完全一致，避免某语言漏键
// 回退到英文或直接显示 key）。
describe('shopApply i18n keys', () => {
  const keysOf = (locale) =>
    Object.keys(messages[locale])
      .filter((key) => key.startsWith('shopApply.'))
      .sort()

  it('has the same shopApply keys in all five locales', () => {
    const base = keysOf('en')
    expect(base.length).toBeGreaterThan(0)
    for (const locale of ['zh', 'de', 'fr', 'nl']) {
      expect(keysOf(locale)).toEqual(base)
    }
  })

  it('keeps a label for every form field plus the upload action', () => {
    for (const locale of ['en', 'zh', 'de', 'fr', 'nl']) {
      for (const key of [
        'shopApply.shopLogo',
        'shopApply.userName',
        'shopApply.shopName',
        'shopApply.phone',
        'shopApply.referrerCode',
        'shopApply.idDocument',
        'shopApply.idDocumentsGroup',
        'shopApply.idDocumentImage',
        'shopApply.residentialAddress',
        'shopApply.chooseImage',
      ]) {
        expect(messages[locale][key]).toBeTruthy()
      }
    }
  })
})
