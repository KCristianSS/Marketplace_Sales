<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { despachosApi, type Despacho } from '@/api/despachos';
import ShippingTracePanel from './ShippingTracePanel.vue';

const props = defineProps<{ orderId: string; admin?: boolean; cancelled?: boolean }>();
const despacho = ref<Despacho | null>(null);
const error = ref('');
const aviso = ref('');
const ocupado = ref(false);
let generacion = 0;
let versionConsulta = -1;
let timer: ReturnType<typeof setInterval> | undefined;

async function cargar(consultar = false) {
  if (ocupado.value) return;
  const actual = generacion;
  ocupado.value = true;
  error.value = '';
  try {
    const data = await (consultar ? despachosApi.consultar(props.orderId) : despachosApi.obtener(props.orderId));
    if (actual !== generacion) return;
    despacho.value = data;
    if (consultar) {
      versionConsulta = data.version;
      aviso.value = 'Consulta registrada para enviar a Entregas. Esperando respuesta del ERP.';
    } else if (versionConsulta >= 0 && data.version > versionConsulta) {
      aviso.value = 'Seguimiento actualizado con la respuesta de Entregas.';
      versionConsulta = -1;
    }
  } catch (e: any) {
    if (actual === generacion) error.value = e.response?.data?.detail || 'No se pudo consultar el despacho.';
  } finally { if (actual === generacion) ocupado.value = false; }
}
async function reintentar() {
  if (ocupado.value) return;
  const actual = generacion;
  ocupado.value = true;
  error.value = '';
  try {
    const data = await despachosApi.reintentar(props.orderId);
    if (actual !== generacion) return;
    despacho.value = data;
    aviso.value = 'Se reintentará la solicitud original sin duplicar el despacho.';
  } catch (e: any) { if (actual === generacion) error.value = e.response?.data?.detail || 'No se pudo reintentar.'; }
  finally { if (actual === generacion) ocupado.value = false; }
}
watch(() => props.orderId, () => {
  generacion++;
  despacho.value = null;
  ocupado.value = false;
  aviso.value = '';
  versionConsulta = -1;
  if (timer) clearInterval(timer);
  void cargar(!props.cancelled);
  timer = setInterval(() => { void cargar(); }, 5000); // Lee respuestas locales; no genera otra consulta externa.
}, { immediate: true });
onBeforeUnmount(() => { generacion++; if (timer) clearInterval(timer); });
</script>

<template>
  <section class="rounded-2xl border border-slate-200 p-4 dark:border-slate-700 space-y-3" aria-label="Seguimiento de despacho">
    <div class="flex flex-wrap items-center justify-between gap-3"><h3 class="text-sm font-bold text-slate-900 dark:text-white">Despacho a domicilio</h3>
      <button v-if="!cancelled" :disabled="ocupado" class="text-sm font-bold text-blue-600 disabled:opacity-50" @click="cargar(true)">{{ ocupado ? 'Consultando…' : 'Actualizar estado en ERP' }}</button></div>
    <p v-if="aviso" role="status" class="text-xs text-blue-700 dark:text-blue-300">{{ aviso }}</p>
    <p v-if="error" role="alert" class="text-sm text-rose-600">{{ error }}</p>
    <button v-if="admin && !despacho && error && !cancelled" :disabled="ocupado" class="text-sm font-bold text-blue-600" @click="reintentar">Recuperar solicitud de despacho</button>
    <template v-if="despacho">
      <dl class="grid sm:grid-cols-2 gap-3 text-sm"><div><dt class="text-xs text-slate-500">Estado logístico</dt><dd class="font-bold capitalize">{{ despacho.estado.replaceAll('_', ' ') }}</dd></div>
        <div><dt class="text-xs text-slate-500">Guía</dt><dd>{{ despacho.guia || 'Pendiente de respuesta de Entregas' }}</dd></div>
        <div><dt class="text-xs text-slate-500">Transportista</dt><dd>{{ despacho.transportista || 'Pendiente de asignación' }}</dd></div>
        <div><dt class="text-xs text-slate-500">Ruta</dt><dd>{{ despacho.ruta || 'Pendiente de asignación' }}</dd></div>
        <div v-if="despacho.ubicacion_actual"><dt class="text-xs text-slate-500">Ubicación</dt><dd>{{ despacho.ubicacion_actual }}</dd></div>
        <div v-if="despacho.fecha_estimada"><dt class="text-xs text-slate-500">Entrega estimada</dt><dd>{{ new Date(despacho.fecha_estimada).toLocaleString('es-BO') }}</dd></div></dl>
      <p v-if="despacho.motivo" class="text-sm text-amber-700">{{ despacho.motivo }}</p>
      <p v-if="despacho.estado === 'pendiente'" class="text-xs text-slate-500">La solicitud se genera automáticamente al confirmar la compra. La guía aparecerá cuando responda el ERP.</p>
      <template v-if="admin">
        <button v-if="despacho.estado === 'pendiente' && !cancelled" :disabled="ocupado" class="text-sm text-blue-600 font-bold" @click="reintentar">Reintentar solicitud</button>
      </template>
    </template>
    <ShippingTracePanel v-if="admin" :order-id="orderId" />
  </section>
</template>
