<script setup lang="ts">
import { ref, computed } from 'vue';
import {
  Package, 
  ShoppingCart, 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  AlertCircle, 
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
    class="group relative flex h-full flex-col overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white shadow-sm transition duration-300 hover:-translate-y-1 hover:border-indigo-300 hover:shadow-2xl hover:shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-800"
  >
    <!-- Ribbon Superior de Oferta y Ahorro -->
    <div class="absolute top-3 left-3 z-10 flex flex-col gap-1.5 items-start">
      <span
        v-if="ahorroPct > 0"
        class="inline-flex flex-col rounded-2xl bg-slate-950/90 px-3 py-2 text-white shadow-lg backdrop-blur-md"
      >
        <span class="text-[10px] font-semibold text-slate-300">Ahorras</span>
        <strong class="text-xl font-black leading-none text-emerald-400">{{ ahorroPct }}%</strong>
      </span>
    </div>

    <!-- Badge de Disponibilidad Conjunta Superior Derecho -->
    <div class="absolute top-3 right-3 z-10">
      <span
        class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold shadow-sm backdrop-blur-md"
        :class="combo.disponible ? 'bg-white/90 text-emerald-700' : 'bg-slate-950/85 text-amber-300'"
      >
        <PackageCheck v-if="combo.disponible" class="w-3.5 h-3.5" />
        <AlertCircle v-else class="w-3.5 h-3.5" />
        {{ combo.disponible ? `${combo.stock_disponible} disponibles` : 'Agotado' }}
      </span>
    </div>

    <!-- Imagen Principal del Combo -->
    <div>
      <div class="relative flex aspect-[16/10] w-full items-center justify-center overflow-hidden bg-slate-100 dark:bg-slate-800/60">
        <img
          v-if="combo.imagen_url"
          :src="combo.imagen_url"
          :alt="combo.nombre"
          class="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          loading="lazy"
        />
        <div v-else class="flex flex-col items-center justify-center text-slate-300 dark:text-slate-600 p-6">
          <Package class="w-12 h-12 stroke-[1.5]" />
          <span class="mt-2 text-xs font-medium">Imagen del paquete</span>
        </div>

        <!-- Indicador de cantidad de productos incluidos -->
        <div class="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-xl bg-white/90 px-2.5 py-1.5 text-xs font-bold text-slate-800 shadow-sm backdrop-blur-md">
          <Package class="h-3.5 w-3.5 text-indigo-600" />
          <span>{{ combo.items.length }} productos</span>
        </div>
      </div>

      <!-- Contenido Principal -->
      <div class="space-y-4 p-5 sm:p-6">
        <div>
          <div class="mb-1 text-[11px] font-semibold text-slate-400">
            {{ combo.sku || 'COMBO-PRO' }}
          </div>
          <h3 class="line-clamp-2 text-lg font-black leading-snug text-slate-900 transition-colors group-hover:text-indigo-600 dark:text-white dark:group-hover:text-indigo-400">
            {{ combo.nombre }}
          </h3>
        </div>

        <p v-if="combo.descripcion" class="line-clamp-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
          {{ combo.descripcion }}
        </p>

        <!-- Precios y Ahorro -->
        <div class="rounded-2xl bg-slate-950 p-4 text-white dark:bg-slate-800">
          <div>
            <div class="flex items-center gap-2">
              <span class="text-2xl font-black text-white">
                Bs. {{ precioCombo.toFixed(2) }}
              </span>
              <span v-if="precioRegular > precioCombo" class="text-xs font-semibold text-slate-400 line-through decoration-slate-500">
                Bs. {{ precioRegular.toFixed(2) }}
              </span>
            </div>
            <span v-if="ahorroBs > 0" class="mt-1 block text-xs font-bold text-emerald-400">
              Ahorro total: Bs. {{ ahorroBs.toFixed(2) }}
            </span>
          </div>
        </div>

        <!-- Botón / Acordeón para Desglose de Componentes (Criterio 1 y 2) -->
        <div class="pt-2">
          <button
            type="button"
            @click="toggleComponents"
            class="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-semibold text-slate-700 transition-colors hover:border-indigo-300 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
          >
            <span>Revisar productos incluidos ({{ combo.items.length }})</span>
            <ChevronUp v-if="isExpandedComponents" class="w-4 h-4" />
            <ChevronDown v-else class="w-4 h-4" />
          </button>

          <!-- Lista Desplegada de Componentes con Stock Individual (Criterio 1) -->
          <div v-if="isExpandedComponents" class="mt-2 space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-700 dark:bg-slate-800/60">
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
    <div class="mt-auto px-5 pb-5 sm:px-6 sm:pb-6">
      <button
        type="button"
        @click="handleAddToCart"
        :disabled="!combo.disponible || combo.stock_disponible <= 0 || isAddingToCart"
        class="flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3.5 text-sm font-bold shadow-md transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        :class="addedSuccess 
          ? 'bg-emerald-600 text-white' 
          : combo.disponible 
            ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/20' 
            : 'bg-slate-200 dark:bg-slate-800 text-slate-500'"
      >
        <CheckCircle2 v-if="addedSuccess" class="w-4 h-4" />
        <ShoppingCart v-else class="w-4 h-4" />
        <span>
          {{ addedSuccess ? 'Combo agregado' : (combo.disponible ? 'Agregar combo al carrito' : 'Combo agotado') }}
        </span>
      </button>
    </div>
  </div>
</template>
