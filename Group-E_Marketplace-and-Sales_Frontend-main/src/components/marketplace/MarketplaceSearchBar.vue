<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import type { SugerenciaItem, FacetasCatalogo } from '@/types';
import { Search, X, Sparkles, SlidersHorizontal, RefreshCw, RotateCcw } from 'lucide-vue-next';

const props = defineProps<{
  searchQuery: string;
  suggestions: SugerenciaItem[];
  showSuggestions: boolean;
  sortBy: 'relevancia' | 'precio_asc' | 'precio_desc' | 'nombre';
  isSearching: boolean;
  isSyncingCatalog: boolean;
  activeFiltersCount: number;
  facets: FacetasCatalogo;
  selectedCategoryIds: string[];
  selectedBrands: string[];
  appliedPriceMin: number | null;
  appliedPriceMax: number | null;
  onlyInStock: boolean;
  debouncedQuery: string;
}>();

const emit = defineEmits<{
  (e: 'update:searchQuery', val: string): void;
  (e: 'update:sortBy', val: 'relevancia' | 'precio_asc' | 'precio_desc' | 'nombre'): void;
  (e: 'update:showSuggestions', val: boolean): void;
  (e: 'selectSuggestion', item: SugerenciaItem): void;
  (e: 'clearSearch'): void;
  (e: 'toggleMobileFilters'): void;
  (e: 'refreshCatalog'): void;
  (e: 'toggleCategory', catId: string): void;
  (e: 'toggleBrand', brand: string): void;
  (e: 'clearPriceRange'): void;
  (e: 'toggleStock'): void;
  (e: 'clearAllFilters'): void;
  (e: 'sortChange'): void;
}>();

const searchContainerRef = ref<HTMLElement | null>(null);

function handleClickOutside(event: MouseEvent) {
  if (searchContainerRef.value && !searchContainerRef.value.contains(event.target as Node)) {
    emit('update:showSuggestions', false);
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside);
});

function onInput(e: Event) {
  const target = e.target as HTMLInputElement;
  emit('update:searchQuery', target.value);
}

function onSortChange(e: Event) {
  const target = e.target as HTMLSelectElement;
  emit('update:sortBy', target.value as any);
  emit('sortChange');
}
</script>

<template>
  <section class="bg-white/95 dark:bg-slate-900/95 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm backdrop-blur-md">
    <div class="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
      
      <!-- Input de Búsqueda con Dropdown de Typeahead -->
      <div ref="searchContainerRef" class="relative flex-1 max-w-2xl">
        <div class="relative">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            :value="searchQuery"
            @input="onInput"
            @focus="$emit('update:showSuggestions', suggestions.length > 0)"
            type="text"
            placeholder="Buscar por nombre, SKU, marca o descripción (ej: camara, xps15, logitech)..."
            class="w-full pl-10 pr-10 py-2.5 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-teal-500 focus:border-teal-500 focus:outline-none transition-all placeholder:text-slate-400"
          />
          <button
            v-if="searchQuery"
            type="button"
            @click="$emit('clearSearch')"
            class="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-md"
            title="Limpiar búsqueda"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Menú Flotante de Sugerencias Predictivas (Typeahead) -->
        <transition
          enter-active-class="transition duration-150 ease-out"
          enter-from-class="transform scale-95 opacity-0"
          enter-to-class="transform scale-100 opacity-100"
          leave-active-class="transition duration-100 ease-in"
          leave-from-class="transform scale-100 opacity-100"
          leave-to-class="transform scale-95 opacity-0"
        >
          <div
            v-if="showSuggestions && suggestions.length > 0"
            class="absolute left-0 right-0 top-full mt-1.5 z-40 bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden divide-y divide-slate-100 dark:divide-slate-800"
          >
            <div class="px-3.5 py-2 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <span class="flex items-center gap-1.5">
                <Sparkles class="w-3 h-3 text-amber-500" /> Coincidencias predictivas
              </span>
              <span>{{ suggestions.length }} sugerencias</span>
            </div>
            <ul class="max-h-72 overflow-y-auto">
              <li
                v-for="sug in suggestions"
                :key="sug.id"
                @click="$emit('selectSuggestion', sug)"
                class="p-2.5 hover:bg-teal-50/70 dark:hover:bg-slate-800 cursor-pointer flex items-center gap-3 transition-colors"
              >
                <img
                  v-if="sug.imagen_url"
                  :src="sug.imagen_url"
                  :alt="sug.nombre"
                  class="w-10 h-10 object-cover rounded-lg border border-slate-200 dark:border-slate-700 shrink-0"
                />
                <div class="flex-1 min-w-0">
                  <p class="text-xs font-bold text-slate-800 dark:text-slate-100 truncate">{{ sug.nombre }}</p>
                  <div class="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                    <span class="bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-300 font-semibold px-1.5 py-0.5 rounded">{{ sug.categoria }}</span>
                    <span class="font-mono">SKU: {{ sug.sku }}</span>
                    <span v-if="sug.marca" class="font-medium text-slate-600 dark:text-slate-400">· {{ sug.marca }}</span>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <span class="text-xs font-black text-teal-700 dark:text-teal-400">
                    Bs. {{ Number(sug.precio).toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}
                  </span>
                </div>
              </li>
            </ul>
          </div>
        </transition>
      </div>

      <!-- Controles de Ordenamiento y Botón de Filtros Móvil -->
      <div class="flex items-center gap-2.5">
        <!-- Selector de Ordenamiento -->
        <div class="flex items-center gap-2">
          <span class="text-xs text-slate-500 font-medium hidden sm:inline">Ordenar:</span>
          <select
            :value="sortBy"
            @change="onSortChange"
            class="text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-teal-500"
          >
            <option value="relevancia">Más relevantes</option>
            <option value="precio_asc">Precio: Menor a Mayor</option>
            <option value="precio_desc">Precio: Mayor a Menor</option>
            <option value="nombre">Nombre A - Z</option>
          </select>
        </div>

        <!-- Botón Filtros en Pantallas Chicas -->
        <button
          type="button"
          @click="$emit('toggleMobileFilters')"
          class="lg:hidden inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-950 dark:text-teal-300 border border-teal-200 dark:border-teal-800 text-xs font-bold shadow-sm"
        >
          <SlidersHorizontal class="w-3.5 h-3.5" />
          <span>Filtros</span>
          <span v-if="activeFiltersCount > 0" class="ml-1 px-1.5 py-0.2 rounded-full bg-teal-600 text-white text-[10px]">
            {{ activeFiltersCount }}
          </span>
        </button>

        <!-- Botón de Sincronizar / Refrescar Catálogo -->
        <button
          type="button"
          class="shrink-0 w-9 h-9 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 hover:bg-teal-50 hover:border-teal-300 dark:hover:bg-slate-800 text-slate-500 hover:text-teal-700 flex items-center justify-center transition-all"
          :title="isSyncingCatalog ? 'Sincronizando...' : 'Actualizar catálogo'"
          :disabled="isSyncingCatalog || isSearching"
          @click="$emit('refreshCatalog')"
        >
          <RefreshCw :class="['w-4 h-4', (isSyncingCatalog || isSearching) ? 'animate-spin text-teal-600' : '']" />
        </button>
      </div>
    </div>

    <!-- Barra de Chips de Filtros Activos -->
    <div v-if="activeFiltersCount > 0" class="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center gap-2">
      <span class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Filtros aplicados:</span>
      
      <!-- Chip de Texto -->
      <span
        v-if="debouncedQuery"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-teal-100 dark:bg-teal-950 text-teal-800 dark:text-teal-200 text-xs font-medium"
      >
        Texto: "{{ debouncedQuery }}"
        <button @click="$emit('clearSearch')" class="hover:text-rose-600"><X class="w-3 h-3" /></button>
      </span>

      <!-- Chips de Categorías -->
      <span
        v-for="cid in selectedCategoryIds"
        :key="cid"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-200 text-xs font-medium"
      >
        {{ facets.categorias.find(c => c.id === cid)?.etiqueta || 'Categoría' }}
        <button @click="$emit('toggleCategory', cid)" class="hover:text-rose-600"><X class="w-3 h-3" /></button>
      </span>

      <!-- Chips de Marcas -->
      <span
        v-for="brand in selectedBrands"
        :key="brand"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-purple-100 dark:bg-purple-950 text-purple-800 dark:text-purple-200 text-xs font-medium"
      >
        {{ brand }}
        <button @click="$emit('toggleBrand', brand)" class="hover:text-rose-600"><X class="w-3 h-3" /></button>
      </span>

      <!-- Chip de Precio -->
      <span
        v-if="appliedPriceMin !== null || appliedPriceMax !== null"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-100 dark:bg-amber-950 text-amber-900 dark:text-amber-200 text-xs font-medium"
      >
        Bs. {{ appliedPriceMin || 0 }} - {{ appliedPriceMax ? 'Bs. ' + appliedPriceMax : 'Sin límite' }}
        <button @click="$emit('clearPriceRange')" class="hover:text-rose-600"><X class="w-3 h-3" /></button>
      </span>

      <!-- Chip de Stock -->
      <span
        v-if="onlyInStock"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-200 text-xs font-medium"
      >
        Solo en stock
        <button @click="$emit('toggleStock')" class="hover:text-rose-600"><X class="w-3 h-3" /></button>
      </span>

      <!-- Botón Limpiar Todo -->
      <button
        @click="$emit('clearAllFilters')"
        class="inline-flex items-center gap-1 text-[11px] font-bold text-rose-600 hover:text-rose-700 ml-auto hover:underline"
      >
        <RotateCcw class="w-3 h-3" /> Limpiar todos
      </button>
    </div>
  </section>
</template>
