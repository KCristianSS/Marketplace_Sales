<script setup lang="ts">
import OrderHistoryPanel from '@/components/orders/OrderHistoryPanel.vue';
import ReturnRequestsPanel from '@/components/orders/ReturnRequestsPanel.vue';
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="flex justify-end">
      <router-link to="/admin/reembolsos" class="rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950/30">Gestionar reembolsos</router-link>
    </div>
    <OrderHistoryPanel scope="administrador" />
    <ReturnRequestsPanel scope="administrador" />
  </div>
</template>
