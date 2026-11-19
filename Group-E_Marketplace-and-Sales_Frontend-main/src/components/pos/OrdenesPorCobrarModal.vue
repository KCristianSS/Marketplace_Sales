<script setup lang="ts">
import { ref, watch } from 'vue';
import { ClipboardList, Loader2, RefreshCw, X } from 'lucide-vue-next';
import { obtenerHistorialOrdenes } from '@/api/ordenes';
import PanelPagosOrden from '@/components/orders/PanelPagosOrden.vue';
import { bs } from '@/lib/imprimir';
import type { OrdenHistorial } from '@/types';

/** KAN-54 — Cobro en el POS de órdenes pendientes: pagos divididos, estados y reintento. */
const props = defineProps<{ open: boolean; ordenInicialId?: string | null }>();
const emit = defineEmits<{ (e: 'close'): void; (e: 'cambio'): void }>();

const ordenes = ref<OrdenHistorial[]>([]);
const cargando = ref(false);
const error = ref('');
const seleccionada = ref<string | null>(null);
const pagina = ref(1);
const totalPaginas = ref(1);
const totalOrdenes = ref(0);

async function cargar() {
  cargando.value = true;
  error.value = '';
  try {
    const r = await obtenerHistorialOrdenes({ estado: 'pendiente', page: pagina.value, limit: 30 });
    ordenes.value = r.items;
    totalPaginas.value = Math.max(1, r.total_paginas);
    totalOrdenes.value = r.total;
    if (!seleccionada.value && r.items.length) seleccionada.value = r.items[0].id;
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudieron cargar las órdenes pendientes.';
  } finally {
    cargando.value = false;
  }
}

watch(() => props.open, (abierto) => { if (abierto) { pagina.value = 1; seleccionada.value = props.ordenInicialId ?? null; cargar(); } });

function cambiarPagina(nueva: number) {
  if (nueva < 1 || nueva > totalPaginas.value) return;
  pagina.value = nueva;
  seleccionada.value = null;
  cargar();
}

function pagosActualizados(resumen: { estado_orden: string }) {
  emit('cambio');
  if (resumen.estado_orden !== 'pendiente') cargar();
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm" data-testid="modal-por-cobrar">
    <div class="w-full max-w-4xl max-h-[92vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl flex flex-col">
      <div class="px-6 py-4 bg-gradient-to-r from-emerald-700 to-teal-800 text-white flex items-center justify-between shrink-0">
        <div class="flex items-center gap-3"><ClipboardList class="w-5 h-5" /><div><h3 class="text-base font-bold">Órdenes por cobrar</h3><p class="text-xs text-emerald-100">Registra y valida los pagos (incluye pagos divididos)</p></div></div>
        <div class="flex items-center gap-1">
          <button type="button" class="p-1.5 rounded-lg hover:bg-white/10" title="Actualizar" @click="cargar"><RefreshCw class="w-4 h-4" :class="{ 'animate-spin': cargando }" /></button>
          <button type="button" class="p-1.5 rounded-lg hover:bg-white/10" title="Cerrar" @click="emit('close')"><X class="w-5 h-5" /></button>
        </div>
      </div>
      <div class="grid md:grid-cols-[260px_1fr] overflow-hidden min-h-0 flex-1">
        <aside class="border-r border-slate-200 dark:border-slate-800 overflow-y-auto p-3 space-y-2">
          <div v-if="cargando" class="py-6 text-center text-xs text-slate-400 flex items-center justify-center gap-2"><Loader2 class="w-4 h-4 animate-spin" /> Cargando…</div>
          <p v-else-if="error" class="text-xs text-red-600">{{ error }}</p>
          <p v-else-if="!ordenes.length" class="py-6 text-center text-xs text-slate-400">No hay órdenes pendientes de pago.</p>
          <button v-for="o in ordenes" :key="o.id" type="button" class="w-full text-left p-3 rounded-xl border text-xs transition-colors"
            :class="seleccionada === o.id ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'" @click="seleccionada = o.id">
            <span class="block font-mono font-bold text-emerald-800 dark:text-emerald-300">{{ o.codigo_orden }}</span>
            <span class="block mt-0.5 text-slate-500">{{ o.items?.length || 0 }} ítem(s) · <b class="font-mono">{{ bs(o.total) }}</b></span>
          </button>
          <div v-if="totalOrdenes > 0" class="flex items-center justify-between gap-2 pt-2 text-xs text-slate-500">
            <button type="button" :disabled="pagina <= 1 || cargando" class="rounded px-2 py-1 disabled:opacity-40" @click="cambiarPagina(pagina - 1)">Anterior</button>
            <span>{{ pagina }} / {{ totalPaginas }} · {{ totalOrdenes }}</span>
            <button type="button" :disabled="pagina >= totalPaginas || cargando" class="rounded px-2 py-1 disabled:opacity-40" @click="cambiarPagina(pagina + 1)">Siguiente</button>
          </div>
        </aside>
        <main class="overflow-y-auto p-4">
          <PanelPagosOrden v-if="seleccionada" :key="seleccionada" :orden-id="seleccionada" puede-registrar mostrar-simulacion @actualizado="pagosActualizados" />
          <p v-else class="py-10 text-center text-sm text-slate-400">Selecciona una orden para cobrarla.</p>
        </main>
      </div>
    </div>
  </div>
</template>
