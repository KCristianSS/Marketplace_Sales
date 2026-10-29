<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { AlertCircle, CheckCircle2, Loader2, MessageSquareText, Star } from 'lucide-vue-next';
import { useAuthStore } from '@/stores/auth';
import {
  enviarResena,
  listarOrdenesElegibles,
  listarResenasAprobadas,
  type OrdenElegibleResena,
  type Resena
} from '@/api/resenas';

const props = defineProps<{ productoId: string }>();
const authStore = useAuthStore();
const resenas = ref<Resena[]>([]);
const ordenesElegibles = ref<OrdenElegibleResena[]>([]);
const ordenSeleccionada = ref('');
const calificacion = ref(5);
const comentario = ref('');
const cargando = ref(false);
const enviando = ref(false);
const error = ref('');
const exito = ref('');
const esCliente = computed(() => authStore.isAuthenticated && authStore.userRole === 'cliente');

async function cargar() {
  cargando.value = true;
  error.value = '';
  try {
    const tasks: Array<Promise<unknown>> = [listarResenasAprobadas(props.productoId).then(data => { resenas.value = data; })];
    if (esCliente.value) {
      tasks.push(listarOrdenesElegibles(props.productoId).then(data => {
        ordenesElegibles.value = data;
        if (!data.some(orden => orden.orden_id === ordenSeleccionada.value)) {
          ordenSeleccionada.value = data[0]?.orden_id || '';
        }
      }));
    } else {
      ordenesElegibles.value = [];
    }
    await Promise.all(tasks);
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudieron cargar las reseñas.';
  } finally {
    cargando.value = false;
  }
}

async function enviar() {
  if (!ordenSeleccionada.value || comentario.value.trim().length < 8) return;
  enviando.value = true;
  error.value = '';
  exito.value = '';
  try {
    await enviarResena({
      producto_id: props.productoId,
      orden_id: ordenSeleccionada.value,
      calificacion: calificacion.value,
      comentario: comentario.value.trim()
    });
    comentario.value = '';
    exito.value = 'Reseña enviada. Se publicará cuando el equipo la apruebe.';
    await cargar();
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'No se pudo enviar la reseña.';
  } finally {
    enviando.value = false;
  }
}

watch(() => [props.productoId, authStore.user?.id], cargar);
onMounted(cargar);
</script>

<template>
  <section class="space-y-4 border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
    <header class="flex items-center justify-between gap-3">
      <h4 class="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
        <MessageSquareText class="h-4 w-4 text-teal-700 dark:text-teal-400" /> Opiniones verificadas
      </h4>
      <span class="text-xs text-slate-500">{{ resenas.length }} aprobada(s)</span>
    </header>

    <p v-if="error" role="alert" class="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" /> {{ error }}
    </p>
    <p v-if="exito" role="status" class="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
      <CheckCircle2 class="h-4 w-4 shrink-0" /> {{ exito }}
    </p>

    <div v-if="cargando" class="flex items-center gap-2 py-3 text-xs text-slate-500"><Loader2 class="h-4 w-4 animate-spin" /> Cargando opiniones...</div>
    <div v-else-if="resenas.length" class="max-h-52 space-y-3 overflow-y-auto">
      <article v-for="resena in resenas" :key="resena.id" class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/70">
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-xs font-semibold text-slate-800 dark:text-slate-100">{{ resena.nombre_cliente || 'Cliente verificado' }}</p>
            <div class="mt-1 flex items-center gap-0.5 text-amber-500" :aria-label="`${resena.calificacion} de 5 estrellas`">
              <Star v-for="estrella in 5" :key="estrella" :class="['h-3.5 w-3.5', estrella <= resena.calificacion ? 'fill-current' : 'text-slate-300']" />
            </div>
          </div>
          <span class="text-[10px] text-slate-400">{{ new Date(resena.created_at).toLocaleDateString('es-BO') }}</span>
        </div>
        <p class="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-600 dark:text-slate-300">{{ resena.comentario }}</p>
      </article>
    </div>
    <p v-else-if="!cargando" class="rounded-lg bg-slate-50 px-3 py-4 text-center text-xs text-slate-500 dark:bg-slate-800/50">Aún no hay opiniones aprobadas para este producto.</p>

    <form v-if="esCliente" class="space-y-3 rounded-lg border border-teal-100 bg-teal-50/60 p-3 dark:border-teal-900/50 dark:bg-teal-950/20" @submit.prevent="enviar">
      <h5 class="text-xs font-bold text-slate-800 dark:text-slate-100">Califica una compra entregada</h5>
      <div v-if="ordenesElegibles.length" class="space-y-3">
        <label class="block space-y-1">
          <span class="text-[11px] font-semibold text-slate-600 dark:text-slate-300">Orden verificada</span>
          <select v-model="ordenSeleccionada" class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900">
            <option v-for="orden in ordenesElegibles" :key="orden.orden_id" :value="orden.orden_id">{{ orden.codigo_orden }} · Entregada {{ new Date(orden.entregada_el).toLocaleDateString('es-BO') }}</option>
          </select>
        </label>
        <div class="flex items-center gap-1" role="group" aria-label="Calificación del producto">
          <button v-for="estrella in 5" :key="estrella" type="button" :aria-label="`${estrella} estrellas`" :aria-pressed="calificacion === estrella" @click="calificacion = estrella">
            <Star :class="['h-6 w-6 transition-colors', estrella <= calificacion ? 'fill-amber-400 text-amber-500' : 'text-slate-300 hover:text-amber-400']" />
          </button>
          <span class="ml-2 text-xs font-semibold text-slate-500">{{ calificacion }}/5</span>
        </div>
        <label class="block space-y-1">
          <span class="text-[11px] font-semibold text-slate-600 dark:text-slate-300">Tu comentario</span>
          <textarea v-model="comentario" required minlength="8" maxlength="1500" rows="3" placeholder="¿Cómo fue tu experiencia con este producto?" class="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-900" />
        </label>
        <div class="flex items-center justify-between gap-3">
          <p class="text-[10px] text-slate-500">La opinión quedará pendiente hasta ser moderada.</p>
          <button type="submit" :disabled="enviando || !ordenSeleccionada || comentario.trim().length < 8" class="shrink-0 rounded-lg bg-teal-700 px-3 py-2 text-xs font-bold text-white hover:bg-teal-800 disabled:opacity-50">
            {{ enviando ? 'Enviando...' : 'Enviar reseña' }}
          </button>
        </div>
      </div>
      <p v-else class="text-xs text-slate-600 dark:text-slate-300">Solo puedes reseñar este producto después de recibir una orden que lo incluya.</p>
    </form>
  </section>
</template>
