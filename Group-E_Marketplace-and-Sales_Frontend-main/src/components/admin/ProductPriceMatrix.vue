<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { AlertCircle, CheckCircle2, Loader2, Save } from 'lucide-vue-next';
import {
  asignarPrecioItem,
  crearListaPrecio,
  eliminarPrecioItem,
  obtenerListasPrecios,
  obtenerPreciosProducto
} from '@/api/catalogo';
import type { ListaPrecio, PrecioItem, Producto } from '@/types';

type Canal = ListaPrecio['canal'];
type TipoCliente = ListaPrecio['tipo_cliente'];

const props = defineProps<{ product: Producto }>();
const emit = defineEmits<{ (event: 'saved'): void }>();

const CANALES: Array<{ id: Canal; label: string }> = [
  { id: 'web', label: 'Web' },
  { id: 'pos', label: 'POS' },
  { id: 'b2b', label: 'B2B' }
];
const SUCURSALES = [
  { id: '', nombre: 'General (todas las sucursales)' },
  { id: 'SUC-LP-CENTRAL', nombre: 'Sucursal Central - La Paz' },
  { id: 'SUC-LP-SOPOCACHI', nombre: 'Sucursal Sopocachi - La Paz' },
  { id: 'SUC-SCZ-EQUIPETROL', nombre: 'Sucursal Equipetrol - Santa Cruz' },
  { id: 'SUC-CBB-CENTRO', nombre: 'Sucursal Centro - Cochabamba' }
];

const tipoCliente = ref<TipoCliente>('retail');
const lists = ref<ListaPrecio[]>([]);
const items = ref<PrecioItem[]>([]);
const draft = ref<Record<string, string>>({});
const isLoading = ref(true);
const isSaving = ref(false);
const errorMessage = ref('');
const successMessage = ref('');

const basePrice = computed(() => Number(props.product.precio || 0));
const productKeys = computed(() => new Set([
  props.product.id,
  ...(props.product.variantes || []).map(variant => variant.id)
]));

function cellKey(canal: Canal, sucursalId: string, tipo: TipoCliente = tipoCliente.value) {
  return `${tipo}|${canal}|${sucursalId}`;
}

function listFor(canal: Canal, sucursalId: string, tipo: TipoCliente = tipoCliente.value) {
  const matches = lists.value.filter(list =>
    list.canal === canal && list.tipo_cliente === tipo && (list.sucursal_id || '') === sucursalId
  );
  return matches.find(list => list.activo) || matches[0];
}

function itemFor(canal: Canal, sucursalId: string, tipo: TipoCliente = tipoCliente.value) {
  const list = listFor(canal, sucursalId, tipo);
  if (!list) return undefined;
  return items.value.find(item => item.lista_precio_id === list.id && productKeys.value.has(item.variante_id));
}

function savedValue(canal: Canal, sucursalId: string, tipo: TipoCliente = tipoCliente.value) {
  const item = itemFor(canal, sucursalId, tipo);
  return item ? String(Number(item.precio)) : '';
}

function inheritedPrice(canal: Canal, sucursalId: string): number {
  if (sucursalId) {
    const general = itemFor(canal, '');
    if (general) return Number(general.precio);
  }
  if (tipoCliente.value === 'corporativo_b2b') {
    const retail = itemFor(canal, sucursalId, 'retail') || itemFor(canal, '', 'retail');
    return retail ? Number(retail.precio) : Math.round(basePrice.value * 0.9 * 100) / 100;
  }
  return basePrice.value;
}

function resetDraft() {
  const values: Record<string, string> = {};
  for (const tipo of ['retail', 'corporativo_b2b'] as TipoCliente[]) {
    for (const sucursal of SUCURSALES) {
      for (const canal of CANALES) {
        values[cellKey(canal.id, sucursal.id, tipo)] = savedValue(canal.id, sucursal.id, tipo);
      }
    }
  }
  draft.value = values;
}

const changedKeys = computed(() => Object.keys(draft.value).filter(key => {
  const [tipo, canal, sucursal] = key.split('|') as [TipoCliente, Canal, string];
  return draft.value[key].trim() !== savedValue(canal, sucursal, tipo);
}));

const invalidKeys = computed(() => changedKeys.value.filter(key => {
  const value = draft.value[key].trim();
  return value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0);
}));

async function load() {
  isLoading.value = true;
  errorMessage.value = '';
  try {
    const [allLists, productItems] = await Promise.all([
      obtenerListasPrecios(),
      obtenerPreciosProducto(props.product.id)
    ]);
    lists.value = allLists;
    items.value = productItems;
    resetDraft();
  } catch (error: any) {
    errorMessage.value = error.response?.data?.detail || 'No se pudieron cargar las tarifas del producto.';
  } finally {
    isLoading.value = false;
  }
}

async function ensureList(canal: Canal, sucursalId: string, tipo: TipoCliente): Promise<ListaPrecio> {
  const existing = listFor(canal, sucursalId, tipo);
  if (existing) return existing;
  const sucursal = SUCURSALES.find(branch => branch.id === sucursalId);
  const canalLabel = CANALES.find(option => option.id === canal)?.label || canal;
  const tipoLabel = tipo === 'corporativo_b2b' ? 'Corporativo' : 'Retail';
  const created = await crearListaPrecio({
    nombre: `${canalLabel} ${tipoLabel} · ${sucursalId ? sucursal?.nombre : 'General'}`,
    canal,
    tipo_cliente: tipo,
    sucursal_id: sucursalId || null,
    moneda: 'BOB',
    activo: true
  });
  lists.value.push(created);
  return created;
}

async function save() {
  if (invalidKeys.value.length) {
    errorMessage.value = 'Los precios deben ser números mayores o iguales a 0.';
    return;
  }
  isSaving.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    for (const key of changedKeys.value) {
      const [tipo, canal, sucursal] = key.split('|') as [TipoCliente, Canal, string];
      const value = draft.value[key].trim();
      const current = itemFor(canal, sucursal, tipo);
      if (value === '') {
        if (current) await eliminarPrecioItem(current.lista_precio_id, current.id);
        continue;
      }
      const list = await ensureList(canal, sucursal, tipo);
      await asignarPrecioItem(list.id, { variante_id: props.product.id, precio: Number(value) });
    }
    const saved = changedKeys.value.length;
    await load();
    successMessage.value = `${saved} tarifa(s) guardada(s).`;
    emit('saved');
  } catch (error: any) {
    errorMessage.value = error.response?.data?.detail || 'No se pudieron guardar las tarifas.';
  } finally {
    isSaving.value = false;
  }
}

watch(() => props.product.id, load);
onMounted(load);
</script>

<template>
  <div class="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50/40 p-4 dark:border-emerald-900 dark:bg-emerald-950/10">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h3 class="text-xs font-bold text-slate-900 dark:text-white">Precios diferenciados · {{ product.nombre }}</h3>
        <p class="mt-0.5 text-[11px] text-slate-500">
          Precio base BOB {{ basePrice.toFixed(2) }}. Deja una celda vacía para heredar el precio indicado.
        </p>
      </div>
      <div class="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-semibold dark:border-slate-700 dark:bg-slate-900" role="group" aria-label="Tipo de cliente">
        <button
          v-for="option in [{ id: 'retail', label: 'Retail' }, { id: 'corporativo_b2b', label: 'Corporativo B2B' }]"
          :key="option.id"
          type="button"
          :aria-pressed="tipoCliente === option.id"
          :class="['rounded-md px-3 py-1.5', tipoCliente === option.id ? 'bg-emerald-700 text-white' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800']"
          @click="tipoCliente = option.id as TipoCliente"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="flex items-center gap-2 rounded-md bg-rose-50 p-2.5 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
      <AlertCircle class="h-4 w-4 shrink-0" /> {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="flex items-center gap-2 rounded-md bg-emerald-100 p-2.5 text-xs text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
      <CheckCircle2 class="h-4 w-4 shrink-0" /> {{ successMessage }}
    </p>

    <div v-if="isLoading" class="flex items-center gap-2 py-6 text-xs text-slate-500">
      <Loader2 class="h-4 w-4 animate-spin" /> Cargando tarifas...
    </div>
    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[620px] text-left text-xs">
        <thead class="text-slate-500">
          <tr>
            <th class="py-2 pr-3 font-semibold">Sucursal</th>
            <th v-for="canal in CANALES" :key="canal.id" class="px-2 py-2 font-semibold">{{ canal.label }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-emerald-100 dark:divide-slate-800">
          <tr v-for="sucursal in SUCURSALES" :key="sucursal.id">
            <th class="py-2 pr-3 font-medium text-slate-700 dark:text-slate-200">{{ sucursal.nombre }}</th>
            <td v-for="canal in CANALES" :key="canal.id" class="px-2 py-1.5">
              <label class="sr-only" :for="`precio-${product.id}-${cellKey(canal.id, sucursal.id)}`">
                Precio {{ canal.label }} en {{ sucursal.nombre }}
              </label>
              <div class="flex items-center gap-1">
                <span class="text-slate-400">BOB</span>
                <input
                  :id="`precio-${product.id}-${cellKey(canal.id, sucursal.id)}`"
                  :value="draft[cellKey(canal.id, sucursal.id)]"
                  type="number"
                  min="0"
                  step="0.01"
                  @input="draft[cellKey(canal.id, sucursal.id)] = ($event.target as HTMLInputElement).value"
                  :placeholder="inheritedPrice(canal.id, sucursal.id).toFixed(2)"
                  :class="[
                    'w-28 rounded-md border bg-white px-2 py-1.5 font-semibold outline-none focus:ring-2 focus:ring-emerald-500/30 dark:bg-slate-800',
                    changedKeys.includes(cellKey(canal.id, sucursal.id)) ? 'border-amber-400' : 'border-slate-300 dark:border-slate-700'
                  ]"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="flex items-center justify-end gap-2">
      <button
        type="button"
        :disabled="!changedKeys.length || isSaving"
        class="rounded-md px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-white disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800"
        @click="resetDraft"
      >
        Descartar
      </button>
      <button
        type="button"
        :disabled="!changedKeys.length || isSaving"
        class="inline-flex items-center gap-1.5 rounded-md bg-emerald-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-800 disabled:opacity-40"
        @click="save"
      >
        <Loader2 v-if="isSaving" class="h-3.5 w-3.5 animate-spin" />
        <Save v-else class="h-3.5 w-3.5" />
        Guardar {{ changedKeys.length || '' }} cambio(s)
      </button>
    </div>
  </div>
</template>
