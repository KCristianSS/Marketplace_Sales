<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { CalendarDays, ChevronLeft, ChevronRight, Download, FileText, PackageOpen, Printer, RefreshCw, Search, SlidersHorizontal } from 'lucide-vue-next';
import { apiClient } from '@/api/client';
import { cambiarEstadoOrden, descargarFacturaXml, obtenerFacturaImpresion, obtenerHistorialOrdenes, obtenerOrden } from '@/api/ordenes';
import type { EstadoOrden, HistorialOrdenesFiltros, OrdenHistorial } from '@/types';
import OrderDetailModal from './OrderDetailModal.vue';

const props = withDefaults(defineProps<{
  scope?: 'cliente' | 'administrador';
  title?: string;
  pageSize?: number;
}>(), { scope: 'cliente', pageSize: 10 });

const isAdmin = computed(() => props.scope === 'administrador');
const heading = computed(() => props.title || (isAdmin.value ? 'Historial de ventas' : 'Historial de compras'));
const orders = ref<OrdenHistorial[]>([]);
const loading = ref(false);
const error = ref('');
const detailLoading = ref(false);
const selectedOrder = ref<OrdenHistorial | null>(null);
const processingDocumentId = ref<string | null>(null);
const cancellationOrder = ref<OrdenHistorial | null>(null);
const cancellationReason = ref('Ya no necesito el pedido');
const cancellationOtherReason = ref('');
const cancellationError = ref('');
const isCancelling = ref(false);const currentPage = ref(1);
const total = ref(0);
const totalPages = ref(1);
const filters = reactive({
  busqueda: '',
  cliente_id: '',
  estado: '' as '' | EstadoOrden,
  canal: '',
  fecha_desde: '',
  fecha_hasta: ''
});

const visibleRange = computed(() => {
  if (!total.value) return '0 resultados';
  const start = (currentPage.value - 1) * props.pageSize + 1;
  return `${start}–${Math.min(currentPage.value * props.pageSize, total.value)} de ${total.value}`;
});

function requestFilters(): HistorialOrdenesFiltros {
  return {
    page: currentPage.value,
    limit: props.pageSize,
    ...(filters.busqueda.trim() ? { busqueda: filters.busqueda.trim() } : {}),
    ...(isAdmin.value && filters.cliente_id.trim() ? { cliente_id: filters.cliente_id.trim() } : {}),
    ...(filters.estado ? { estado: filters.estado } : {}),
    ...(filters.canal ? { canal: filters.canal } : {}),
    ...(filters.fecha_desde ? { fecha_desde: filters.fecha_desde } : {}),
    ...(filters.fecha_hasta ? { fecha_hasta: filters.fecha_hasta } : {})
  };
}

async function loadOrders() {
  loading.value = true;
  error.value = '';
  try {
    const response = await obtenerHistorialOrdenes(requestFilters());
    orders.value = response.items;
    total.value = response.total;
    currentPage.value = response.pagina;
    totalPages.value = response.total_paginas;
  } catch (err: any) {
    orders.value = [];
    total.value = 0;
    totalPages.value = 1;
    error.value = err.response?.data?.detail || 'No se pudo cargar el historial. Revisa tu conexión e inténtalo otra vez.';
  } finally {
    loading.value = false;
  }
}

function applyFilters() {
  currentPage.value = 1;
  void loadOrders();
}

function clearFilters() {
  filters.busqueda = '';
  filters.cliente_id = '';
  filters.estado = '';
  filters.canal = '';
  filters.fecha_desde = '';
  filters.fecha_hasta = '';
  applyFilters();
}

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value || page === currentPage.value) return;
  currentPage.value = page;
  void loadOrders();
}

async function openDetail(order: OrdenHistorial) {
  selectedOrder.value = order;
  detailLoading.value = true;
  try {
    selectedOrder.value = await obtenerOrden(order.id);
  } catch {
    // La fila del listado conserva la información suficiente si el detalle falla.
  } finally {
    detailLoading.value = false;
  }
}

function cufOf(order: OrdenHistorial) {
  return order.cuf_factura || order.factura?.cuf || null;
}

async function downloadXml(order: OrdenHistorial) {
  const cuf = cufOf(order);
  if (!cuf) return;
  processingDocumentId.value = order.id;
  error.value = '';
  try {
    const blob = await descargarFacturaXml(cuf);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `factura_${order.codigo_orden}_${cuf.slice(0, 16)}.xml`.replace(/[^a-zA-Z0-9._-]/g, '_');
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo descargar el comprobante XML.';
  } finally {
    processingDocumentId.value = null;
  }
}

async function printReceipt(order: OrdenHistorial) {
  const cuf = cufOf(order);
  if (!cuf) return;
  const preview = window.open('', '_blank');
  if (!preview) {
    error.value = 'El navegador bloqueó la ventana de impresión. Habilita las ventanas emergentes e inténtalo otra vez.';
    return;
  }
  preview.opener = null;
  preview.document.title = 'Cargando comprobante…';
  preview.document.body.innerHTML = '<p style="font-family:system-ui;padding:24px">Cargando comprobante…</p>';
  processingDocumentId.value = order.id;
  error.value = '';
  try {
    const html = await obtenerFacturaImpresion(cuf);
    preview.document.open();
    preview.document.write(html);
    preview.document.close();
  } catch (err: any) {
    preview.close();
    error.value = err.response?.data?.detail || 'No se pudo abrir el comprobante para impresión.';
  } finally {
    processingDocumentId.value = null;
  }
}

function formatCurrency(value: number | undefined | null) {
  return new Intl.NumberFormat('es-BO', { style: 'currency', currency: 'BOB', minimumFractionDigits: 2 }).format(Number(value || 0));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium' }).format(new Date(value));
}

function productSummary(order: OrdenHistorial) {
  const first = order.items[0];
  if (!first) return 'Sin ítems registrados';
  return `${first.nombre_producto}${order.items.length > 1 ? ` y ${order.items.length - 1} más` : ''}`;
}

function paymentSummary(order: OrdenHistorial) {
  return order.pagos.map(payment => payment.metodo).join(', ') || 'Pago registrado';
}

function shortId(value: string) {
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function canCancel(order: OrdenHistorial) {
  return ['pendiente', 'confirmada', 'en_preparacion'].includes(order.estado);
}

// Cancellation is excluded on purpose: it must go through the reversal saga (/cancelar).
const SIGUIENTE_ESTADO: Partial<Record<EstadoOrden, EstadoOrden>> = {
  pendiente: 'confirmada',
  confirmada: 'en_preparacion',
  en_preparacion: 'despachada',
  despachada: 'entregada'
};

const ETIQUETA_ESTADO: Record<EstadoOrden, string> = {
  pendiente: 'Pendiente',
  confirmada: 'Confirmada',
  en_preparacion: 'En preparación',
  despachada: 'Despachada',
  entregada: 'Entregada',
  cancelada: 'Cancelada'
};

const advancingOrderId = ref<string | null>(null);

function nextStatus(order: OrdenHistorial) {
  return isAdmin.value ? SIGUIENTE_ESTADO[order.estado] || null : null;
}

async function advanceStatus(order: OrdenHistorial) {
  const siguiente = nextStatus(order);
  if (!siguiente) return;
  advancingOrderId.value = order.id;
  error.value = '';
  try {
    const updated = await cambiarEstadoOrden(order.id, siguiente);
    orders.value = orders.value.map(item => item.id === updated.id ? { ...item, ...updated } : item);
    if (selectedOrder.value?.id === updated.id) selectedOrder.value = { ...selectedOrder.value, ...updated };
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo actualizar el estado de la orden.';
  } finally {
    advancingOrderId.value = null;
  }
}

function openCancellation(order: OrdenHistorial) {
  cancellationOrder.value = order;
  cancellationReason.value = 'Ya no necesito el pedido';
  cancellationOtherReason.value = '';
  cancellationError.value = '';
}

async function confirmCancellation() {
  const order = cancellationOrder.value;
  if (!order) return;
  const motivo = cancellationReason.value === 'Otro'
    ? cancellationOtherReason.value.trim()
    : cancellationReason.value;
  if (motivo.length < 3) {
    cancellationError.value = 'Describe brevemente el motivo de cancelación.';
    return;
  }

  isCancelling.value = true;
  cancellationError.value = '';
  try {
    const { data } = await apiClient.post<OrdenHistorial>(
      `/api/v1/ordenes/${encodeURIComponent(order.id)}/cancelar`,
      null,
      { params: { motivo } }
    );
    orders.value = orders.value.map(item => item.id === data.id ? { ...item, ...data } : item);
    if (selectedOrder.value?.id === data.id) selectedOrder.value = { ...selectedOrder.value, ...data };
    cancellationOrder.value = null;
  } catch (err: any) {
    const detail = err.response?.data?.detail;
    cancellationError.value = typeof detail === 'string' ? detail : detail?.mensaje || 'No se pudo cancelar el pedido.';
  } finally {
    isCancelling.value = false;
  }
}
function statusClass(status: string) {
  const classes: Record<string, string> = {
    entregada: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    confirmada: 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300',
    en_preparacion: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    despachada: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950/60 dark:text-cyan-300',
    pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    cancelada: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300'
  };
  return classes[status] || classes.pendiente;
}

onMounted(() => void loadOrders());
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-6">
      <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div class="max-w-2xl"><p class="text-xs font-semibold text-emerald-700 dark:text-emerald-300">Transacciones registradas</p><h2 class="mt-1 text-lg font-extrabold text-slate-900 dark:text-white">{{ heading }}</h2><p class="mt-1 text-sm text-slate-500">{{ isAdmin ? 'Consulta ventas web y POS con sus comprobantes asociados.' : 'Consulta tus pedidos, su estado y los comprobantes emitidos.' }}</p></div>
        <button type="button" :disabled="loading" class="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="loadOrders"><RefreshCw :class="['h-3.5 w-3.5', { 'animate-spin': loading }]" /> Actualizar</button>
      </div>
      <form class="mt-5 grid gap-3 border-t border-slate-100 pt-4 dark:border-slate-800 lg:grid-cols-6" @submit.prevent="applyFilters">
        <label class="relative lg:col-span-2"><span class="sr-only">Buscar en historial</span><Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input v-model="filters.busqueda" type="search" class="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-800 placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="Orden, producto, guía o CUF" /></label>
        <label v-if="isAdmin" class="relative lg:col-span-2"><span class="sr-only">ID del cliente</span><input v-model="filters.cliente_id" type="search" class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" placeholder="ID del cliente" /></label>
        <label><span class="sr-only">Estado</span><select v-model="filters.estado" class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"><option value="">Todos los estados</option><option value="pendiente">Pendiente</option><option value="confirmada">Confirmada</option><option value="en_preparacion">En preparación</option><option value="despachada">Despachada</option><option value="entregada">Entregada</option><option value="cancelada">Cancelada</option></select></label>
        <label><span class="sr-only">Canal</span><select v-model="filters.canal" class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"><option value="">Todos los canales</option><option value="web">Marketplace</option><option value="pos">Punto de venta</option><option value="b2b">B2B</option></select></label>
        <label class="relative"><span class="sr-only">Desde</span><CalendarDays class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input v-model="filters.fecha_desde" type="date" class="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-2 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" title="Fecha desde" /></label>
        <label class="relative"><span class="sr-only">Hasta</span><CalendarDays class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" /><input v-model="filters.fecha_hasta" type="date" class="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-2 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" title="Fecha hasta" /></label>
        <div class="flex gap-2 lg:col-span-6"><button type="submit" :disabled="loading" class="inline-flex items-center gap-1.5 rounded-xl bg-emerald-800 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-900 disabled:opacity-60"><SlidersHorizontal class="h-3.5 w-3.5" /> Aplicar filtros</button><button type="button" class="rounded-xl px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" @click="clearFilters">Limpiar</button></div>
      </form>
    </div>

    <div v-if="error" class="flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-200" role="alert"><span>{{ error }}</span><button type="button" class="shrink-0 text-xs font-bold underline" @click="loadOrders">Reintentar</button></div>
    <div v-if="loading" class="space-y-3" aria-label="Cargando historial"><div v-for="index in 3" :key="index" class="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" /></div>
    <div v-else-if="orders.length === 0" class="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900"><PackageOpen class="mx-auto h-9 w-9 text-slate-400" /><h3 class="mt-3 text-sm font-bold text-slate-800 dark:text-white">No hay transacciones para mostrar</h3><p class="mx-auto mt-1 max-w-md text-sm text-slate-500">{{ isAdmin ? 'Prueba ajustando los filtros o espera a que se registren nuevas ventas.' : 'Cuando completes una compra, aparecerá aquí con su comprobante.' }}</p><RouterLink v-if="!isAdmin" to="/marketplace" class="mt-4 inline-flex rounded-xl bg-emerald-800 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-900">Ir al Marketplace</RouterLink></div>

    <div v-else class="space-y-3">
      <div class="flex items-center justify-between px-1 text-xs text-slate-500"><span>{{ visibleRange }}</span><span>Página {{ currentPage }} de {{ totalPages }}</span></div>
      <div v-if="isAdmin" class="hidden overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:block"><table class="min-w-full text-left text-sm"><thead class="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-800/70"><tr><th class="px-5 py-3 font-semibold">Orden</th><th class="px-5 py-3 font-semibold">Cliente</th><th class="px-5 py-3 font-semibold">Canal</th><th class="px-5 py-3 font-semibold">Estado</th><th class="px-5 py-3 font-semibold">Total</th><th class="px-5 py-3"><span class="sr-only">Acciones</span></th></tr></thead><tbody class="divide-y divide-slate-100 dark:divide-slate-800"><tr v-for="order in orders" :key="order.id" class="hover:bg-slate-50/70 dark:hover:bg-slate-800/40"><td class="px-5 py-4"><p class="font-mono text-xs font-bold text-emerald-800 dark:text-emerald-300">{{ order.codigo_orden }}</p><p class="mt-1 text-xs text-slate-500">{{ formatDate(order.created_at) }}</p></td><td class="px-5 py-4 font-mono text-xs text-slate-600 dark:text-slate-300">{{ shortId(order.cliente_id) }}</td><td class="px-5 py-4 capitalize text-slate-600 dark:text-slate-300">{{ order.canal }}</td><td class="px-5 py-4"><span :class="['inline-flex rounded-full px-2 py-1 text-xs font-bold capitalize', statusClass(order.estado)]">{{ order.estado.replace('_', ' ') }}</span></td><td class="px-5 py-4 font-bold text-slate-800 dark:text-white">{{ formatCurrency(order.total) }}</td><td class="px-5 py-4 text-right"><div class="flex items-center justify-end gap-1.5"><button v-if="nextStatus(order)" type="button" :disabled="advancingOrderId === order.id" class="rounded-lg bg-emerald-800 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-900 disabled:opacity-60" @click="advanceStatus(order)">{{ advancingOrderId === order.id ? 'Actualizando…' : `Marcar ${ETIQUETA_ESTADO[nextStatus(order)!].toLowerCase()}` }}</button><button v-if="canCancel(order)" type="button" class="rounded-lg border border-rose-200 px-2.5 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950/30" @click="openCancellation(order)">Cancelar</button><button type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950/30" @click="openDetail(order)">Ver detalle</button></div></td></tr></tbody></table></div>
      <article v-for="order in orders" :key="order.id" :class="['rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-5', { 'lg:hidden': isAdmin }]">
        <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="font-mono text-sm font-extrabold text-emerald-800 dark:text-emerald-300">{{ order.codigo_orden }}</span><span :class="['rounded-full px-2.5 py-1 text-xs font-bold capitalize', statusClass(order.estado)]">{{ order.estado.replace('_', ' ') }}</span></div><p class="mt-2 truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{{ productSummary(order) }}</p><div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span>{{ formatDate(order.created_at) }}</span><span class="capitalize">{{ order.canal }}</span><span class="capitalize">{{ paymentSummary(order) }}</span></div><p v-if="isAdmin" class="mt-2 font-mono text-xs text-slate-500">Cliente: {{ order.cliente_id }}</p></div><div class="flex shrink-0 flex-row items-center justify-between gap-3 sm:flex-col sm:items-end"><div class="text-right"><span class="block text-xs text-slate-500">Total</span><strong class="text-base text-slate-900 dark:text-white">{{ formatCurrency(order.total) }}</strong></div><button type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950/30" @click="openDetail(order)">Ver detalle</button></div></div>
        <div class="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3 dark:border-slate-800"><button v-if="cufOf(order)" type="button" :disabled="processingDocumentId === order.id" class="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-100 disabled:opacity-60 dark:bg-blue-950/40 dark:text-blue-300" @click="printReceipt(order)"><Printer class="h-3.5 w-3.5" /> Comprobante</button><button v-if="cufOf(order)" type="button" :disabled="processingDocumentId === order.id" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-60 dark:text-slate-300 dark:hover:bg-slate-800" @click="downloadXml(order)"><Download class="h-3.5 w-3.5" /> XML</button><button v-if="nextStatus(order)" type="button" :disabled="advancingOrderId === order.id" class="rounded-lg bg-emerald-800 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-900 disabled:opacity-60" @click="advanceStatus(order)">{{ advancingOrderId === order.id ? 'Actualizando…' : `Marcar ${ETIQUETA_ESTADO[nextStatus(order)!].toLowerCase()}` }}</button><button v-if="canCancel(order)" type="button" class="rounded-lg border border-rose-200 px-2.5 py-1.5 text-xs font-bold text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950/30" @click="openCancellation(order)">Cancelar pedido</button><span v-if="!cufOf(order)" class="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-slate-400"><FileText class="h-3.5 w-3.5" /> Sin comprobante fiscal</span></div>
      </article>
      <nav v-if="totalPages > 1" class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900" aria-label="Paginación del historial"><button type="button" :disabled="currentPage === 1" class="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800" @click="goToPage(currentPage - 1)"><ChevronLeft class="h-4 w-4" /> Anterior</button><span class="text-xs text-slate-500">{{ currentPage }} / {{ totalPages }}</span><button type="button" :disabled="currentPage === totalPages" class="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800" @click="goToPage(currentPage + 1)">Siguiente <ChevronRight class="h-4 w-4" /></button></nav>
    </div>
    <div v-if="cancellationOrder" class="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/70 p-4" role="dialog" aria-modal="true" aria-labelledby="cancel-order-title">
      <div class="w-full max-w-md space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div>
          <h3 id="cancel-order-title" class="text-base font-bold text-slate-900 dark:text-white">¿Cancelar este pedido?</h3>
          <p class="mt-1 text-xs text-slate-500">{{ cancellationOrder.codigo_orden }} · El stock se liberará y se tramitará la reversión del cobro.</p>
        </div>
        <label class="block space-y-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">Motivo de cancelación
          <select v-model="cancellationReason" class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800"><option>Ya no necesito el pedido</option><option>Pedido realizado por error</option><option>Necesito cambiar el pedido</option><option>Otro</option></select>
        </label>
        <textarea v-if="cancellationReason === 'Otro'" v-model="cancellationOtherReason" rows="3" maxlength="240" placeholder="Cuéntanos el motivo" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800" />
        <p v-if="cancellationError" role="alert" class="text-xs font-semibold text-rose-600">{{ cancellationError }}</p>
        <div class="flex justify-end gap-2"><button type="button" :disabled="isCancelling" class="rounded-lg px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800" @click="cancellationOrder = null">Volver</button><button type="button" :disabled="isCancelling" class="rounded-lg bg-rose-600 px-4 py-2 text-xs font-bold text-white hover:bg-rose-700 disabled:opacity-50" @click="confirmCancellation">{{ isCancelling ? 'Cancelando…' : 'Confirmar cancelación' }}</button></div>
      </div>
    </div>
    <OrderDetailModal :order="selectedOrder" :loading="detailLoading" :processing-document="processingDocumentId === selectedOrder?.id" @close="selectedOrder = null" @print="printReceipt" @download="downloadXml" />
  </section>
</template>
