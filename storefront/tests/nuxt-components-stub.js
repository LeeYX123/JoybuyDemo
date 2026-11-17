// Vitest stand-in for Nuxt's virtual #components module. Only NuxtLink is used
// by the account components (to render the seller entry as a real link), so a
// minimal anchor component is enough for component tests.
import { defineComponent, h } from 'vue'

export const NuxtLink = defineComponent({
  name: 'NuxtLink',
  props: {
    to: { type: [String, Object], default: '' },
  },
  setup(props, { slots }) {
    return () => h('a', { href: typeof props.to === 'string' ? props.to : '' }, slots.default?.())
  },
})

export default { NuxtLink }
