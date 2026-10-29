<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { AlertCircle, Check, CheckCircle2, Loader2, MessageSquareText, RefreshCw, Star, X } from 'lucide-vue-next';
import { listarResenasPendientes, moderarResena, type Resena } from '@/api/resenas';

const pendientes = ref<Resena[]>([]);
const motivos = ref<Record<string, string>>({});
const cargando = ref(false);
const procesandoId = ref<string | null>(null);
const error = ref('');
const mensaje = ref('');

async function cargar() {
  cargando.value = true;
  error.value = '';
  try {
    pendientes.value = await listarResenasPendientes();
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudieron cargar las reseñas pendientes.';
  } finally {
    cargando.value = false;
  }
}

async function moderar(resena: Resena, accion: 'aprobar' | 'rechazar') {
  const motivo = motivos.value[resena.id]?.trim();
  if (accion === 'rechazar' && !motivo) {
    error.value = 'Escribe un motivo para rechazar la reseña.';
    return;
  }
  procesandoId.value = resena.id;
  error.value = '';
  mensaje.value = '';
  try {
    await moderarResena(resena.id, { accion, motivo });
    pendientes.value = pendientes.value.filter(item => item.id !== resena.id);
    mensaje.value = accion === 'aprobar' ? 'Reseña aprobada y publicada.' : 'Reseña rechazada.';
    delete motivos.value[resena.id];
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo moderar la reseña.';
  } finally {
    procesandoId.value = null;
  }
}

onMounted(cargar);
</script>

<template>
  <section class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white"><MessageSquareText class="h-4 w-4 text-teal-700 dark:text-teal-400" /> Moderación de reseñas</h2>
        <p class="mt-1 text-xs text-slate-500">Solo las reseñas aprobadas aparecen públicamente en el producto.</p>
      </div>
      <button type="button" :disabled="cargando" class="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800" @click="cargar">
        <RefreshCw :class="['h-3.5 w-3.5', cargando ? 'animate-spin' : '']" /> Actualizar
      </button>
    </header>

    <p v-if="error" role="alert" class="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300"><AlertCircle class="h-4 w-4 shrink-0" /> {{ error }}</p>
    <p v-if="mensaje" role="status" class="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"><CheckCircle2 class="h-4 w-4 shrink-0" /> {{ mensaje }}</p>

    <div v-if="cargando" class="flex justify-center py-10 text-slate-500"><Loader2 class="h-5 w-5 animate-spin" /></div>
    <div v-else-if="pendientes.length" class="divide-y divide-slate-100 dark:divide-slate-800">
      <article v-for="resena in pendientes" :key="resena.id" class="grid gap-4 py-4 first:pt-0 lg:grid-cols-[1fr_260px]">
        <div class="min-w-0 space-y-2">
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">{{ resena.producto_nombre || `Producto ${resena.producto_id.slice(0, 8)}` }}</h3>
            <span v-if="resena.producto_sku" class="font-mono text-[10px] text-slate-400">{{ resena.producto_sku }}</span>
            <span class="text-[10px] text-slate-400">{{ resena.codigo_orden ? `Orden ${resena.codigo_orden}` : resena.orden_id ? `Orden ${resena.orden_id.slice(0, 8)}` : 'Sin orden vinculada' }}</span>
          </div>
          <div class="flex items-center gap-0.5 text-amber-500" :aria-label="`${resena.calificacion} de 5 estrellas`">
            <Star v-for="estrella in 5" :key="estrella" :class="['h-4 w-4', estrella <= resena.calificacion ? 'fill-current' : 'text-slate-300']" />
            <span class="ml-1.5 text-[10px] font-semibold text-slate-500">{{ resena.calificacion }}/5</span>
          </div>
          <p class="whitespace-pre-wrap text-xs leading-relaxed text-slate-700 dark:text-slate-300">{{ resena.comentario }}</p>
          <p class="text-[10px] text-slate-400">{{ resena.nombre_cliente || `Cliente ${resena.cliente_id.slice(0, 8)}` }} · {{ new Date(resena.created_at).toLocaleString('es-BO') }}</p>
        </div>
        <div class="space-y-2">
          <label class="block space-y-1">
            <span class="text-[10px] font-semibold text-slate-500">Motivo de rechazo (requerido para rechazar)</span>
            <textarea v-model="motivos[resena.id]" rows="2" maxlength="500" class="w-full resize-y rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-xs dark:border-slate-700 dark:bg-slate-800" placeholder="Describe el motivo"></textarea>
          </label>
          <div class="flex justify-end gap-2">
            <button type="button" :disabled="procesandoId === resena.id" class="inline-flex items-center gap-1 rounded-lg border border-rose-200 px-3 py-2 text-xs font-bold text-rose-700 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950/30" @click="moderar(resena, 'rechazar')">
              <X class="h-3.5 w-3.5" /> Rechazar
            </button>
            <button type="button" :disabled="procesandoId === resena.id" class="inline-flex items-center gap-1 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-800 disabled:opacity-50" @click="moderar(resena, 'aprobar')">
              <Loader2 v-if="procesandoId === resena.id" class="h-3.5 w-3.5 animate-spin" />
              <Check v-else class="h-3.5 w-3.5" /> Aprobar
            </button>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-xs text-slate-500 dark:border-slate-700">
      No hay reseñas pendientes de moderación.
    </div>
  </section>
</template>
