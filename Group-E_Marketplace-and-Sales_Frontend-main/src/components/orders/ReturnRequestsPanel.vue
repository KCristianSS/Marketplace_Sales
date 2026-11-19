<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { listarDevoluciones, resolverDevolucion, solicitarDevolucion, type Devolucion, type ItemDevolucion } from '@/api/devoluciones';
import type { OrdenHistorial } from '@/types';

const props = defineProps<{ scope: 'cliente' | 'administrador'; order?: OrdenHistorial }>();
const requests = ref<Devolucion[]>([]);
const loading = ref(false);
const saving = ref(false);
const open = ref(false);
const reason = ref('');
const selectedFiles = ref<File[]>([]);
const quantities = ref<Record<string, number>>({});
const comments = ref<Record<string, string>>({});
const errors = ref<Record<string, string>>({});
const isAdmin = computed(() => props.scope === 'administrador');
const matching = computed(() => props.order ? requests.value.filter(item => item.orden_id === props.order!.id) : requests.value);
const usedQuantities = computed(() => {
  const used: Record<string, number> = {};
  for (const request of matching.value) {
    if (request.estado === 'rechazada') continue;
    for (const item of request.items || []) used[item.orden_item_id] = (used[item.orden_item_id] || 0) + item.cantidad;
  }
  return used;
});
const returnableItems = computed(() => (props.order?.items || []).map(item => ({
  orden_item_id: item.id,
  variante_id: item.variante_id,
  sku: item.sku,
  nombre_producto: item.nombre_producto,
  cantidad: Math.max(0, item.cantidad - (usedQuantities.value[item.id] || 0)),
  precio_unitario: item.precio_unitario
})).filter(item => item.cantidad > 0));
const hasOpenRequest = computed(() => matching.value.some(item => item.estado === 'solicitada'));
const withinWindow = computed(() => props.order?.estado === 'entregada');

async function load() {
  loading.value = true;
  try { requests.value = await listarDevoluciones(); }
  catch (error: any) { errors.value.load = error.response?.data?.detail || 'No se pudieron cargar las solicitudes.'; }
  finally { loading.value = false; }
}

async function submit() {
  if (!props.order) return;
  const selected = returnableItems.value.filter(item => Number(quantities.value[item.orden_item_id]) > 0).map(item => ({ ...item, cantidad: Number(quantities.value[item.orden_item_id]) }));
  if (!selected.length) { errors.value.form = 'Selecciona al menos un producto y su cantidad.'; return; }
  if (!selectedFiles.value.length) { errors.value.form = 'Adjunta al menos una foto como evidencia.'; return; }
  saving.value = true;
  errors.value.form = '';
  try {
    await solicitarDevolucion({ ordenId: props.order.id, motivo: reason.value.trim(), items: selected, evidencias: selectedFiles.value });
    open.value = false;
    reason.value = '';
    selectedFiles.value = [];
    quantities.value = {};
    await load();
  } catch (error: any) { errors.value.form = error.response?.data?.detail || 'No se pudo enviar la solicitud.'; }
  finally { saving.value = false; }
}

async function resolve(request: Devolucion, action: 'aprobar' | 'rechazar') {
  const comment = (comments.value[request.id] || '').trim();
  if (action === 'rechazar' && comment.length < 3) { errors.value[request.id] = 'El comentario es obligatorio para rechazar.'; return; }
  errors.value[request.id] = '';
  try {
    const updated = await resolverDevolucion(request.id, action, comment);
    requests.value = requests.value.map(item => item.id === updated.id ? { ...item, ...updated } : item);
  } catch (error: any) { errors.value[request.id] = error.response?.data?.detail || 'No se pudo resolver la solicitud.'; }
}

function statusLabel(state: string) { return ({ solicitada: 'Solicitada', aprobada: 'Aprobada', rechazada: 'Rechazada', completada: 'Completada' } as Record<string, string>)[state] || state; }
onMounted(load);
</script>

<template>
  <section class="space-y-3">
    <div v-if="!isAdmin && order" class="border-t border-slate-100 pt-3 dark:border-slate-800">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">Devolución <span v-if="matching.length">· {{ statusLabel(matching[0].estado) }}</span></p>
        <button v-if="withinWindow && returnableItems.length && !hasOpenRequest" type="button" class="rounded-lg border border-amber-300 px-2.5 py-1.5 text-xs font-bold text-amber-800 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-950/30" @click="open = true">Solicitar devolución</button>
      </div>
      <div v-for="request in matching" :key="request.id" class="mt-2 rounded-lg bg-slate-50 p-3 text-xs dark:bg-slate-800/60">
        <p><strong>{{ statusLabel(request.estado) }}</strong> · {{ request.motivo }}</p>
        <p class="mt-1 text-slate-500">{{ request.items.map(item => `${item.cantidad} × ${item.nombre_producto}`).join(', ') }}</p>
        <p v-if="request.comentario_resolucion" class="mt-1 text-slate-600 dark:text-slate-300">Respuesta: {{ request.comentario_resolucion }}</p>
      </div>
      <p v-if="errors.load" class="mt-2 text-xs text-rose-600">{{ errors.load }}</p>
    </div>

    <div v-if="isAdmin" class="space-y-3">
      <h2 class="text-lg font-extrabold text-slate-900 dark:text-white">Solicitudes de devolución</h2>
      <div v-if="loading" class="text-sm text-slate-500">Cargando solicitudes…</div>
      <div v-else-if="!requests.length" class="rounded-xl border border-dashed p-5 text-sm text-slate-500">No hay solicitudes de devolución.</div>
      <article v-for="request in requests" :key="request.id" class="space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <div class="flex flex-wrap items-center justify-between gap-2"><div><p class="font-mono text-xs font-bold text-emerald-800 dark:text-emerald-300">{{ request.ordenes?.codigo_orden || request.orden_id }}</p><p class="text-xs text-slate-500">{{ request.motivo }}</p></div><span class="rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">{{ statusLabel(request.estado) }}</span></div>
        <ul class="list-inside list-disc text-xs text-slate-600 dark:text-slate-300"><li v-for="item in request.items" :key="item.orden_item_id">{{ item.cantidad }} × {{ item.nombre_producto }} ({{ item.sku }})</li></ul>
        <div v-if="request.evidencia_urls?.length" class="flex flex-wrap gap-2"><a v-for="(url, index) in request.evidencia_urls" :key="url" :href="url" target="_blank" rel="noopener noreferrer" class="text-xs font-semibold text-blue-700 underline dark:text-blue-300">Ver evidencia {{ index + 1 }}</a></div>
        <p v-if="request.comentario_resolucion" class="text-xs text-slate-500">Comentario: {{ request.comentario_resolucion }}</p>
        <template v-if="request.estado === 'solicitada'"><textarea v-model="comments[request.id]" rows="2" maxlength="1000" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-950" placeholder="Comentario (obligatorio si rechazas)"/><p v-if="errors[request.id]" class="text-xs text-rose-600">{{ errors[request.id] }}</p><div class="flex justify-end gap-2"><button type="button" class="rounded-lg border border-rose-300 px-3 py-2 text-xs font-bold text-rose-700" @click="resolve(request, 'rechazar')">Rechazar</button><button type="button" class="rounded-lg bg-emerald-800 px-3 py-2 text-xs font-bold text-white" @click="resolve(request, 'aprobar')">Aprobar</button></div></template>
      </article>
    </div>

    <div v-if="open" class="fixed inset-0 z-[95] flex items-center justify-center bg-slate-950/70 p-4" role="dialog" aria-modal="true" aria-label="Solicitar devolución"><form class="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900" @submit.prevent="submit"><div><h3 class="font-bold text-slate-900 dark:text-white">Solicitar devolución</h3><p class="text-xs text-slate-500">Orden {{ order?.codigo_orden }} · dentro de los 7 días posteriores a la entrega.</p></div><div class="space-y-2"><label v-for="item in returnableItems" :key="item.orden_item_id" class="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3 text-xs dark:border-slate-700"><span>{{ item.nombre_producto }} <span class="text-slate-400">(hasta {{ item.cantidad }})</span></span><input v-model.number="quantities[item.orden_item_id]" type="number" min="0" :max="item.cantidad" class="w-20 rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800" aria-label="Cantidad a devolver" /></label></div><label class="block text-xs font-semibold">Motivo<textarea v-model="reason" required minlength="3" maxlength="1000" rows="3" class="mt-1 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-950" /></label><label class="block text-xs font-semibold">Fotos de evidencia<input type="file" accept="image/*" multiple class="mt-1 block w-full text-xs" @change="selectedFiles = Array.from(($event.target as HTMLInputElement).files || []).slice(0, 5)"/><span class="text-slate-500">Hasta 5 imágenes, 5 MB por imagen.</span></label><p v-if="errors.form" role="alert" class="text-xs text-rose-600">{{ errors.form }}</p><div class="flex justify-end gap-2"><button type="button" class="rounded-lg px-3 py-2 text-xs font-semibold text-slate-600" @click="open = false">Cancelar</button><button type="submit" :disabled="saving" class="rounded-lg bg-emerald-800 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">{{ saving ? 'Enviando…' : 'Enviar solicitud' }}</button></div></form></div>
  </section>
</template>
