<script setup>
import CmsBanner from './CmsBanner.vue'
import CmsCampaignGrid from './CmsCampaignGrid.vue'
import CmsHero from './CmsHero.vue'
import CmsLinkGrid from './CmsLinkGrid.vue'
import CmsProductPool from './CmsProductPool.vue'
import CmsRichText from './CmsRichText.vue'
// Renders a CMS page top-to-bottom. Unknown module types and malformed
// payloads degrade to a visible placeholder — a bad floor never breaks the
// page (docs/08 WP-21 acceptance).

const props = defineProps({
  modules: {
    type: Array,
    default: () => [],
  },
})

function typeOf(module) {
  return typeof module?.type === 'string' ? module.type : ''
}

function payloadOf(module) {
  return module && typeof module.payload === 'object' && module.payload !== null
    ? module.payload
    : {}
}
</script>

<template>
  <div class="cms-renderer">
    <template v-for="(module, index) in props.modules" :key="index">
      <CmsHero
        v-if="typeOf(module) === 'hero' && Object.keys(payloadOf(module)).length > 0"
        :payload="payloadOf(module)"
      />
      <CmsCampaignGrid
        v-else-if="typeOf(module) === 'campaign_grid' && Array.isArray(payloadOf(module).items)"
        :payload="payloadOf(module)"
      />
      <CmsBanner
        v-else-if="typeOf(module) === 'banner' && Object.keys(payloadOf(module)).length > 0"
        :payload="payloadOf(module)"
      />
      <CmsProductPool
        v-else-if="typeOf(module) === 'product_pool' && Array.isArray(payloadOf(module).products)"
        :payload="payloadOf(module)"
      />
      <CmsRichText
        v-else-if="typeOf(module) === 'rich_text' && Object.keys(payloadOf(module)).length > 0"
        :payload="payloadOf(module)"
      />
      <CmsLinkGrid
        v-else-if="typeOf(module) === 'link_grid' && Array.isArray(payloadOf(module).items)"
        :payload="payloadOf(module)"
      />
      <section v-else class="cms-unknown" role="status" aria-live="polite">
        <p>Content module "{{ typeOf(module) || 'unknown' }}" is unavailable.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cms-renderer {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.cms-unknown {
  padding: var(--space-5);
  border: 1px dashed var(--colour-border-strong);
  border-radius: var(--radius-lg);
  background: var(--colour-surface-muted);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}
</style>
