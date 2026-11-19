<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Mail, Save, RotateCcw, Loader2 } from 'lucide-vue-next';
import { useAuthStore } from '@/stores/auth';
import { getPreferenciasNotificacion, updatePreferenciasNotificacion } from '@/api/client';
import { notify } from '@/lib/feedback';

const auth = useAuthStore();
const correo = ref(true);
const cargando = ref(true);
const guardando = ref(false);
const error = ref('');
const actualizado = ref<string | null>(null);
const clienteId = computed(() => auth.user?.id);
async function cargar() {
  cargando.value = true;
  error.value = '';
  try {
    if (!clienteId.value) throw new Error('Inicia sesión para configurar tus notificaciones.');
    const p = await getPreferenciasNotificacion(clienteId.value);
    correo.value = p.canal_correo && p.avisos_estado_pedido;
    actualizado.value = p.updated_at || null;
  } catch (e: any) { error.value = e.response?.data?.detail || e.message || 'No se pudieron cargar tus preferencias.'; }
  finally { cargando.value = false; }
}
async function guardar() {
  if (!clienteId.value || guardando.value) return;
  guardando.value = true;
  error.value = '';
  try {
    const p = await updatePreferenciasNotificacion(clienteId.value, {
      canal_correo: correo.value,
      avisos_estado_pedido: correo.value,
      avisos_promociones: false,
      avisos_recordatorios: false,
    });
    actualizado.value = p.updated_at || null;
    notify.success('Preferencias de correo guardadas.');
  } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'No se pudieron guardar tus preferencias.'; }
  finally { guardando.value = false; }
}
function restablecer() { correo.value = true; }
onMounted(cargar);
</script>

<template>
  <section class="space-y-5">
    <header class="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
      <span class="rounded-xl bg-blue-50 p-3 text-blue-700 dark:bg-blue-950 dark:text-blue-300"><Mail class="h-6 w-6" /></span>
      <div><h2 class="text-lg font-bold text-slate-900 dark:text-white">Notificaciones por correo</h2><p class="mt-1 text-sm text-slate-500">Recibe las actualizaciones de tus pedidos en tu correo electrónico.</p></div>
    </header>
    <p v-if="error" role="alert" class="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{{ error }}</p>
    <div v-if="cargando" class="flex items-center justify-center gap-2 p-10 text-sm text-slate-500"><Loader2 class="h-5 w-5 animate-spin" /> Cargando preferencias…</div>
    <form v-else class="space-y-5" @submit.prevent="guardar">
      <label class="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <span><span class="block text-sm font-bold">Recibir correos electrónicos</span><span class="mt-1 block text-xs text-slate-500">{{ auth.user?.email }}</span></span>
        <input v-model="correo" type="checkbox" class="h-5 w-5 rounded text-blue-600" />
      </label>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <button type="button" :disabled="guardando" class="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm disabled:opacity-50" @click="restablecer"><RotateCcw class="h-4 w-4" /> Valores por defecto</button>
        <button :disabled="guardando" class="flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-40"><Loader2 v-if="guardando" class="h-4 w-4 animate-spin" /><Save v-else class="h-4 w-4" /> {{ guardando ? 'Guardando…' : 'Guardar preferencias' }}</button>
      </div>
      <p v-if="actualizado" class="text-xs text-slate-500">Última actualización: {{ new Date(actualizado).toLocaleString('es-BO') }}</p>
    </form>
  </section>
</template>
