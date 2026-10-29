<script setup lang="ts">
import { ref, computed } from 'vue';
import { 
  X, 
  Sparkles, 
  Package, 
  ShoppingCart, 
  CheckCircle2, 
  AlertCircle, 
  PackageCheck,
  ShieldCheck,
  Percent
} from 'lucide-vue-next';
import type { Combo } from '@/types';
import { useCartStore } from '@/stores/cart';

const props = defineProps<{
  combo: Combo | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const cartStore = useCartStore();
const addedSuccess = ref(false);

const precioRegular = computed(() => Number(props.combo?.precio_original || 0));
const precioCombo = computed(() => Number(props.combo?.precio_combo || 0));
const ahorroBs = computed(() => Number(props.combo?.ahorro_monto || 0));
const ahorroPct = computed(() => Number(props.combo?.ahorro_porcentaje || 0));

function handleAddToCart() {
  if (!props.combo || !props.combo.disponible || props.combo.stock_disponible <= 0) return;

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
      emit('close');
    }, 1500);
  }
}
</script>

<template>
  <div 
    v-if="combo"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4 overflow-y-auto"
    role="dialog"
    aria-modal="true"
    @click.self="emit('close')"
  >
    <div class="w-full max-w-3xl bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden my-8 max-h-[90vh] flex flex-col">
      <!-- Encabezado Modal -->
      <div class="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-800/40">
        <div class="flex items-center gap-3">
          <span class="p-2.5 rounded-2xl bg-indigo-100 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400">
            <Package class="w-6 h-6" />
          </span>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-mono px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                {{ combo.sku || 'COMBO-PRO' }}
              </span>
              <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-rose-600 text-white uppercase tracking-wider">
                -{{ ahorroPct }}% OFF
              </span>
            </div>
            <h2 class="text-lg font-black text-slate-900 dark:text-white mt-1">
              {{ combo.nombre }}
            </h2>
          </div>
        </div>

        <button
          @click="emit('close')"
          class="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Cuerpo del Modal -->
      <div class="p-6 space-y-6 overflow-y-auto flex-1">
        <!-- Imagen y Descripción -->
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-6 items-center">
          <div class="sm:col-span-5 h-48 rounded-2xl overflow-hidden bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
            <img
              v-if="combo.imagen_url"
              :src="combo.imagen_url"
              :alt="combo.nombre"
              class="w-full h-full object-cover"
            />
            <div v-else class="w-full h-full flex flex-col items-center justify-center text-slate-300 dark:text-slate-600">
              <Package class="w-12 h-12" />
              <span class="text-xs mt-2">Paquete Promocional</span>
            </div>
          </div>

          <div class="sm:col-span-7 space-y-3">
            <p v-if="combo.descripcion" class="text-sm text-slate-600 dark:text-slate-300">
              {{ combo.descripcion }}
            </p>

            <!-- Indicador de Disponibilidad Conjunta -->
            <div
              class="p-3 rounded-xl border text-xs flex items-center justify-between"
              :class="combo.disponible ? 'bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-900 text-emerald-800 dark:text-emerald-300' : 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300'"
            >
              <div class="flex items-center gap-2">
                <PackageCheck v-if="combo.disponible" class="w-4 h-4 text-emerald-600" />
                <AlertCircle v-else class="w-4 h-4 text-amber-600" />
                <span>
                  <strong>Disponibilidad conjunta:</strong>
                  {{ combo.disponible ? `${combo.stock_disponible} paquetes disponibles para entrega inmediata` : 'Agotado' }}
                </span>
              </div>
            </div>

            <!-- Resumen de Ahorro -->
            <div class="p-3.5 bg-indigo-50 dark:bg-indigo-950/40 rounded-xl border border-indigo-100 dark:border-indigo-900 text-xs space-y-1">
              <div class="flex justify-between text-slate-500 dark:text-slate-400">
                <span>Precio individual sumado:</span>
                <span class="line-through font-semibold">Bs. {{ precioRegular.toFixed(2) }}</span>
              </div>
              <div class="flex justify-between text-indigo-950 dark:text-indigo-200 font-bold text-sm">
                <span>Precio especial del paquete:</span>
                <span class="text-indigo-600 dark:text-indigo-400 text-base">Bs. {{ precioCombo.toFixed(2) }}</span>
              </div>
              <div class="text-emerald-600 dark:text-emerald-400 font-bold pt-1 border-t border-indigo-200/50 dark:border-indigo-900/50 flex justify-between">
                <span>Tu Ahorro:</span>
                <span>Bs. {{ ahorroBs.toFixed(2) }} ({{ ahorroPct }}% de descuento)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Desglose de Existencias Individuales y Componentes (Criterio 1 y 2) -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Desglose de Artículos Incluidos en el Combo
            </h3>
            <span class="text-xs text-slate-400">
              {{ combo.items.length }} artículos empaquetados
            </span>
          </div>

          <div class="space-y-2">
            <div
              v-for="it in combo.items"
              :key="it.variante_id"
              class="flex items-center justify-between p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-800 text-xs"
            >
              <div class="flex items-center gap-3 min-w-0 pr-3">
                <div class="w-10 h-10 rounded-xl bg-white dark:bg-slate-800 overflow-hidden flex-shrink-0 border border-slate-200 dark:border-slate-700 flex items-center justify-center">
                  <img
                    v-if="it.imagen_url"
                    :src="it.imagen_url"
                    :alt="it.nombre_producto"
                    class="w-full h-full object-cover"
                  />
                  <Package v-else class="w-5 h-5 text-slate-400" />
                </div>
                <div class="min-w-0">
                  <div class="font-bold text-slate-900 dark:text-white truncate">
                    {{ it.nombre_producto }}
                  </div>
                  <div class="text-[11px] text-slate-500 font-mono">
                    SKU: {{ it.sku }} | Variante: {{ it.nombre_variante || 'Base' }}
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-4 flex-shrink-0">
                <div class="text-right">
                  <span class="block text-slate-500 text-[11px]">
                    {{ it.cantidad }}x a Bs. {{ Number(it.precio_unitario).toFixed(2) }}
                  </span>
                  <span class="block font-bold text-slate-800 dark:text-slate-200">
                    Bs. {{ Number(it.precio_subtotal).toFixed(2) }}
                  </span>
                </div>

                <!-- Existencia individual de cada ítem (Criterio 1) -->
                <div class="text-right">
                  <span
                    class="inline-block px-2.5 py-1 rounded-full text-[11px] font-bold"
                    :class="it.stock_disponible >= it.cantidad ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300'"
                  >
                    Stock: {{ it.stock_disponible }} disp.
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Pie del Modal con Acción de Compra -->
      <div class="p-6 bg-slate-50 dark:bg-slate-800/40 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <div>
          <span class="text-xs text-slate-400 block">Total del Combo:</span>
          <span class="text-2xl font-black text-slate-900 dark:text-white">
            Bs. {{ precioCombo.toFixed(2) }}
          </span>
        </div>

        <button
          type="button"
          @click="handleAddToCart"
          :disabled="!combo.disponible || combo.stock_disponible <= 0"
          class="py-3 px-6 rounded-2xl font-bold text-sm uppercase tracking-wider flex items-center gap-2 shadow-lg transition-all active:scale-98 disabled:opacity-50 disabled:cursor-not-allowed"
          :class="addedSuccess 
            ? 'bg-emerald-600 text-white' 
            : combo.disponible 
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/30' 
              : 'bg-slate-200 text-slate-500'"
        >
          <CheckCircle2 v-if="addedSuccess" class="w-5 h-5" />
          <ShoppingCart v-else class="w-5 h-5" />
          <span>{{ addedSuccess ? '¡Agregado al Carrito!' : (combo.disponible ? 'Agregar Paquete al Carrito' : 'Agotado') }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
