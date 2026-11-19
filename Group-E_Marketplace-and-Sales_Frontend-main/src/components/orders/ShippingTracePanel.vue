<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue';
import { despachosApi, type FiltrosTrazabilidad, type TrazaEnvio } from '@/api/despachos';

const props = defineProps<{ orderId?: string }>();
const items = ref<TrazaEnvio[]>([]);
const pagina = ref(1);
const paginas = ref(1);
const total = ref(0);
const loading = ref(false);
const error = ref('');
const filtros = reactive({ estado: '', tipo_evento: '', direccion: '', simulacion: '', estado_logistico: '' });
let solicitud = 0;
let timer: ReturnType<typeof setInterval> | undefined;

async function cargar() {
  const actual = ++solicitud;
  loading.value = true;
  try {
    const params: FiltrosTrazabilidad = { page: pagina.value, limit: 20 };
    if (props.orderId) params.orden_id = props.orderId;
    if (filtros.estado) params.estado = filtros.estado;
    if (filtros.tipo_evento) params.tipo_evento = filtros.tipo_evento;
    if (filtros.direccion) params.direccion = filtros.direccion as 'entrada' | 'salida';
    if (filtros.simulacion) params.simulacion = filtros.simulacion === 'true';
    if (filtros.estado_logistico) params.estado_logistico = filtros.estado_logistico;
    const data = await despachosApi.trazabilidad(params);
    if (actual !== solicitud) return;
    items.value = data.items;
    total.value = data.total;
    pagina.value = data.pagina;
    paginas.value = data.total_paginas;
    error.value = '';
  } catch (err: any) {
    if (actual === solicitud) error.value = err.response?.data?.detail || 'No se pudo cargar la trazabilidad de envíos.';
  } finally { if (actual === solicitud) loading.value = false; }
}
function filtrar() { pagina.value = 1; void cargar(); }
function ir(p: number) { pagina.value = p; void cargar(); }
function fecha(valor: string) { return new Date(valor).toLocaleString('es-BO'); }
function json(valor: unknown) { return JSON.stringify(valor, null, 2); }
watch(() => props.orderId, () => {
  pagina.value = 1;
  items.value = [];
  void cargar();
  if (timer) clearInterval(timer);
  timer = setInterval(() => { if (!loading.value) void cargar(); }, 5000);
}, { immediate: true });
onBeforeUnmount(() => { solicitud++; if (timer) clearInterval(timer); });
</script>

<template>
  <section class="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900" aria-label="Trazabilidad de envíos">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div><h3 class="font-bold text-slate-900 dark:text-white">Trazabilidad de envíos y mensajes</h3>
        <p class="mt-1 text-xs text-slate-500">Estados actuales de las colas, intentos de publicación y respuestas de Entregas. Actualización cada 5 segundos.</p></div>
      <button type="button" :disabled="loading" class="rounded-lg border px-3 py-2 text-xs font-bold disabled:opacity-50" @click="cargar">{{ loading ? 'Cargando…' : 'Actualizar mensajes' }}</button>
    </header>
    <form class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" @submit.prevent="filtrar">
      <select v-model="filtros.estado" aria-label="Estado del mensaje" class="trace-input"><option value="">Todos los estados del mensaje</option><option v-for="e in ['pendiente','procesando','publicado','error_publicacion','cancelado','recibido','aplicado','ignorado','duplicado']" :key="e" :value="e">{{ e.replaceAll('_',' ') }}</option></select>
      <select v-model="filtros.tipo_evento" aria-label="Tipo de evento" class="trace-input"><option value="">Todos los eventos</option><option v-for="e in ['despacho.solicitado','despacho.estado.consultado','despacho.cancelacion.solicitada','despacho.generado','despacho.rechazado','despacho.estado.actualizado','despacho.cancelado','despacho.cotizacion.calculada','despacho.cotizacion.recibida']" :key="e" :value="e">{{ e }}</option></select>
      <select v-model="filtros.direccion" aria-label="Dirección del mensaje" class="trace-input"><option value="">Enviados y recibidos</option><option value="salida">Salientes a Entregas</option><option value="entrada">Respuestas recibidas</option></select>
      <select v-model="filtros.estado_logistico" aria-label="Estado logístico" class="trace-input"><option value="">Todos los estados logísticos</option><option v-for="e in ['pendiente','programado','en_preparacion','en_transito','entregado','rechazado','cancelado']" :key="e" :value="e">{{ e.replaceAll('_',' ') }}</option></select>
      <select v-model="filtros.simulacion" aria-label="Modo del mensaje" class="trace-input"><option value="">Todos los modos</option><option value="true">Cotizaciones de simulación</option><option value="false">Despachos</option></select>
      <button type="submit" class="rounded-lg bg-blue-600 px-3 py-2 text-sm font-bold text-white">Aplicar filtros</button>
    </form>
    <p v-if="error" role="alert" class="text-sm text-rose-600">{{ error }}</p>
    <p class="text-xs text-slate-500">{{ total }} registros · Página {{ pagina }} de {{ paginas }}</p>
    <p v-if="!items.length && !loading && !error" class="py-4 text-sm text-slate-500">No hay mensajes para los filtros seleccionados.</p>
    <article v-for="item in items" :key="item.id" class="space-y-2 rounded-xl border border-slate-200 p-3 text-xs dark:border-slate-700">
      <div class="flex flex-wrap justify-between gap-2"><strong class="break-all">{{ item.tipo_evento }}</strong><time>{{ fecha(item.created_at) }}</time></div>
      <div class="flex flex-wrap gap-2">
        <span class="rounded bg-slate-100 px-2 py-1 dark:bg-slate-800">{{ item.direccion === 'salida' ? 'Saliente' : 'Entrante' }} · {{ item.estado.replaceAll('_',' ') }}</span>
        <span v-if="item.estado_logistico" class="rounded bg-blue-50 px-2 py-1 text-blue-700 dark:bg-blue-950 dark:text-blue-200">Logística: {{ item.estado_logistico.replaceAll('_',' ') }}</span>
        <span v-if="item.simulacion" class="rounded bg-amber-50 px-2 py-1 font-bold text-amber-800">Simulación de cotización</span>
        <span v-if="item.registro === 'estado_actual'">Estado actual de la cola · Intentos: {{ item.intentos }}</span>
        <span v-if="item.registro === 'metadatos_historicos'">Registro histórico: contenido original no disponible</span>
      </div>
      <p class="break-all">Evento: {{ item.event_id }} · Correlación: {{ item.correlation_id || '—' }}</p>
      <p v-if="item.orden_id" class="break-all">Orden: {{ item.orden_id }}</p>
      <p v-if="item.message_id" class="break-all">ID Pub/Sub: {{ item.message_id }}</p>
      <p v-if="item.topic" class="break-all">Tópico: {{ item.topic }}</p>
      <p v-if="item.ultimo_error" class="text-rose-600">{{ item.ultimo_error }}</p>
      <details><summary class="cursor-pointer font-semibold text-blue-700 dark:text-blue-300">Ver contenido del mensaje</summary><pre class="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-3 dark:bg-slate-950">{{ json(item.mensaje) }}</pre><p class="mt-2 font-semibold">Atributos Pub/Sub</p><pre class="mt-1 overflow-auto whitespace-pre-wrap break-all">{{ json(item.atributos) }}</pre></details>
    </article>
    <nav v-if="paginas > 1" class="flex items-center justify-between" aria-label="Paginación de mensajes"><button type="button" :disabled="loading || pagina <= 1" class="rounded border px-3 py-2 text-xs disabled:opacity-50" @click="ir(pagina - 1)">Anterior</button><button type="button" :disabled="loading || pagina >= paginas" class="rounded border px-3 py-2 text-xs disabled:opacity-50" @click="ir(pagina + 1)">Siguiente</button></nav>
  </section>
</template>

<style scoped>
.trace-input { @apply w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800; }
</style>
