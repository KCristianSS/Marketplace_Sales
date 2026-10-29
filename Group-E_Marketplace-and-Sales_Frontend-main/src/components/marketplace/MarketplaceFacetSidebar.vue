<script setup lang="ts">
import { ref, watch } from 'vue';
import type { FacetasCatalogo } from '@/types';
import { Filter, X, RotateCcw } from 'lucide-vue-next';

const props = defineProps<{
  facets: FacetasCatalogo;
  selectedCategoryIds: string[];
  selectedBrands: string[];
  priceMin: number | null;
  priceMax: number | null;
  onlyInStock: boolean;
  activeFiltersCount: number;
  isMobileOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'toggleCategory', catId: string): void;
  (e: 'toggleBrand', brand: string): void;
  (e: 'applyPriceRange', min: number | null, max: number | null): void;
  (e: 'toggleStock'): void;
  (e: 'resetFilters'): void;
  (e: 'closeMobile'): void;
}>();

const priceMinInput = ref<number | null>(props.priceMin);
const priceMaxInput = ref<number | null>(props.priceMax);

watch(() => [props.priceMin, props.priceMax], ([newMin, newMax]) => {
  priceMinInput.value = newMin;
  priceMaxInput.value = newMax;
});

function handleApplyManualPrice() {
  emit('applyPriceRange', priceMinInput.value, priceMaxInput.value);
}

function handleQuickPrice(min: number | null, max: number | null) {
  priceMinInput.value = min;
  priceMaxInput.value = max;
  emit('applyPriceRange', min, max);
}
</script>

<template>
  <aside
    :class="[
      'bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 space-y-6 shadow-sm sticky top-6',
      isMobileOpen ? 'block fixed inset-x-4 top-20 z-50 max-h-[85vh] overflow-y-auto shadow-2xl border-teal-500' : 'hidden lg:block'
    ]"
  >
    <!-- Encabezado Sidebar Móvil -->
    <div class="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
      <div class="flex items-center gap-2 text-slate-900 dark:text-white font-extrabold text-sm">
        <Filter class="w-4 h-4 text-teal-600" />
        <span>Filtrar Productos</span>
      </div>
      <button
        v-if="isMobileOpen"
        @click="$emit('closeMobile')"
        class="lg:hidden p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg"
        title="Cerrar filtros"
      >
        <X class="w-5 h-5" />
      </button>
    </div>

    <!-- 1. Faceta: Categorías con recuento dinámico -->
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Categorías</h3>
        <span class="text-[10px] text-slate-400 font-semibold">{{ facets.categorias.length }}</span>
      </div>
      <div class="space-y-1.5 max-h-52 overflow-y-auto pr-1">
        <label
          v-for="cat in facets.categorias"
          :key="cat.id"
          class="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 hover:text-teal-700 dark:hover:text-teal-300 cursor-pointer p-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
        >
          <div class="flex items-center gap-2.5 truncate">
            <input
              type="checkbox"
              :checked="selectedCategoryIds.includes(cat.id)"
              @change="$emit('toggleCategory', cat.id)"
              class="rounded border-slate-300 text-teal-600 focus:ring-teal-500 w-4 h-4"
            />
            <span class="truncate" :title="cat.etiqueta">{{ cat.etiqueta }}</span>
          </div>
          <span
            :class="[
              'text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0',
              selectedCategoryIds.includes(cat.id)
                ? 'bg-teal-600 text-white'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
            ]"
          >
            {{ cat.total }}
          </span>
        </label>
      </div>
    </div>

    <!-- 2. Faceta: Marcas con recuento dinámico -->
    <div class="space-y-3 pt-4 border-t border-slate-100 dark:border-slate-800">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Marcas</h3>
        <span class="text-[10px] text-slate-400 font-semibold">{{ facets.marcas.length }}</span>
      </div>
      <div class="space-y-1.5 max-h-48 overflow-y-auto pr-1">
        <label
          v-for="brand in facets.marcas"
          :key="brand.id"
          class="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 hover:text-teal-700 dark:hover:text-teal-300 cursor-pointer p-1.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors"
        >
          <div class="flex items-center gap-2.5 truncate">
            <input
              type="checkbox"
              :checked="selectedBrands.includes(brand.id)"
              @change="$emit('toggleBrand', brand.id)"
              class="rounded border-slate-300 text-teal-600 focus:ring-teal-500 w-4 h-4"
            />
            <span class="truncate">{{ brand.etiqueta }}</span>
          </div>
          <span
            :class="[
              'text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0',
              selectedBrands.includes(brand.id)
                ? 'bg-teal-600 text-white'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-500'
            ]"
          >
            {{ brand.total }}
          </span>
        </label>
      </div>
    </div>

    <!-- 3. Faceta: Rango de Precios en BOB -->
    <div class="space-y-3 pt-4 border-t border-slate-100 dark:border-slate-800">
      <div class="flex items-center justify-between">
        <h3 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Precio (BOB)</h3>
        <span class="text-[10px] text-slate-400 font-mono">
          Bs. {{ facets.precio.min }} - {{ facets.precio.max }}
        </span>
      </div>

      <!-- Píldoras de rango rápido -->
      <div class="grid grid-cols-2 gap-1.5 text-[11px]">
        <button
          type="button"
          @click="handleQuickPrice(null, 1000)"
          class="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-teal-50 hover:border-teal-300 dark:hover:bg-slate-800 font-medium transition-colors"
        >
          &lt; Bs. 1.000
        </button>
        <button
          type="button"
          @click="handleQuickPrice(1000, 3000)"
          class="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-teal-50 hover:border-teal-300 dark:hover:bg-slate-800 font-medium transition-colors"
        >
          1.000 - 3.000
        </button>
        <button
          type="button"
          @click="handleQuickPrice(3000, 8000)"
          class="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-teal-50 hover:border-teal-300 dark:hover:bg-slate-800 font-medium transition-colors"
        >
          3.000 - 8.000
        </button>
        <button
          type="button"
          @click="handleQuickPrice(8000, null)"
          class="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-teal-50 hover:border-teal-300 dark:hover:bg-slate-800 font-medium transition-colors"
        >
          &gt; Bs. 8.000
        </button>
      </div>

      <!-- Inputs manuales Min y Max -->
      <div class="flex items-center gap-2 pt-1">
        <input
          v-model.number="priceMinInput"
          type="number"
          placeholder="Mín"
          class="w-1/2 px-2.5 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-500"
        />
        <span class="text-slate-400 text-xs">-</span>
        <input
          v-model.number="priceMaxInput"
          type="number"
          placeholder="Máx"
          class="w-1/2 px-2.5 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-500"
        />
      </div>
      <button
        type="button"
        @click="handleApplyManualPrice"
        class="w-full py-1.5 bg-slate-900 hover:bg-slate-800 dark:bg-teal-700 dark:hover:bg-teal-600 text-white rounded-lg text-xs font-bold transition-all shadow-sm"
      >
        Aplicar Precio
      </button>
    </div>

    <!-- 4. Faceta: Disponibilidad y Stock -->
    <div class="pt-4 border-t border-slate-100 dark:border-slate-800">
      <label class="flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
        <div class="flex items-center gap-2">
          <input
            type="checkbox"
            :checked="onlyInStock"
            @change="$emit('toggleStock')"
            class="rounded border-slate-300 text-teal-600 focus:ring-teal-500 w-4 h-4"
          />
          <span class="font-medium">Solo en stock inmediato</span>
        </div>
        <span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
          {{ facets.en_stock }}
        </span>
      </label>
    </div>

    <!-- Botón Reset Filtros -->
    <div v-if="activeFiltersCount > 0" class="pt-2">
      <button
        type="button"
        @click="$emit('resetFilters')"
        class="w-full py-2 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
      >
        <RotateCcw class="w-3.5 h-3.5" />
        <span>Restablecer Filtros</span>
      </button>
    </div>
  </aside>
</template>
