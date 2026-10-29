<script setup lang="ts">
import OrderHistoryPanel from '@/components/orders/OrderHistoryPanel.vue';
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="rounded-2xl border border-emerald-950/10 bg-[var(--brand-ink)] px-6 py-7 text-white shadow-lg sm:px-8">
      <p class="text-sm font-semibold text-emerald-100">Control comercial</p>
      <h1 class="display-font mt-1 text-3xl">Ventas, órdenes y comprobantes</h1>
      <p class="mt-2 max-w-2xl text-sm leading-6 text-emerald-50/85">Consulta la trazabilidad de cada venta registrada en Marketplace, POS y canales corporativos.</p>
    </div>
    <OrderHistoryPanel scope="administrador" />
  </div>
</template>
