<script setup>
import { useStaffAuth } from '@/composables/useStaffAuth'

const { staff, permissions } = useStaffAuth()
</script>

<template>
  <section aria-labelledby="dash-title">
    <h1 id="dash-title">仪表盘</h1>
    <p>已登录：{{ staff?.display_name }}。已授权权限：{{ permissions.size }} 项。</p>
  </section>
</template>
