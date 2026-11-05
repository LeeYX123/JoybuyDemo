import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import CategoryTreePicker from './CategoryTreePicker.vue'

const TREE = [
  {
    source_id: 'minihome:UK-Mini-HP-Electronics',
    name: 'Electronics',
    name_zh: '电子产品',
    children: [
      {
        source_id: 'l2:1405',
        name: 'Kettles & Toasters',
        name_zh: '热水壶 & 烤面包机',
        children: [],
      },
      { source_id: 'l2:1421', name: 'Phones', name_zh: '手机', children: [] },
    ],
  },
  {
    source_id: 'minihome:UK-Mini-HP-Pets',
    name: 'Pets',
    name_zh: '',
    children: [],
  },
]

// v-model 宿主：真实地把子组件 emit 写回 prop，模拟父页面行为。
function Harness(props = {}) {
  return defineComponent({
    components: { CategoryTreePicker },
    setup() {
      const selection = ref(props.initial || [])
      return { selection, TREE }
    },
    template: '<CategoryTreePicker v-model="selection" :categories="TREE" />',
  })
}

describe('CategoryTreePicker', () => {
  it('renders channels and expands children', async () => {
    const wrapper = mount(Harness())
    expect(wrapper.text()).toContain('Electronics')
    expect(wrapper.text()).toContain('Pets')
    expect(wrapper.text()).not.toContain('Kettles & Toasters')

    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('展开'))
      .trigger('click')
    expect(wrapper.text()).toContain('Kettles & Toasters')
    expect(wrapper.text()).toContain('l2:1405')
  })

  it('shows the Chinese name together with the English name', async () => {
    const wrapper = mount(Harness())
    expect(wrapper.text()).toContain('电子产品')
    expect(wrapper.text()).toContain('Electronics')
    // 没有中文名的类目只显示英文名，不留空占位。
    expect(wrapper.find('.tree-picker__name-en').exists()).toBe(true)
  })

  it('selects and deselects a node through v-model', async () => {
    const wrapper = mount(Harness())
    const firstCheckbox = wrapper.findAll('input[type="checkbox"]')[0]

    await firstCheckbox.setValue(true)
    expect(wrapper.vm.selection).toEqual([
      {
        source_id: 'minihome:UK-Mini-HP-Electronics',
        name: 'Electronics',
        name_zh: '电子产品',
        include_descendants: true,
      },
    ])

    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false)
    expect(wrapper.vm.selection).toEqual([])
  })

  it('toggles include_descendants on a selected child', async () => {
    const wrapper = mount(
      Harness({
        initial: [
          {
            source_id: 'l2:1405',
            name: 'Kettles & Toasters',
            name_zh: '热水壶 & 烤面包机',
            include_descendants: true,
          },
        ],
      }),
    )
    // 子类目行默认折叠，先展开 Electronics 频道再找切换按钮。
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('展开'))
      .trigger('click')
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('含子类目'))
      .trigger('click')
    expect(wrapper.vm.selection).toEqual([
      {
        source_id: 'l2:1405',
        name: 'Kettles & Toasters',
        name_zh: '热水壶 & 烤面包机',
        include_descendants: false,
      },
    ])
    expect(wrapper.text()).toContain('仅当前类目')
  })

  it('filters by keyword and auto-shows matching children', async () => {
    const wrapper = mount(Harness())
    await wrapper.find('input[type="search"]').setValue('kettles')
    expect(wrapper.text()).toContain('Electronics')
    expect(wrapper.text()).toContain('Kettles & Toasters')
    expect(wrapper.text()).not.toContain('Pets')
  })

  it('filters by Chinese keyword', async () => {
    const wrapper = mount(Harness())
    await wrapper.find('input[type="search"]').setValue('烤面包')
    expect(wrapper.text()).toContain('热水壶 & 烤面包机')
    expect(wrapper.text()).not.toContain('Pets')
  })
})
