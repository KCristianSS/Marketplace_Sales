<script setup lang="ts">
import { ref, computed } from 'vue';
import { 
  Sparkles, 
  Package, 
  ShoppingCart, 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  AlertCircle, 
  Info,
  PackageCheck
} from 'lucide-vue-next';
import type { Combo } from '@/types';
import { useCartStore } from '@/stores/cart';

const props = defineProps<{
  combo: Combo;
}>();

const emit = defineEmits<{
  (e: 'ver-detalle', combo: Combo): void;
}>();

const cartStore = useCartStore();
const isExpandedComponents = ref(false);
const isAddingToCart = ref(false);
const addedSuccess = ref(false);

const precioRegular = computed(() => Number(props.combo.precio_original || 0));
const precioCombo = computed(() => Number(props.combo.precio_combo || 0));
const ahorroBs = computed(() => Number(props.combo.ahorro_monto || 0));
const ahorroPct = computed(() => Number(props.combo.ahorro_porcentaje || 0));

function toggleComponents(e: Event) {
  e.stopPropagation();
  isExpandedComponents.value = !isExpandedComponents.value;
}

function handleAddToCart(e: Event) {
  e.stopPropagation();
  if (!props.combo.disponible || props.combo.stock_disponible <= 0) return;

  isAddingToCart.value = true;
  try {
    const success = cartStore.addItem({
      variante_id: `combo-${props.combo.id}`,
      sku: props.combo.sku || `CMB-${props.combo.id.slice(0, 8).toUpperCase()}`,
      nombre: `[COMBO] ${props.combo.nombre}`,
      cantidad: 1,
      precio_unitario: precioCombo.value,
      stock_disponible: props.combo.stock_disponible,
    });

    if (success) {
      addedSuccess.value = true;
      setTimeout(() => {
        addedSuccess.value = false;
      }, 2500);
    }
  } finally {
    isAddingToCart.value = false;
  }
}
</script>

<template>
  <div 
    @click="emit('ver-detalle', combo)"
    class="group relative bg-white dark:bg-slate-900 rounded-3xl border border-slate-200/90 dark:border-slate-800 shadow-sm hover:shadow-xl hover:border-indigo-500/40 transition-all duration-300 flex flex-col justify-between overflow-hidden cursor-pointer"
  >
    <!-- Ribbon Superior de Oferta y Ahorro -->
    <div class="absolute top-3 left-3 z-10 flex flex-col gap-1.5 items-start">
      <span 
        v-if="ahorroPct > 0"
        class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-rose-600 text-white text-[11px] font-black uppercase tracking-wider shadow-md shadow-rose-600/30"
      >
        <Sparkles class="w-3 h-3" />
        -{{ ahorroPct }}% OFF
      </span>

      <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-indigo-600 text-white text-[10px] font-bold uppercase tracking-wider shadow-xs">
        Pack Comercial
      </span>
    </div>

    <!-- Badge de Disponibilidad Conjunta Superior Derecho -->
    <div class="absolute top-3 right-3 z-10">
      <span
        class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold backdrop-blur-md shadow-xs"
        :class="combo.disponible ? 'bg-emerald-500/90 text-white' : 'bg-slate-800/80 text-amber-300'"
      >
        <PackageCheck v-if="combo.disponible" class="w-3.5 h-3.5" />
        <AlertCircle v-else class="w-3.5 h-3.5" />
        {{ combo.disponible ? `${combo.stock_disponible} packs listos` : 'Agotado' }}
      </span>
    </div>

    <!-- Imagen Principal del Combo -->
    <div>
      <div class="relative w-full aspect-16/10 bg-slate-100 dark:bg-slate-800/60 overflow-hidden flex items-center justify-center">
        <img
          v-if="combo.imagen_url"
          :src="combo.imagen_url"
          :alt="combo.nombre"
          class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          loading="lazy"
        />
        <div v-else class="flex flex-col items-center justify-center text-slate-300 dark:text-slate-600 p-6">
          <Package class="w-12 h-12 stroke-[1.5]" />
          <span class="text-xs mt-2 font-medium">Paquete Comercial</span>
        </div>

        <!-- Indicador de cantidad de productos incluidos -->
        <div class="absolute bottom-3 left-3 bg-slate-950/70 backdrop-blur-sm text-white px-2.5 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5">
          <Package class="w-3.5 h-3.5 text-indigo-400" />
          <span>{{ combo.items.length }} productos incluidos</span>
        </div>
      </div>

      <!-- Contenido Principal -->
      <div class="p-5 space-y-3">
        <div>
          <div class="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-1">
            {{ combo.sku || 'COMBO-PRO' }}
          </div>
          <h3 class="text-base font-bold text-slate-900 dark:text-white leading-snug group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors line-clamp-2">
            {{ combo.nombre }}
          </h3>
        </div>

        <p v-if="combo.descripcion" class="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
          {{ combo.descripcion }}
        </p>

        <!-- Precios y Ahorro -->
        <div class="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-baseline justify-between">
          <div>
            <div class="flex items-center gap-2">
              <span class="text-xl font-black text-slate-900 dark:text-white">
                Bs. {{ precioCombo.toFixed(2) }}
              </span>
              <span v-if="precioRegular > precioCombo" class="text-xs font-semibold text-slate-400 line-through">
                Bs. {{ precioRegular.toFixed(2) }}
              </span>
            </div>
            <span v-if="ahorroBs > 0" class="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 block mt-0.5">
              ¡Ahorras Bs. {{ ahorroBs.toFixed(2) }} comprando el pack!
            </span>
          </div>
        </div>

        <!-- Botón / Acordeón para Desglose de Componentes (Criterio 1 y 2) -->
        <div class="pt-2">
          <button
            type="button"
            @click="toggleComponents"
            class="w-full flex items-center justify-between text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 bg-indigo-50/60 dark:bg-indigo-950/40 p-2.5 rounded-xl transition-colors"
          >
            <span>Ver detalle de productos incluidos ({{ combo.items.length }})</span>
            <ChevronUp v-if="isExpandedComponents" class="w-4 h-4" />
            <ChevronDown v-else class="w-4 h-4" />
          </button>

          <!-- Lista Desplegada de Componentes con Stock Individual (Criterio 1) -->
          <div v-if="isExpandedComponents" class="mt-2 space-y-1.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs animate-in fade-in duration-200">
            <div
              v-for="it in combo.items"
              :key="it.variante_id"
              class="flex items-center justify-between gap-2 py-1 border-b border-slate-200/50 dark:border-slate-700/50 last:border-0"
            >
              <div class="flex items-center gap-2 truncate">
                <span class="font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/60 px-1.5 py-0.5 rounded text-[10px]">
                  {{ it.cantidad }}x
                </span>
                <span class="truncate text-slate-800 dark:text-slate-200 font-medium" :title="it.nombre_producto">
                  {{ it.nombre_producto }}
                </span>
              </div>
              <div class="flex items-center gap-2 flex-shrink-0">
                <span
                  class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  :class="it.stock_disponible >= it.cantidad ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'"
                >
                  Stock: {{ it.stock_disponible }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Acciones Inferiores -->
    <div class="p-5 pt-0">
      <button
        type="button"
        @click="handleAddToCart"
        :disabled="!combo.disponible || combo.stock_disponible <= 0 || isAddingToCart"
        class="w-full py-3 px-4 rounded-xl font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 transition-all shadow-md active:scale-98 disabled:opacity-50 disabled:cursor-not-allowed"
        :class="addedSuccess 
          ? 'bg-emerald-600 text-white' 
          : combo.disponible 
            ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/20' 
            : 'bg-slate-200 dark:bg-slate-800 text-slate-500'"
      >
        <CheckCircle2 v-if="addedSuccess" class="w-4 h-4" />
        <ShoppingCart v-else class="w-4 h-4" />
        <span>
          {{ addedSuccess ? '¡Combo en el Carrito!' : (combo.disponible ? 'Comprar Combo' : 'Combo Agotado') }}
        </span>
      </button>
    </div>
  </div>
</template>
