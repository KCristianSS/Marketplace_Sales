<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, RouterLink } from 'vue-router';
import { ArrowLeft, Check, CircleDot, Clock3, MapPin, PackageCheck, Truck } from 'lucide-vue-next';
import { escucharSeguimientoPedido, obtenerSeguimientoPedido, type SeguimientoPedido } from '@/api/ordenes';
import type { EstadoOrden } from '@/types';

const route = useRoute();
const seguimiento = ref<SeguimientoPedido | null>(null);
const cargando = ref(true);
const error = ref('');
const actualizando = ref(false);
let controller: AbortController | null = null;
let intervalo: ReturnType<typeof setInterval> | null = null;

const estados = ['pendiente', 'confirmada', 'en_preparacion', 'despachada', 'entregada'] as const;
const etiquetas: Record<string, string> = {
  pendiente: 'Pedido recibido',
  confirmada: 'Pedido confirmado',
  en_preparacion: 'En preparación',
  despachada: 'Despachado',
  entregada: 'Entregado',
  cancelada: 'Cancelado'
};
const historialPorEstado = computed(() => new Map((seguimiento.value?.historial || []).map((evento) => [evento.estado, evento])));
const esRetiro = computed(() => seguimiento.value?.tipo_despacho === 'retiro_sucursal');
const estadosTimeline = computed<EstadoOrden[]>(() => {
  if (seguimiento.value?.estado_actual !== 'cancelada') return [...estados];
  const registrados: EstadoOrden[] = estados.filter((estado) => historialPorEstado.value.has(estado));
  if (!registrados.length) registrados.push('pendiente');
  registrados.push('cancelada');
  return registrados;
});

function fechaHora(value: string | null | undefined) {
  if (!value) return 'Pendiente';
  return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function detenerSeguimiento() {
  controller?.abort();
  controller = null;
  if (intervalo) clearInterval(intervalo);
  intervalo = null;
}

async function actualizar(silencioso = false) {
  const id = String(route.params.id || '');
  if (!id) return;
  if (!silencioso) cargando.value = true;
  actualizando.value = true;
  try {
    seguimiento.value = await obtenerSeguimientoPedido(id);
    error.value = '';
  } catch (err: any) {
    if (!seguimiento.value) error.value = err.response?.data?.detail || 'No se pudo cargar el seguimiento del pedido.';
  } finally {
    cargando.value = false;
    actualizando.value = false;
  }
}

async function iniciar(id: string) {
  detenerSeguimiento();
  seguimiento.value = null;
  error.value = '';
  cargando.value = true;
  await actualizar();
  if (!seguimiento.value) return;
  intervalo = setInterval(() => void actualizar(true), 10000);
  controller = new AbortController();
  void escucharSeguimientoPedido(id, controller.signal, (nuevo) => {
    seguimiento.value = nuevo;
    error.value = '';
  }).catch(() => {
    // La consulta periódica mantiene la pantalla al día si el proxy o la red cierran el stream.
  });
}

watch(() => String(route.params.id || ''), (id) => void iniciar(id), { immediate: true });
onBeforeUnmount(detenerSeguimiento);
</script>

<template>
  <main class="mx-auto min-h-[70vh] max-w-4xl px-4 py-8 sm:px-6 lg:py-12">
    <RouterLink to="/mi-cuenta?tab=pedidos" class="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 hover:text-emerald-950 dark:text-emerald-300 dark:hover:text-emerald-200"><ArrowLeft class="h-4 w-4" /> Volver a mis pedidos</RouterLink>

    <div v-if="cargando" class="mt-6 animate-pulse space-y-4" aria-label="Cargando seguimiento"><div class="h-36 rounded-2xl bg-slate-200 dark:bg-slate-800" /><div class="h-72 rounded-2xl bg-slate-200 dark:bg-slate-800" /></div>
    <section v-else-if="error" class="mt-6 rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200" role="alert"><h1 class="text-lg font-bold">No se pudo mostrar el seguimiento</h1><p class="mt-2 text-sm">{{ error }}</p><button type="button" class="mt-4 rounded-lg bg-rose-700 px-4 py-2 text-sm font-bold text-white" @click="iniciar(String(route.params.id || ''))">Reintentar</button></section>

    <template v-else-if="seguimiento">
      <section class="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8">
        <div class="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
          <div><p class="text-xs font-bold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">Seguimiento del pedido</p><h1 class="mt-2 font-mono text-2xl font-extrabold text-slate-900 dark:text-white">{{ seguimiento.codigo_orden }}</h1><p class="mt-2 text-sm text-slate-600 dark:text-slate-300">Estado actual: <span class="font-bold capitalize">{{ etiquetas[seguimiento.estado_actual] || seguimiento.estado_actual.replace('_', ' ') }}</span></p></div>
          <div class="flex items-center gap-2 self-start rounded-full bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200" aria-live="polite"><span class="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />{{ actualizando ? 'Actualizando' : 'Actualización automática activa' }}</div>
        </div>
        <div class="mt-6 grid gap-3 sm:grid-cols-2">
          <div class="flex gap-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/70"><component :is="esRetiro ? MapPin : Truck" class="mt-0.5 h-5 w-5 shrink-0 text-emerald-700 dark:text-emerald-300" /><div><p class="text-xs font-semibold text-slate-500">{{ esRetiro ? 'Retiro estimado en sucursal' : 'Entrega estimada a domicilio' }}</p><p class="mt-1 font-bold text-slate-900 dark:text-white">{{ seguimiento.fecha_estimada ? fechaHora(seguimiento.fecha_estimada) : 'Fecha no disponible' }}</p></div></div>
          <div v-if="seguimiento.tracking_number" class="flex gap-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/70"><PackageCheck class="mt-0.5 h-5 w-5 shrink-0 text-emerald-700 dark:text-emerald-300" /><div><p class="text-xs font-semibold text-slate-500">Número de guía</p><p class="mt-1 font-mono font-bold text-slate-900 dark:text-white">{{ seguimiento.tracking_number }}</p></div></div>
        </div>
      </section>

      <section class="mt-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8">
        <h2 class="text-lg font-extrabold text-slate-900 dark:text-white">Historial del pedido</h2>
        <ol class="mt-6">
          <li v-for="(estado, index) in estadosTimeline" :key="estado" class="relative flex gap-4 pb-7 last:pb-0">
            <span v-if="index < estadosTimeline.length - 1" class="absolute left-[15px] top-8 h-full w-px bg-slate-200 dark:bg-slate-700" />
            <span :class="['relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full', historialPorEstado.has(estado) ? 'bg-emerald-700 text-white' : 'border border-slate-300 bg-white text-slate-400 dark:border-slate-700 dark:bg-slate-900']">
              <Check v-if="historialPorEstado.has(estado) && estado !== seguimiento.estado_actual" class="h-4 w-4" /><CircleDot v-else-if="estado === seguimiento.estado_actual" class="h-4 w-4" /><Clock3 v-else class="h-4 w-4" />
            </span>
            <div class="min-w-0 flex-1 pt-1"><div class="flex flex-wrap items-center justify-between gap-2"><h3 :class="['text-sm font-bold', estado === seguimiento.estado_actual ? 'text-emerald-800 dark:text-emerald-300' : 'text-slate-800 dark:text-slate-200']">{{ etiquetas[estado] || estado }}</h3><time v-if="historialPorEstado.get(estado)?.fecha_hora" class="text-xs text-slate-500">{{ fechaHora(historialPorEstado.get(estado)?.fecha_hora) }}</time></div><p v-if="estado === 'cancelada' && seguimiento.motivo_cancelacion" class="mt-1 text-sm text-slate-600 dark:text-slate-300">Motivo: {{ seguimiento.motivo_cancelacion }}</p><p v-else-if="estado === seguimiento.estado_actual" class="mt-1 text-xs text-slate-500">Estado actual</p></div>
          </li>
        </ol>
        <p v-if="seguimiento.estado_actual === 'cancelada' && !seguimiento.motivo_cancelacion" class="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">Este pedido fue cancelado.</p>
      </section>
    </template>
  </main>
</template>
