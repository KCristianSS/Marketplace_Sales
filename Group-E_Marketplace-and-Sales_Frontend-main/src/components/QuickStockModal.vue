<script setup lang="ts">
import { ref, nextTick, watch } from 'vue';
import { Search, X, MapPin, Loader2, PackageSearch, Zap } from 'lucide-vue-next';
import { buscarStockMultisucursal, type ProductoStockResumen } from '@/api/catalogo';

/**
 * Consulta Rápida de Stock Multi-Sucursal (atajo global F3).
 * Permite a un cajero/administrador buscar un producto por SKU o nombre y
 * ver de inmediato el desglose de unidades disponibles por sucursal, sin
 * salir de la pantalla en la que se encuentra (POS, catálogo, etc.).
 */
const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ 
  (e: 'close'): void;
  (e: 'select', sku: string): void;
}>();

function seleccionarParaPos(sku: string) {
  emit('select', sku);
  cerrar();
}

const query = ref('');
const buscando = ref(false);
const resultados = ref<ProductoStockResumen[]>([]);
const buscoAlMenosUnaVez = ref(false);
const inputRef = ref<HTMLInputElement | null>(null);
let debounceId: ReturnType<typeof setTimeout> | undefined;

function nivelIndicador(stock: number): 'ok' | 'bajo' | 'agotado' {
  if (stock <= 0) return 'agotado';
  if (stock < 5) return 'bajo';
  return 'ok';
}

async function ejecutarBusqueda() {
  if (!query.value.trim()) {
    resultados.value = [];
    return;
  }
  buscando.value = true;
  try {
    const data = await buscarStockMultisucursal(query.value.trim());
    resultados.value = data.resultados;
  } catch (err) {
    resultados.value = [];
  } finally {
    buscando.value = false;
    buscoAlMenosUnaVez.value = true;
  }
}

function onInput() {
  clearTimeout(debounceId);
  debounceId = setTimeout(ejecutarBusqueda, 300);
}

function cerrar() {
  query.value = '';
  resultados.value = [];
  buscoAlMenosUnaVez.value = false;
  emit('close');
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      await nextTick();
      inputRef.value?.focus();
    }
  }
);
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center p-4 pt-[10vh]"
    @keydown.esc="cerrar"
  >
    <div class="bg-white dark:bg-slate-900 w-full max-w-2xl rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
      <!-- Encabezado -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-800">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <PackageSearch class="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 class="text-sm font-bold text-slate-800 dark:text-white">Consulta Rápida de Stock</h3>
            <p class="text-[11px] text-slate-400">Disponibilidad por sucursal en tiempo real</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono font-bold text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded border border-slate-200 dark:border-slate-700">
            <Zap class="w-3 h-3" /> F3
          </span>
          <button @click="cerrar" class="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-white rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
            <X class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- Input de búsqueda -->
      <div class="p-4 border-b border-slate-100 dark:border-slate-800">
        <div class="relative">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            ref="inputRef"
            v-model="query"
            @input="onInput"
            @keydown.enter="ejecutarBusqueda"
            type="text"
            placeholder="Buscar por SKU o nombre de producto..."
            class="w-full pl-10 pr-4 py-2.5 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-600 focus:outline-none"
          />
        </div>
      </div>

      <!-- Resultados -->
      <div class="max-h-[50vh] overflow-y-auto p-4 space-y-4">
        <div v-if="buscando" class="flex items-center justify-center gap-2 text-slate-400 text-sm py-8">
          <Loader2 class="w-4 h-4 animate-spin" /> Buscando disponibilidad...
        </div>

        <div v-else-if="buscoAlMenosUnaVez && resultados.length === 0" class="text-center text-slate-400 text-sm py-8">
          No se encontraron productos que coincidan con "{{ query }}".
        </div>

        <div v-else-if="!buscoAlMenosUnaVez" class="text-center text-slate-400 text-sm py-8">
          Escribe un SKU o nombre de producto para ver su disponibilidad por sucursal.
        </div>

        <div
          v-for="prod in resultados"
          :key="prod.sku"
          class="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden"
        >
          <div class="flex items-center justify-between px-4 py-2.5 bg-slate-50 dark:bg-slate-800/60">
            <div>
              <p class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ prod.nombre }}</p>
              <p class="text-[11px] font-mono text-slate-400">SKU: {{ prod.sku }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-bold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 px-2.5 py-1 rounded-lg">
                {{ prod.stock_total }} unid. totales
              </span>
              <button 
                type="button"
                @click="seleccionarParaPos(prod.sku)"
                class="px-2.5 py-1 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm transition-all active:scale-95"
              >
                + Cargar al POS
              </button>
            </div>
          </div>
          <table class="w-full text-left text-xs">
            <thead class="text-slate-500 dark:text-slate-400">
              <tr>
                <th class="px-4 py-1.5 font-medium">Sucursal</th>
                <th class="px-4 py-1.5 font-medium text-right">Disponible</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="suc in prod.sucursales" :key="suc.sucursal_id">
                <td class="px-4 py-2 flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                  <MapPin class="w-3.5 h-3.5 text-slate-400" /> {{ suc.sucursal_nombre }}
                </td>
                <td class="px-4 py-2 text-right">
                  <span
                    class="inline-flex items-center gap-1.5 font-bold"
                    :class="{
                      'text-emerald-600 dark:text-emerald-400': nivelIndicador(suc.stock_disponible) === 'ok',
                      'text-amber-600 dark:text-amber-400': nivelIndicador(suc.stock_disponible) === 'bajo',
                      'text-rose-600 dark:text-rose-400': nivelIndicador(suc.stock_disponible) === 'agotado',
                    }"
                  >
                    <span
                      class="w-2 h-2 rounded-full"
                      :class="{
                        'bg-emerald-500': nivelIndicador(suc.stock_disponible) === 'ok',
                        'bg-amber-500': nivelIndicador(suc.stock_disponible) === 'bajo',
                        'bg-rose-500': nivelIndicador(suc.stock_disponible) === 'agotado',
                      }"
                    ></span>
                    {{ suc.stock_disponible }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
