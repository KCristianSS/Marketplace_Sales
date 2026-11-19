<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { RefreshCw, ShieldCheck, Filter, X } from 'lucide-vue-next';
import { obtenerAuditoria, type AuditEntry, type AuditFilters } from '@/api/auditoria';

const entries = ref<AuditEntry[]>([]);
const total = ref(0);
const page = ref(1);
const pages = ref(1);
const pending = ref<number | null>(null);
const loading = ref(false);
const error = ref('');
const filters = reactive({ accion: '', entidad: '', actor: '', rol: '', solicitud: '', desde: '', hasta: '' });
let applied: Omit<AuditFilters, 'page' | 'limit'> = {};
let controller: AbortController | null = null;
let generation = 0;

async function load() {
  controller?.abort();
  controller = new AbortController();
  const current = ++generation;
  loading.value = true;
  error.value = '';
  try {
    const data = await obtenerAuditoria({ ...applied, page: page.value, limit: 20 }, controller.signal);
    if (current !== generation) return;
    entries.value = data.items;
    total.value = data.total;
    page.value = data.pagina;
    pages.value = data.total_paginas;
    pending.value = data.pendientes_locales;
  } catch (err: any) {
    if (current === generation && err.code !== 'ERR_CANCELED') error.value = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'No se pudo cargar la auditoría. Intenta nuevamente.';
  } finally { if (current === generation) loading.value = false; }
}
function applyFilters() {
  if (filters.desde && filters.hasta && new Date(filters.desde) > new Date(filters.hasta)) {
    error.value = 'La fecha inicial no puede ser posterior a la fecha final.';
    return;
  }
  applied = Object.fromEntries(Object.entries(filters).filter(([, value]) => value.trim()).map(([key, value]) =>
    [key, key === 'desde' || key === 'hasta' ? new Date(value).toISOString() : value.trim()]));
  page.value = 1;
  void load();
}
function resetFilters() { Object.keys(filters).forEach(key => { filters[key as keyof typeof filters] = ''; }); applyFilters(); }
function goTo(value: number) { page.value = value; void load(); }
function date(value: string) { return new Date(value).toLocaleString('es-BO'); }
function json(value: unknown) { return value === undefined ? '—' : JSON.stringify(value, null, 2); }
function fields(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : value == null ? {} : { valor: value };
}
function changes(entry: AuditEntry) {
  const before = fields(entry.payload_before), after = fields(entry.payload_after);
  return [...new Set([...Object.keys(before), ...Object.keys(after)])].sort().filter(key => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .map(key => ({ key, before: before[key], after: after[key] }));
}
onMounted(load);
onBeforeUnmount(() => { generation++; controller?.abort(); });
</script>

<template>
  <section class="space-y-5" aria-label="Auditoría de operaciones">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div><h2 class="flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-white"><ShieldCheck class="h-6 w-6 text-blue-600" /> Auditoría de operaciones</h2><p class="mt-1 text-sm text-slate-500">Consulta quién realizó cada operación, cuándo, desde dónde y qué valores cambiaron.</p></div>
      <button type="button" :disabled="loading" class="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50" @click="load"><RefreshCw :class="['h-4 w-4', { 'animate-spin': loading }]" /> Actualizar</button>
    </header>
    <form class="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900 sm:grid-cols-2 xl:grid-cols-4" @submit.prevent="applyFilters">
      <label class="audit-label">Operación<input v-model="filters.accion" maxlength="100" placeholder="Ej.: ORDEN_ESTADO_CAMBIADO" class="audit-input" /></label>
      <label class="audit-label">Entidad<select v-model="filters.entidad" class="audit-input"><option value="">Todas las entidades</option><option v-for="entity in ['productos','categorias','listas_precios','precios_items','combos','cupones','ordenes','pos_ventas','pagos','reembolsos','usuarios_internos','caja_turnos','movimientos_caja','tarjetas_regalo','flete_configuracion','cotizaciones_b2b','perfiles_clientes','cotizaciones_configuracion']" :key="entity" :value="entity">{{ entity.replaceAll('_', ' ') }}</option></select></label>
      <label class="audit-label">Usuario (UUID)<input v-model="filters.actor" pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" placeholder="ID del usuario" class="audit-input" /></label>
      <label class="audit-label">Rol<select v-model="filters.rol" class="audit-input"><option value="">Todos los roles</option><option v-for="role in ['administrador','gerente_comercial','cajero','cliente','sistema','pasarela','anonimo']" :key="role" :value="role">{{ role.replaceAll('_',' ') }}</option></select></label>
      <label class="audit-label">Desde<input v-model="filters.desde" type="datetime-local" class="audit-input" /></label>
      <label class="audit-label">Hasta<input v-model="filters.hasta" type="datetime-local" class="audit-input" /></label>
      <label class="audit-label">ID de solicitud<input v-model="filters.solicitud" pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" placeholder="Agrupar una operación" class="audit-input" /></label>
      <div class="flex items-end gap-2"><button type="submit" class="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white"><Filter class="h-4 w-4" /> Filtrar</button><button type="button" aria-label="Limpiar filtros" class="rounded-lg border p-2" @click="resetFilters"><X class="h-5 w-5" /></button></div>
    </form>
    <p v-if="pending" role="status" class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{{ pending }} eventos pendientes de guardar en Supabase. El sistema los reintentará automáticamente; pulsa Actualizar para consultar su estado.</p>
    <p v-if="error" role="alert" class="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
    <div class="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900" :aria-busy="loading">
      <div class="border-b px-4 py-3 text-xs text-slate-500">{{ total }} registros · Página {{ page }} de {{ pages }} <span v-if="loading">· Cargando…</span></div>
      <div class="overflow-x-auto"><table class="w-full min-w-[850px] text-left text-sm"><thead class="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800"><tr><th class="p-3">Cuándo</th><th class="p-3">Quién</th><th class="p-3">Qué</th><th class="p-3">Desde dónde</th><th class="p-3">Cambios</th></tr></thead><tbody>
        <tr v-for="entry in entries" :key="entry.id" class="border-t border-slate-100 align-top dark:border-slate-800">
          <td class="p-3 text-xs"><time>{{ date(entry.created_at) }}</time></td>
          <td class="max-w-[190px] p-3"><span class="text-xs font-semibold capitalize">{{ entry.user_role?.replaceAll('_',' ') || 'Sin rol registrado' }}</span><p class="mt-1 break-all font-mono text-[11px] text-slate-500">{{ entry.actor_id || entry.user_id || 'Actor no registrado' }}</p></td>
          <td class="max-w-[220px] p-3"><strong class="break-all text-xs">{{ entry.action }}</strong><p class="mt-1 text-xs text-slate-500">{{ entry.entity }}</p><p v-if="entry.entity_id" class="mt-1 break-all font-mono text-[11px] text-slate-400">{{ entry.entity_id }}</p></td>
          <td class="max-w-[200px] p-3 text-xs"><p>{{ entry.ip_address || 'IP no registrada' }}</p><p v-if="entry.request_path" class="mt-1 break-all text-slate-500">{{ entry.request_method }} {{ entry.request_path }}</p><span v-if="entry.source === 'legacy'" class="mt-1 block text-[10px] text-amber-700">Registro histórico: puede tener metadatos incompletos</span></td>
          <td class="min-w-[210px] p-3"><details><summary class="cursor-pointer text-xs font-bold text-blue-700 dark:text-blue-300">Ver antes y después</summary><div class="mt-3 max-w-xl space-y-3 text-xs">
            <div v-for="change in changes(entry)" :key="change.key" class="rounded-lg border border-slate-200 p-2 dark:border-slate-700"><strong>{{ change.key }}</strong><div class="mt-2 grid gap-2"><div><span class="font-semibold text-rose-700">Antes</span><pre class="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2 dark:bg-slate-950">{{ json(change.before) }}</pre></div><div><span class="font-semibold text-emerald-700">Después</span><pre class="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2 dark:bg-slate-950">{{ json(change.after) }}</pre></div></div></div>
            <p v-if="!changes(entry).length" class="text-slate-500">El evento no incluye diferencias entre valores.</p>
            <p v-if="entry.request_id" class="break-all"><strong>Solicitud:</strong> {{ entry.request_id }}</p><p v-if="entry.user_agent" class="break-all"><strong>Dispositivo:</strong> {{ entry.user_agent }}</p>
            <details><summary class="cursor-pointer text-slate-500">Ver registro JSON</summary><pre class="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all">{{ json(entry) }}</pre></details>
          </div></details></td>
        </tr>
        <tr v-if="!entries.length && !loading && !error"><td colspan="5" class="p-8 text-center text-slate-500">No hay auditorías para los filtros seleccionados.</td></tr>
      </tbody></table></div>
      <nav v-if="pages > 1" class="flex justify-between border-t p-3" aria-label="Paginación de auditoría"><button type="button" :disabled="loading || page <= 1" class="rounded-lg border px-3 py-2 text-xs disabled:opacity-50" @click="goTo(page-1)">Anterior</button><button type="button" :disabled="loading || page >= pages" class="rounded-lg border px-3 py-2 text-xs disabled:opacity-50" @click="goTo(page+1)">Siguiente</button></nav>
    </div>
  </section>
</template>

<style scoped>
.audit-label { @apply space-y-1 text-xs font-semibold text-slate-600 dark:text-slate-300; }
.audit-input { @apply block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-normal dark:border-slate-700 dark:bg-slate-800; }
</style>
