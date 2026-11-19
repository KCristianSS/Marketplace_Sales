<script setup lang="ts">
import { computed } from 'vue';

const TIPO_CAMBIO_OFICIAL = 6.96; // BOB por USD

const props = withDefaults(defineProps<{
  price: number;
  priceUsd?: number;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  layout?: 'stacked' | 'inline' | 'compact';
  bold?: boolean;
  colorClass?: string;
  showExchangeRate?: boolean;
}>(), {
  size: 'md',
  layout: 'inline',
  bold: true,
  colorClass: '',
  showExchangeRate: false
});

const bobFormatted = computed(() => {
  return Number(props.price || 0).toLocaleString('es-BO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
});

const usdCalculated = computed(() => {
  if (props.priceUsd !== undefined && props.priceUsd > 0) {
    return props.priceUsd;
  }
  return Number(props.price || 0) / TIPO_CAMBIO_OFICIAL;
});

const usdFormatted = computed(() => {
  return usdCalculated.value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
});
</script>

<template>
  <div 
    :class="[
      'inline-flex transition-colors',
      layout === 'stacked' ? 'flex-col items-start leading-tight' : 'flex-wrap items-baseline gap-1.5'
    ]"
  >
    <!-- Precio Principal en BOB -->
    <span 
      :class="[
        colorClass || 'text-slate-900 dark:text-white',
        bold ? 'font-black' : 'font-semibold',
        size === 'xs' ? 'text-xs' : '',
        size === 'sm' ? 'text-sm' : '',
        size === 'md' ? 'text-base sm:text-lg' : '',
        size === 'lg' ? 'text-xl sm:text-2xl' : '',
        size === 'xl' ? 'text-2xl sm:text-3xl tracking-tight' : ''
      ]"
    >
      <span class="text-[10px] sm:text-xs font-bold text-slate-500 dark:text-slate-400 mr-0.5 uppercase">BOB</span>
      <span>{{ bobFormatted }}</span>
    </span>

    <!-- Equivalencia en USD (Moneda Dual RF-04 / KAN-299) -->
    <span 
      :class="[
        'inline-flex items-center gap-1 font-semibold text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/80 px-1.5 py-0.5 rounded-md border border-slate-200/70 dark:border-slate-700/60',
        size === 'xs' ? 'text-[9px]' : '',
        size === 'sm' ? 'text-[10px]' : '',
        size === 'md' ? 'text-xs' : '',
        size === 'lg' ? 'text-xs sm:text-sm' : '',
        size === 'xl' ? 'text-sm' : ''
      ]"
      title="Equivalente en Dólares Estadounidenses (T/C 6.96)"
    >
      <span class="text-[9px] font-bold text-blue-600 dark:text-blue-400">$</span>
      <span class="font-mono">{{ usdFormatted }}</span>
      <span class="text-[8px] uppercase tracking-wider text-slate-400">USD</span>
    </span>

    <span v-if="showExchangeRate" class="text-[9px] text-slate-400 block w-full mt-0.5">
      T/C Oficial: 6.96 BOB/USD
    </span>
  </div>
</template>
