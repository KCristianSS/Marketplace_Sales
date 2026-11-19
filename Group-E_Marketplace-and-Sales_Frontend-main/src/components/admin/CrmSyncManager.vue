<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { RefreshCw, Send, Users, CheckCircle2, Clock, AlertTriangle } from 'lucide-vue-next';
import { getClientesSyncEstado, resincronizarCliente, procesarOutboxCrm, type CrmSyncEstadoResponse } from '@/api/client';
import { notify } from '@/lib/feedback';

const data = ref<CrmSyncEstadoResponse | null>(null);
const cargando = ref(false);
const procesando = ref(false);
const clienteEnviando = ref<string | null>(null);
const error = ref('');
const tab = ref<'clientes' | 'mensajes' | 'respuestas'>('clientes');
let timer: ReturnType<typeof setInterval> | undefined;
const etiquetas: Record<string, string> = { pendiente: 'Pendiente', publicando: 'Publicando', publicado: 'Publicado · esperando CRM', reintentando: 'Reintentando', sincronizado: 'Confirmado por CRM', error: 'Error' };
function fecha(value?: string | null) { return value ? new Date(value).toLocaleString('es-BO') : '—'; }
function clase(estado: string) { return estado === 'sincronizado' ? 'bg-emerald-100 text-emerald-800' : estado === 'error' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'; }
async function cargar() {
  if (cargando.value) return;
  cargando.value = true;
  try { data.value = await getClientesSyncEstado(); error.value = ''; }
  catch (e: any) { error.value = e.response?.data?.detail || 'No se pudo consultar la sincronización.'; }
  finally { cargando.value = false; }
}
async function sincronizar(id: string) {
  clienteEnviando.value = id;
  try { const result = await resincronizarCliente(id); notify.success(result.mensaje); await cargar(); }
  catch (e: any) { notify.error(e.response?.data?.detail || 'No se pudo encolar el cliente.'); }
  finally { clienteEnviando.value = null; }
}
async function procesar() {
  procesando.value = true;
  try { const result = await procesarOutboxCrm(20); notify.success(`Se procesaron ${result.procesados_total} intentos. Consulta el resultado de cada mensaje.`); await cargar(); }
  catch (e: any) { notify.error(e.response?.data?.detail || 'No se pudo procesar la cola.'); }
  finally { procesando.value = false; }
}
onMounted(() => { cargar(); timer = setInterval(cargar, 5000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div><h2 class="flex items-center gap-2 text-lg font-bold"><Users class="h-5 w-5 text-emerald-700" /> Clientes y CRM</h2><p class="mt-1 text-sm text-slate-500">Sincronización automática al registrar clientes o modificar sus datos y direcciones.</p></div>
      <button :disabled="cargando" class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm disabled:opacity-50" @click="cargar"><RefreshCw class="h-4 w-4" :class="{ 'animate-spin': cargando }" /> Actualizar</button>
    </header>
    <p v-if="error" role="alert" class="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
    <template v-if="data">
      <div class="grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><CheckCircle2 class="mb-2 h-5 w-5 text-emerald-600" /><p class="text-2xl font-bold">{{ data.metricas_clientes.sincronizados }}</p><p class="text-xs text-slate-500">Clientes confirmados por CRM</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><Clock class="mb-2 h-5 w-5 text-amber-600" /><p class="text-2xl font-bold">{{ data.metricas_clientes.pendientes }}</p><p class="text-xs text-slate-500">Clientes pendientes de confirmación</p></div>
        <div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"><AlertTriangle class="mb-2 h-5 w-5 text-rose-600" /><p class="text-2xl font-bold">{{ data.outbox_metricas.errores }}</p><p class="text-xs text-slate-500">Mensajes con error</p></div>
      </div>
      <p v-if="!data.receptor_configurado" class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Falta configurar la suscripción de respuestas del CRM. Los mensajes publicados quedarán esperando confirmación.</p>
      <div class="flex flex-wrap items-center gap-2">
        <button v-for="opcion in ([['clientes', 'Clientes'], ['mensajes', 'Mensajes'], ['respuestas', 'Respuestas del CRM']] as const)" :key="opcion[0]" class="rounded-xl px-4 py-2 text-sm font-semibold" :class="tab === opcion[0] ? 'bg-emerald-700 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'" @click="tab = opcion[0]">{{ opcion[1] }}</button>
      </div>
      <div v-if="tab === 'clientes'" class="overflow-x-auto rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table class="w-full text-left text-sm"><thead class="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800"><tr><th class="p-4">Cliente</th><th class="p-4">Estado</th><th class="p-4">Contacto CRM</th><th class="p-4">Última confirmación</th><th class="p-4">Acción</th></tr></thead><tbody class="divide-y divide-slate-100 dark:divide-slate-800">
          <tr v-for="c in data.clientes" :key="c.id"><td class="p-4"><p class="font-semibold">{{ c.nombre_completo }}</p><p class="text-xs text-slate-500">{{ c.email }}</p></td><td class="p-4"><span class="rounded-full px-2 py-1 text-xs font-bold" :class="clase(c.crm_sync_estado)">{{ etiquetas[c.crm_sync_estado] || c.crm_sync_estado }}</span></td><td class="p-4 font-mono text-xs">{{ c.crm_contact_id || 'Sin confirmar' }}</td><td class="p-4 text-xs">{{ fecha(c.crm_sync_at) }}</td><td class="p-4"><button :disabled="!!clienteEnviando" class="flex items-center gap-1 rounded-lg border border-emerald-200 px-3 py-2 text-xs font-bold text-emerald-800 disabled:opacity-40 dark:text-emerald-300" @click="sincronizar(c.id)"><Send class="h-3.5 w-3.5" /> {{ clienteEnviando === c.id ? 'Encolando…' : 'Sincronizar' }}</button></td></tr>
          <tr v-if="!data.clientes.length"><td colspan="5" class="p-8 text-center text-slate-500">No hay clientes registrados.</td></tr>
        </tbody></table><p class="p-3 text-xs text-slate-500">{{ data.clientes.length }} clientes mostrados de {{ data.metricas_clientes.total }}. Máximo 500 registros recientes.</p>
      </div>
      <div v-if="tab === 'mensajes'" class="space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-slate-500">Últimos 50 eventos. Los intentos conservan el identificador del evento.</p><button :disabled="procesando" class="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-50" @click="procesar">{{ procesando ? 'Procesando…' : 'Procesar pendientes' }}</button></div>
        <article v-for="item in data.ultimos_eventos_outbox" :key="item.id" class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <div class="flex flex-wrap justify-between gap-2"><span class="text-sm font-bold">{{ item.event_type }}</span><span class="rounded-full px-2 py-1 text-xs font-bold" :class="clase(item.estado)">{{ etiquetas[item.estado] || item.estado }}</span></div>
          <p class="mt-2 break-all font-mono text-xs text-slate-500">Evento: {{ item.event_id }}</p><p class="mt-1 text-xs text-slate-500">{{ fecha(item.created_at) }} · Intentos {{ item.intentos }} / {{ item.max_intentos }} · Message ID: {{ item.message_id || 'Sin publicación confirmada' }}</p>
          <p v-if="item.ultimo_error" class="mt-2 text-xs text-rose-700">{{ item.ultimo_error }}</p><details class="mt-3 text-xs"><summary class="cursor-pointer font-semibold">Ver contenido enviado</summary><pre class="mt-2 overflow-auto rounded-lg bg-slate-50 p-3 dark:bg-slate-800">{{ JSON.stringify(item.payload, null, 2) }}</pre></details>
        </article><p v-if="!data.ultimos_eventos_outbox.length" class="py-8 text-center text-sm text-slate-500">Todavía no hay mensajes. Puedes sincronizar un cliente existente.</p>
      </div>
      <div v-if="tab === 'respuestas'" class="space-y-3">
        <p class="text-sm text-slate-500">Solo se muestran respuestas recibidas del CRM. Publicar un mensaje no confirma que el CRM haya actualizado al cliente.</p>
        <article v-for="item in data.ultimas_verificaciones_crm" :key="item.id" class="rounded-xl border border-slate-200 p-4"><p class="text-sm font-bold">{{ item.event_type }}</p><p class="mt-1 break-all font-mono text-xs">{{ item.event_id }}</p><p class="mt-1 text-xs text-slate-500">{{ fecha(item.recibido_at) }} · {{ item.aplicado ? 'Aplicado al estado del cliente' : 'Sin cambio en la versión actual' }} · Duplicados ignorados: {{ item.duplicados || 0 }}</p></article>
        <p v-if="!data.ultimas_verificaciones_crm.length" class="py-8 text-center text-sm text-slate-500">No se han recibido confirmaciones del CRM.</p>
      </div>
      <details class="text-xs text-slate-500"><summary class="cursor-pointer">Configuración de mensajería</summary><p class="mt-2 break-all font-mono">{{ data.topic }}</p><p class="mt-1">Destino: CRM · actualización de pantalla cada 5 segundos.</p></details>
    </template>
  </section>
</template>
