<script setup lang="ts">
import { computed } from 'vue';
import { Calendar, CreditCard, Download, FileText, MapPin, Package, Printer, ReceiptText, Truck, X } from 'lucide-vue-next';
import type { OrdenHistorial } from '@/types';

const props = withDefaults(defineProps<{
  order: OrdenHistorial | null;
  loading?: boolean;
  processingDocument?: boolean;
}>(), { loading: false, processingDocument: false });

const emit = defineEmits<{
  close: [];
  print: [order: OrdenHistorial];
  download: [order: OrdenHistorial];
}>();

const cuf = computed(() => props.order?.cuf_factura || props.order?.factura?.cuf || null);

function formatCurrency(value: number | undefined | null) {
  return new Intl.NumberFormat('es-BO', { style: 'currency', currency: 'BOB', minimumFractionDigits: 2 }).format(Number(value || 0));
}

function formatDate(value?: string) {
  if (!value) return 'Sin fecha registrada';
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function statusClass(status?: string) {
  const classes: Record<string, string> = {
    entregada: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    confirmada: 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300',
    en_preparacion: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    despachada: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-950/60 dark:text-cyan-300',
    pendiente: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    cancelada: 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300'
  };
  return classes[status || ''] || classes.pendiente;
}
</script>

<template>
  <div v-if="order || loading" class="fixed inset-0 z-[70] flex items-end bg-slate-950/55 p-0 backdrop-blur-sm sm:items-center sm:justify-center sm:p-6" role="presentation" @click.self="emit('close')">
    <section class="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-white shadow-2xl dark:bg-slate-900 sm:max-w-3xl sm:rounded-3xl" role="dialog" aria-modal="true" aria-labelledby="order-detail-title" @keydown.esc="emit('close')">
      <header class="sticky top-0 z-10 flex items-start justify-between border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95 sm:px-7">
        <div>
          <p class="text-xs font-semibold text-slate-500">Detalle de transacción</p>
          <h2 id="order-detail-title" class="mt-1 text-lg font-extrabold text-slate-900 dark:text-white">{{ order?.codigo_orden || 'Cargando orden…' }}</h2>
        </div>
        <button type="button" class="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-white" aria-label="Cerrar detalle" @click="emit('close')"><X class="h-5 w-5" /></button>
      </header>

      <div v-if="loading" class="space-y-5 p-5 sm:p-7"><div v-for="index in 4" :key="index" class="h-20 animate-pulse rounded-2xl bg-slate-100 dark:bg-slate-800" /></div>

      <div v-else-if="order" class="space-y-6 p-5 sm:p-7">
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/60">
          <div class="flex items-center gap-3">
            <span class="rounded-xl bg-white p-2 text-blue-700 shadow-sm dark:bg-slate-900 dark:text-blue-300"><ReceiptText class="h-5 w-5" /></span>
            <div><p class="text-xs text-slate-500">Estado de la orden</p><span :class="['mt-1 inline-flex rounded-full px-2.5 py-1 text-xs font-bold capitalize', statusClass(order.estado)]">{{ order.estado.replace('_', ' ') }}</span></div>
          </div>
          <p class="text-right text-xs text-slate-500"><span class="block">Total pagado</span><strong class="text-base text-slate-900 dark:text-white">{{ formatCurrency(order.total) }}</strong></p>
        </div>

        <div class="grid gap-3 sm:grid-cols-2">
          <div class="flex gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"><Calendar class="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /><div><p class="text-xs text-slate-500">Fecha de compra</p><p class="mt-0.5 text-sm font-semibold text-slate-800 dark:text-slate-100">{{ formatDate(order.created_at) }}</p></div></div>
          <div class="flex gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"><Truck class="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /><div><p class="text-xs text-slate-500">Entrega</p><p class="mt-0.5 text-sm font-semibold capitalize text-slate-800 dark:text-slate-100">{{ order.tipo_despacho.replace('_', ' ') }}</p></div></div>
          <div v-if="order.tracking_number" class="flex gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"><MapPin class="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /><div><p class="text-xs text-slate-500">Guía de despacho</p><p class="mt-0.5 break-all text-sm font-semibold text-slate-800 dark:text-slate-100">{{ order.tracking_number }}</p></div></div>
          <div class="flex gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"><CreditCard class="mt-0.5 h-4 w-4 shrink-0 text-slate-400" /><div><p class="text-xs text-slate-500">Pago</p><p class="mt-0.5 text-sm font-semibold capitalize text-slate-800 dark:text-slate-100">{{ order.pagos.map(pago => pago.metodo).join(', ') || 'No registrado' }}</p></div></div>
        </div>

        <section>
          <div class="mb-3 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-white"><Package class="h-4 w-4 text-blue-600" /> Productos</div>
          <div class="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
            <div v-for="item in order.items" :key="item.id" class="flex items-start justify-between gap-4 border-b border-slate-100 p-3 last:border-b-0 dark:border-slate-800">
              <div class="min-w-0"><p class="text-sm font-semibold text-slate-800 dark:text-slate-100">{{ item.nombre_producto }}</p><p class="mt-0.5 text-xs text-slate-500">{{ item.sku }} · {{ item.cantidad }} × {{ formatCurrency(item.precio_unitario) }}</p></div>
              <strong class="shrink-0 text-sm text-slate-800 dark:text-white">{{ formatCurrency(item.total_linea) }}</strong>
            </div>
          </div>
        </section>

        <section class="ml-auto max-w-sm space-y-2 text-sm">
          <div class="flex justify-between text-slate-500"><span>Subtotal</span><span>{{ formatCurrency(order.subtotal) }}</span></div>
          <div v-if="order.descuento" class="flex justify-between text-emerald-700 dark:text-emerald-300"><span>Descuento</span><span>−{{ formatCurrency(order.descuento) }}</span></div>
          <div class="flex justify-between text-slate-500"><span>Envío</span><span>{{ formatCurrency(order.costo_envio) }}</span></div>
          <div class="flex justify-between border-t border-slate-200 pt-2 font-extrabold text-slate-900 dark:border-slate-700 dark:text-white"><span>Total</span><span>{{ formatCurrency(order.total) }}</span></div>
        </section>

        <section v-if="cuf" class="rounded-2xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-900/70 dark:bg-blue-950/30">
          <div class="flex items-start gap-3"><FileText class="mt-0.5 h-5 w-5 shrink-0 text-blue-700 dark:text-blue-300" /><div class="min-w-0"><p class="text-sm font-bold text-blue-950 dark:text-blue-100">Comprobante fiscal disponible</p><p class="mt-1 break-all text-xs text-blue-800 dark:text-blue-200">CUF: {{ cuf }}</p></div></div>
          <div class="mt-4 flex flex-wrap gap-2"><button type="button" :disabled="processingDocument" class="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60" @click="emit('print', order)"><Printer class="h-3.5 w-3.5" /> Ver e imprimir</button><button type="button" :disabled="processingDocument" class="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 py-2 text-xs font-bold text-blue-800 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-blue-800 dark:bg-slate-900 dark:text-blue-200" @click="emit('download', order)"><Download class="h-3.5 w-3.5" /> Descargar XML</button></div>
        </section>
      </div>
    </section>
  </div>
</template>
