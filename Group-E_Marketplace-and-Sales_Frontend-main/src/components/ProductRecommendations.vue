<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { apiClient } from '@/api/client';
import { useCartStore } from '@/stores/cart';
import DualCurrencyPrice from '@/components/DualCurrencyPrice.vue';
import type { 
  RecomendacionesResponse, 
  RecomendacionItem, 
  BundleFrecuente 
} from '@/types';
import {
  Sparkles,
  ShoppingBag,
  Plus,
  Check,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  Tag,
  ArrowRight,
  Layers,
  CheckCircle2,
  PackagePlus,
  Percent,
  HelpCircle,
  ExternalLink
} from 'lucide-vue-next';

const props = defineProps<{
  productId?: string;
  productSku?: string;
  productTitle?: string;
}>();

const cartStore = useCartStore();

const isLoading = ref(false);
const errorMsg = ref('');
const dataRecomendaciones = ref<RecomendacionesResponse | null>(null);

// Filtro de carrusel: 'todos' | 'cross_sell' | 'up_sell'
const activeFilter = ref<'todos' | 'cross_sell' | 'up_sell'>('todos');

// Estado interactivo de checkboxes para "Frecuentemente comprados juntos" (KAN-141)
const bundleSelectedIds = ref<Record<string, boolean>>({});
const isAddingBundle = ref(false);
const bundleSuccessToast = ref(false);

// Referencia al contenedor del carrusel para scroll horizontal
const carouselTrackRef = ref<HTMLElement | null>(null);

async function fetchRecommendations() {
  const targetId = props.productId || props.productSku;
  if (!targetId) return;

  isLoading.value = true;
  errorMsg.value = '';

  try {
    const res = await apiClient.get<RecomendacionesResponse>(`/v1/catalogo/productos/${encodeURIComponent(targetId)}/recomendados`);
    dataRecomendaciones.value = res.data;

    // Inicializar todos los productos del bundle como seleccionados
    if (res.data?.frecuentemente_comprados_juntos?.productos) {
      const initialMap: Record<string, boolean> = {};
      res.data.frecuentemente_comprados_juntos.productos.forEach(p => {
        initialMap[p.id] = true;
      });
      bundleSelectedIds.value = initialMap;
    }
  } catch (err: any) {
    console.error('Error obteniendo recomendaciones:', err);
    errorMsg.value = 'No se pudieron cargar recomendaciones en este momento.';
  } finally {
    isLoading.value = false;
  }
}

// Filtrar lista del carrusel (KAN-140)
const filteredCarouselItems = computed<RecomendacionItem[]>(() => {
  if (!dataRecomendaciones.value) return [];
  const list = dataRecomendaciones.value.recomendaciones || [];
  if (activeFilter.value === 'todos') return list;
  return list.filter(item => item.tipo_recomendacion === activeFilter.value);
});

// Cálculos dinámicos para el Bundle "Frecuentemente Comprados Juntos" (KAN-141)
const bundleItems = computed<RecomendacionItem[]>(() => {
  return dataRecomendaciones.value?.frecuentemente_comprados_juntos?.productos || [];
});

const selectedBundleProducts = computed<RecomendacionItem[]>(() => {
  return bundleItems.value.filter(p => bundleSelectedIds.value[p.id]);
});

const bundleSubtotalIndividual = computed<number>(() => {
  return selectedBundleProducts.value.reduce((acc, curr) => acc + Number(curr.precio), 0);
});

// Ahorro dinámico (8% de descuento al comprar 2 o más ítems juntos)
const bundleAhorro = computed<number>(() => {
  if (selectedBundleProducts.value.length < 2) return 0;
  return Math.round(bundleSubtotalIndividual.value * 0.08 * 100) / 100;
});

const bundleTotalFinal = computed<number>(() => {
  return Math.max(0, bundleSubtotalIndividual.value - bundleAhorro.value);
});

// Scroll suave en carrusel
function scrollCarousel(direction: 'left' | 'right') {
  if (!carouselTrackRef.value) return;
  const offset = direction === 'left' ? -320 : 320;
  carouselTrackRef.value.scrollBy({ left: offset, behavior: 'smooth' });
}

// Agregar producto individual al carrito
function agregarItem(item: RecomendacionItem) {
  cartStore.addItem({
    variante_id: item.variante_id || item.id,
    sku: item.sku,
    nombre: item.nombre,
    cantidad: 1,
    precio_unitario: Number(item.precio)
  });
}

// Agregar todo el paquete "Frecuentemente comprados juntos" de una sola vez (KAN-141)
function agregarBundleCompleto() {
  if (selectedBundleProducts.value.length === 0) return;

  isAddingBundle.value = true;
  selectedBundleProducts.value.forEach(p => {
    cartStore.addItem({
      variante_id: p.variante_id || p.id,
      sku: p.sku,
      nombre: p.nombre,
      cantidad: 1,
      precio_unitario: Number(p.precio)
    });
  });

  bundleSuccessToast.value = true;
  setTimeout(() => {
    bundleSuccessToast.value = false;
    isAddingBundle.value = false;
  }, 2500);
}

watch(() => [props.productId, props.productSku], () => {
  fetchRecommendations();
});

onMounted(() => {
  fetchRecommendations();
});
</script>

<template>
  <div v-if="isLoading" class="py-10 text-center text-xs text-slate-500 flex flex-col items-center justify-center gap-2">
    <Sparkles class="w-6 h-6 text-amber-500 animate-spin" />
    <span>Calculando recomendaciones y complementos con IA y afinidad de catálogo...</span>
  </div>
  <div v-else-if="dataRecomendaciones" class="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800 space-y-8">
    
    <!-- ===================================================================== -->
    <!-- KAN-141: SECCIÓN "FRECUENTEMENTE COMPRADOS JUNTOS" (BUNDLE SUGERIDO) -->
    <!-- ===================================================================== -->
    <section v-if="bundleItems.length >= 2" class="p-5 sm:p-6 bg-slate-50 dark:bg-slate-950/60 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2.5">
          <div class="p-2 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-xl">
            <PackagePlus class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
              <span>Frecuentemente Comprados Juntos</span>
              <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 font-bold border border-emerald-500/30">
                Combo Ahorro 8% OFF
              </span>
            </h3>
            <p class="text-xs text-slate-500 mt-0.5">
              Clientes que compraron este producto también adquirieron estos accesorios para completar su setup.
            </p>
          </div>
        </div>
      </div>

      <!-- Grid Visual de Productos Conectados con '+' -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        <!-- Columna de Productos y Checkboxes (8 cols) -->
        <div class="lg:col-span-8 space-y-4">
          <!-- Tarjetas en Fila -->
          <div class="flex flex-wrap items-center gap-3 sm:gap-4">
            <template v-for="(item, idx) in bundleItems" :key="item.id">
              <!-- Tarjeta de Producto en Bundle -->
              <div 
                :class="[
                  bundleSelectedIds[item.id] 
                    ? 'border-teal-500/60 bg-white dark:bg-slate-900 shadow-md ring-1 ring-teal-500/20' 
                    : 'border-slate-200 dark:border-slate-800 bg-slate-100/60 dark:bg-slate-900/40 opacity-60'
                ]"
                class="flex items-center gap-3 p-3 rounded-xl border transition-all max-w-[260px] flex-1 min-w-[200px]"
              >
                <!-- Miniatura -->
                <div class="w-14 h-14 rounded-lg bg-slate-100 dark:bg-slate-800 overflow-hidden shrink-0 border border-slate-200 dark:border-slate-700">
                  <img :src="item.imagen || 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=200&q=80'" :alt="item.nombre" class="w-full h-full object-cover" />
                </div>
                
                <div class="flex-1 min-w-0">
                  <span class="text-[10px] uppercase font-bold text-teal-600 dark:text-teal-400 block truncate">
                    {{ item.badge || item.categoria }}
                  </span>
                  <p class="text-xs font-bold text-slate-800 dark:text-slate-100 truncate mt-0.5" :title="item.nombre">
                    {{ item.nombre }}
                  </p>
                  <p class="text-xs font-mono font-bold text-slate-900 dark:text-white mt-0.5">
                    BOB {{ Number(item.precio).toFixed(2) }}
                  </p>
                </div>
              </div>

              <!-- Separador '+' entre artículos -->
              <div v-if="idx < bundleItems.length - 1" class="text-slate-400 dark:text-slate-600 shrink-0">
                <Plus class="w-5 h-5" />
              </div>
            </template>
          </div>

          <!-- Lista de Checkboxes Interactivos -->
          <div class="space-y-2 pt-2 border-t border-slate-200 dark:border-slate-800 text-xs">
            <label 
              v-for="item in bundleItems" 
              :key="'chk-' + item.id"
              class="flex items-center gap-2.5 cursor-pointer text-slate-700 dark:text-slate-300 font-medium hover:text-teal-600 transition-colors"
            >
              <input 
                type="checkbox" 
                v-model="bundleSelectedIds[item.id]" 
                class="w-4 h-4 rounded text-teal-600 focus:ring-teal-500 border-slate-300 dark:border-slate-700 cursor-pointer"
              />
              <span class="truncate">
                <strong v-if="item.tipo_recomendacion === 'base'">Este artículo:</strong>
                {{ item.nombre }} — <span class="font-mono font-bold text-slate-900 dark:text-white">BOB {{ Number(item.precio).toFixed(2) }}</span>
              </span>
            </label>
          </div>
        </div>

        <!-- Columna de Resumen de Precio y Botón de Adición (4 cols) -->
        <div class="lg:col-span-4 p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex flex-col justify-between space-y-3.5 shadow-sm">
          <div>
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 block">
              Precio del Set Seleccionado ({{ selectedBundleProducts.length }} ítems)
            </span>
            
            <div class="mt-1 flex items-baseline gap-2">
              <span class="text-xl sm:text-2xl font-black text-teal-700 dark:text-teal-400">
                BOB {{ bundleTotalFinal.toFixed(2) }}
              </span>
              <span v-if="bundleAhorro > 0" class="text-xs line-through text-slate-400 font-mono">
                BOB {{ bundleSubtotalIndividual.toFixed(2) }}
              </span>
            </div>

            <div v-if="bundleAhorro > 0" class="mt-1 text-[11px] text-emerald-700 dark:text-emerald-400 font-bold flex items-center gap-1">
              <Percent class="w-3.5 h-3.5" />
              <span>Ahorras BOB {{ bundleAhorro.toFixed(2) }} comprando juntos</span>
            </div>
          </div>

          <button
            type="button"
            :disabled="selectedBundleProducts.length === 0 || isAddingBundle"
            @click="agregarBundleCompleto"
            class="w-full py-2.5 px-4 bg-teal-700 hover:bg-teal-800 disabled:opacity-50 text-white rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-md shadow-teal-900/20 active:scale-[0.98] transition-all"
          >
            <ShoppingBag class="w-4 h-4" />
            <span>{{ isAddingBundle ? 'Agregando paquete...' : `Agregar los ${selectedBundleProducts.length} productos al carrito` }}</span>
          </button>

          <p v-if="bundleSuccessToast" class="text-center text-xs font-bold text-emerald-600 dark:text-emerald-400 animate-pulse flex items-center justify-center gap-1">
            <CheckCircle2 class="w-4 h-4" /> ¡Paquete añadido al carrito con éxito!
          </p>
        </div>
      </div>
    </section>

    <!-- ===================================================================== -->
    <!-- KAN-140: CARRUSEL INTERACTIVO DE RECOMENDACIONES (CROSS & UP-SELL)     -->
    <!-- ===================================================================== -->
    <section class="space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <div class="p-1.5 bg-teal-50 dark:bg-teal-950/60 text-teal-600 dark:text-teal-400 rounded-lg">
              <Sparkles class="w-4 h-4" />
            </div>
            <h3 class="text-base font-extrabold text-slate-900 dark:text-white">
              Recomendaciones para ti
            </h3>
            <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold">
              RF-19 · Cross/Up-sell
            </span>
          </div>
          <p class="text-xs text-slate-500 mt-0.5">
            Artículos complementarios y alternativas de mayor gama calculados por reglas de afinidad.
          </p>
        </div>

        <!-- Filtros y Flechas de Navegación -->
        <div class="flex items-center gap-3">
          <!-- Filtro de Categoría de Recomendación -->
          <div class="inline-flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5 text-xs font-semibold">
            <button
              type="button"
              @click="activeFilter = 'todos'"
              :class="activeFilter === 'todos' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-white'"
              class="px-2.5 py-1 rounded-md transition-all text-[11px]"
            >
              Todos ({{ dataRecomendaciones.recomendaciones.length }})
            </button>
            <button
              type="button"
              @click="activeFilter = 'cross_sell'"
              :class="activeFilter === 'cross_sell' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-white'"
              class="px-2.5 py-1 rounded-md transition-all text-[11px]"
            >
              Accesorios Afines
            </button>
            <button
              type="button"
              @click="activeFilter = 'up_sell'"
              :class="activeFilter === 'up_sell' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-800 dark:hover:text-white'"
              class="px-2.5 py-1 rounded-md transition-all text-[11px]"
            >
              Gama Superior (Up-sell)
            </button>
          </div>

          <!-- Botones de Carrusel -->
          <div class="flex items-center gap-1">
            <button
              type="button"
              @click="scrollCarousel('left')"
              class="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 shadow-sm"
              title="Anterior"
            >
              <ChevronLeft class="w-4 h-4" />
            </button>
            <button
              type="button"
              @click="scrollCarousel('right')"
              class="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 shadow-sm"
              title="Siguiente"
            >
              <ChevronRight class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <!-- Pista Desplazable del Carrusel (KAN-140) -->
      <div
        ref="carouselTrackRef"
        class="flex gap-4 overflow-x-auto pb-4 pt-1 snap-x snap-mandatory scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-700"
      >
        <div
          v-for="item in filteredCarouselItems"
          :key="item.id"
          class="snap-start shrink-0 w-64 sm:w-72 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all flex flex-col justify-between"
        >
          <!-- Imagen y Badges -->
          <div class="relative h-44 bg-slate-100 dark:bg-slate-950 overflow-hidden group">
            <img 
              :src="item.imagen || 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=400&q=80'" 
              :alt="item.nombre" 
              class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />

            <!-- Badge de Tipo de Recomendación -->
            <span
              :class="[
                item.tipo_recomendacion === 'up_sell' 
                  ? 'bg-indigo-600 text-white' 
                  : 'bg-teal-700 text-white'
              ]"
              class="absolute top-2.5 left-2.5 text-[10px] font-bold px-2 py-0.5 rounded-md shadow-sm"
            >
              {{ item.badge || (item.tipo_recomendacion === 'up_sell' ? 'Gama Superior' : 'Accesorio Afín') }}
            </span>

            <!-- Score de Afinidad -->
            <span class="absolute top-2.5 right-2.5 bg-black/70 text-white text-[10px] font-mono font-bold px-1.5 py-0.5 rounded backdrop-blur-sm">
              {{ Math.round(item.score_afinidad * 100) }}% match
            </span>
          </div>

          <!-- Contenido y Motivo -->
          <div class="p-3.5 flex-1 flex flex-col justify-between space-y-3">
            <div>
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {{ item.categoria }}
              </span>
              <h4 class="text-xs font-bold text-slate-900 dark:text-white line-clamp-2 mt-0.5" :title="item.nombre">
                {{ item.nombre }}
              </h4>
              <p class="text-[11px] text-slate-500 line-clamp-2 mt-1.5 italic bg-slate-50 dark:bg-slate-800/60 p-2 rounded-lg border border-slate-100 dark:border-slate-800">
                "{{ item.motivo }}"
              </p>
            </div>

            <!-- Precios y Botón de Compra -->
            <div class="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <DualCurrencyPrice :price="Number(item.precio)" size="sm" layout="stacked" />
              </div>

              <button
                type="button"
                @click="agregarItem(item)"
                class="p-2 bg-teal-700 hover:bg-teal-800 active:scale-95 text-white rounded-lg shadow-sm transition-all"
                title="Añadir accesorio al carrito"
              >
                <ShoppingBag class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <div v-if="filteredCarouselItems.length === 0" class="w-full py-8 text-center text-xs text-slate-400">
          No hay recomendaciones en este filtro específico.
        </div>
      </div>
    </section>

  </div>
</template>
