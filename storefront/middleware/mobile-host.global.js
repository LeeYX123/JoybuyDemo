// ADR 0001: on the "m." host the same routes render the mobile layout.
// Runs globally so every page (including footer/policy pages that pin the
// desktop footer-page layout via definePageMeta) is redirected to the mobile
// shell on m.localhost / m.<domain>.
export default defineNuxtRouteMiddleware((to) => {
  const url = useRequestURL()
  if (url.host.startsWith('m.')) {
    to.meta.layout = 'mobile'
  }
})
