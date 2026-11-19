<script setup lang="ts">
import { useNotificationMessage } from '@/lib/feedback';
import { computed, onMounted, reactive, ref } from 'vue';
import { ChevronLeft, ChevronRight, Mail, RefreshCw, RotateCcw, Search } from 'lucide-vue-next';
import { obtenerBitacoraNotificaciones, reenviarNotificacion, type EstadoNotificacion, type NotificacionLog } from '@/api/notificaciones';

const PAGE_SIZE = 15;
const filters = reactive({ estado: '' as EstadoNotificacion | '', correo: '', orden_id: '' });
const rows = ref<NotificacionLog[]>([]);
const loading = ref(false);
const error = ref('');
const notice = useNotificationMessage<string>('success', '');
const page = ref(1);
const total = ref(0);
const pages = ref(1);
const resendingId = ref('');
const rangeLabel = computed(() => total.value ? `${(page.value - 1) * PAGE_SIZE + 1}–${Math.min(page.value * PAGE_SIZE, total.value)} de ${total.value}` : '0 resultados');

async function load() {
  loading.value = true;
  error.value = '';
  notice.value = '';
  try {
    const result = await obtenerBitacoraNotificaciones({
      estado: filters.estado,
      correo: filters.correo.trim() || undefined,
      orden_id: filters.orden_id.trim() || undefined,
      page: page.value,
      limit: PAGE_SIZE
    });
    rows.value = result.items;
    total.value = result.total;
    pages.value = result.total_paginas;
    page.value = result.pagina;
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo cargar la bitácora de notificaciones.';
    rows.value = [];
    total.value = 0;
  } finally { loading.value = false; }
}

function applyFilters() { page.value = 1; void load(); }
function clearFilters() { filters.estado = ''; filters.correo = ''; filters.orden_id = ''; applyFilters(); }

async function resend(row: NotificacionLog) {
  resendingId.value = row.id;
  error.value = '';
  notice.value = '';
  try {
    await reenviarNotificacion(row.id);
    await load();
    notice.value = `Se programó el reenvío a ${row.correo_destino}.`;
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo programar el reenvío.';
  } finally { resendingId.value = ''; }
}

function labelStatus(value: EstadoNotificacion) {
  return ({ pendiente: 'Pendiente', procesando: 'En proceso', enviada: 'Enviada', fallida: 'Fallida' } as Record<EstadoNotificacion, string>)[value];
}
function statusClass(value: EstadoNotificacion) {
  return ({
    pendiente: 'bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
    procesando: 'bg-blue-50 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
    enviada: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300',
    fallida: 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300'
  } as Record<EstadoNotificacion, string>)[value];
}
function formatDate(value?: string | null) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}
function shortOrderId(value: string) { return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value; }

onMounted(() => void load());
</script>

<template>
  <section class="space-y-5">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-6">
      <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div class="flex items-start gap-3"><span class="rounded-xl bg-blue-50 p-2.5 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300"><Mail class="h-5 w-5" /></span><div><h2 class="text-lg font-extrabold text-slate-900 dark:text-white">Bitácora de notificaciones</h2><p class="mt-1 text-sm text-slate-500">Correos de actualización de pedidos, reintentos y estado de entrega.</p></div></div>
        <button type="button" :disabled="loading" class="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="load"><RefreshCw :class="['h-3.5 w-3.5', { 'animate-spin': loading }]" /> Actualizar</button>
      </div>
      <form class="mt-5 grid gap-3 border-t border-slate-100 pt-4 dark:border-slate-800 md:grid-cols-4" @submit.prevent="applyFilters">
        <label class="relative md:col-span-2"><span class="sr-only">Correo destino</span><Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input v-model="filters.correo" type="search" class="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="Buscar por correo" /></label>
        <label><span class="sr-only">ID de la orden</span><input v-model="filters.orden_id" type="search" class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="ID de orden" /></label>
        <label><span class="sr-only">Estado de notificación</span><select v-model="filters.estado" class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"><option value="">Todos los estados</option><option value="pendiente">Pendiente</option><option value="procesando">En proceso</option><option value="enviada">Enviada</option><option value="fallida">Fallida</option></select></label>
        <div class="flex gap-2 md:col-span-4"><button type="submit" :disabled="loading" class="rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-blue-800 disabled:opacity-50">Aplicar filtros</button><button type="button" class="rounded-lg px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" @click="clearFilters">Limpiar</button></div>
      </form>
    </div>

    <p v-if="error" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200">{{ error }}</p>


    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex items-center justify-between border-b border-slate-100 px-5 py-3 text-xs text-slate-500 dark:border-slate-800"><span>{{ rangeLabel }}</span><span v-if="pages > 1">Página {{ page }} de {{ pages }}</span></div>
      <div v-if="loading" class="space-y-3 p-5"><div v-for="i in 4" :key="i" class="h-12 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" /></div>
      <div v-else-if="!rows.length" class="p-10 text-center text-sm text-slate-500">No hay notificaciones que coincidan con los filtros.</div>
      <div v-else class="overflow-x-auto"><table class="min-w-full text-left text-sm"><thead class="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800/70"><tr><th class="px-4 py-3 font-semibold">Pedido / estado</th><th class="px-4 py-3 font-semibold">Destinatario</th><th class="px-4 py-3 font-semibold">Notificación</th><th class="px-4 py-3 font-semibold">Estado del envío</th><th class="px-4 py-3 font-semibold">Intentos / fecha</th><th class="px-4 py-3"><span class="sr-only">Acciones</span></th></tr></thead><tbody class="divide-y divide-slate-100 dark:divide-slate-800"><tr v-for="row in rows" :key="row.id" class="align-top"><td class="px-4 py-4"><p class="font-mono text-xs font-bold text-slate-700 dark:text-slate-200" :title="row.orden_id">{{ shortOrderId(row.orden_id) }}</p><p class="mt-1 text-xs capitalize text-slate-500">Pedido {{ row.estado_orden.replaceAll('_', ' ') }}</p></td><td class="px-4 py-4 text-xs text-slate-600 dark:text-slate-300">{{ row.correo_destino }}</td><td class="max-w-sm px-4 py-4"><p class="text-xs font-semibold text-slate-800 dark:text-slate-100">{{ row.asunto }}</p><p v-if="row.ultimo_error" class="mt-1 line-clamp-2 text-xs text-rose-700 dark:text-rose-300" :title="row.ultimo_error">{{ row.ultimo_error }}</p></td><td class="px-4 py-4"><span :class="['inline-flex rounded-full px-2.5 py-1 text-xs font-bold', statusClass(row.estado)]">{{ labelStatus(row.estado) }}</span><p v-if="row.enviado_at" class="mt-1 text-[11px] text-slate-500">{{ formatDate(row.enviado_at) }}</p></td><td class="px-4 py-4 text-xs text-slate-600 dark:text-slate-300">{{ row.intentos }} / {{ row.max_intentos }}<p class="mt-1 text-[11px] text-slate-500">{{ formatDate(row.creado_at) }}</p></td><td class="px-4 py-4 text-right"><button v-if="row.estado === 'fallida'" type="button" :disabled="resendingId === row.id" class="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 px-2.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-900 dark:text-blue-300 dark:hover:bg-blue-950/40" @click="resend(row)"><RotateCcw :class="['h-3.5 w-3.5', { 'animate-spin': resendingId === row.id }]" />Reenviar</button><span v-else class="text-xs text-slate-400">—</span></td></tr></tbody></table></div>
      <div v-if="pages > 1" class="flex items-center justify-between border-t border-slate-100 px-4 py-3 dark:border-slate-800"><button type="button" :disabled="page <= 1 || loading" class="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800" @click="page--; load()"><ChevronLeft class="h-4 w-4" />Anterior</button><span class="text-xs text-slate-500">{{ page }} / {{ pages }}</span><button type="button" :disabled="page >= pages || loading" class="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800" @click="page++; load()">Siguiente<ChevronRight class="h-4 w-4" /></button></div>
    </div>
  </section>
</template>
