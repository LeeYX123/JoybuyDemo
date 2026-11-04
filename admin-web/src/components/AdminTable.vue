<script setup>
// Generic admin list table: columns describe fields, rows come from the
// parent view; actions render through the #actions slot per row.
const props = defineProps({
  columns: {
    type: Array,
    required: true, // [{ key, label, width? }]
  },
  rows: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyText: {
    type: String,
    default: '暂无记录。',
  },
})
</script>

<template>
  <div class="admin-table-wrap">
    <table class="admin-table">
      <thead>
        <tr>
          <th
            v-for="column in props.columns"
            :key="column.key"
            :style="column.width ? { width: column.width } : {}"
          >
            {{ column.label }}
          </th>
          <th v-if="$slots.actions">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in props.rows" :key="index">
          <td v-for="column in props.columns" :key="column.key">
            {{ row[column.key] ?? '—' }}
          </td>
          <td v-if="$slots.actions" class="admin-table__actions">
            <slot name="actions" :row="row" />
          </td>
        </tr>
        <tr v-if="props.rows.length === 0 && !props.loading">
          <td :colspan="props.columns.length + ($slots.actions ? 1 : 0)" class="admin-table__empty">
            {{ props.emptyText }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.admin-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.admin-table th,
.admin-table td {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--colour-border);
  white-space: nowrap;
  max-width: 24rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

.admin-table th {
  color: var(--colour-muted);
  font-weight: var(--font-weight-semibold);
  background: var(--colour-surface);
}

.admin-table__empty {
  text-align: center;
  color: var(--colour-muted);
  padding-block: var(--space-6);
}

.admin-table__actions :deep(button) {
  margin-right: var(--space-2);
}
</style>
