<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { PackageCheck, PackageX, PackageMinus, Loader2 } from 'lucide-vue-next';
import { consultarStock } from '@/api/catalogo';

/**
 * RF-07 [FE]: Badge reactivo de disponibilidad de stock para tarjetas de
 * catálogo y detalle de producto. Consulta el endpoint de disponibilidad
 * (respaldado por caché Redis de 30s sobre RIO-INV-01) y se refresca sola
 * cada `refrescarCadaMs` para reflejar cambios sin recargar la página.
 */
const props = withDefaults(defineProps<{
  sku: string;
  sucursalId?: string;
  refrescarCadaMs?: number;
}>(), {
  refrescarCadaMs: 30000,
});

const cargando = ref(true);
const stock = ref<number | null>(null);
const error = ref(false);
let intervalId: ReturnType<typeof setInterval> | undefined;

async function cargarStock() {
  try {
    const data = await consultarStock(props.sku, props.sucursalId);
    stock.value = data.stock_disponible;
    error.value = false;
  } catch (err) {
    error.value = true;
  } finally {
    cargando.value = false;
  }
}

onMounted(() => {
  cargarStock();
  if (props.refrescarCadaMs > 0) {
    intervalId = setInterval(cargarStock, props.refrescarCadaMs);
  }
});

watch(() => props.sku, () => {
  cargando.value = true;
  cargarStock();
});

defineExpose({ cargarStock });
</script>

<template>
  <span
    v-if="cargando"
    class="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400"
  >
    <Loader2 class="w-3 h-3 animate-spin" /> Consultando stock…
  </span>

  <span
    v-else-if="error"
    class="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400"
  >
    Stock no disponible
  </span>

  <span
    v-else-if="(stock ?? 0) <= 0"
    class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400"
  >
    <PackageX class="w-3 h-3" /> Agotado
  </span>

  <span
    v-else-if="(stock ?? 0) < 5"
    class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400"
    :title="`${stock} unidades disponibles`"
  >
    <PackageMinus class="w-3 h-3" /> Pocas unidades ({{ stock }})
  </span>

  <span
    v-else
    class="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400"
    :title="`${stock} unidades disponibles`"
  >
    <PackageCheck class="w-3 h-3" /> En stock
  </span>
</template>
