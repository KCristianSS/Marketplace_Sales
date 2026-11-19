<script setup lang="ts">
import { ref } from 'vue';
import { Store, Banknote, ShieldAlert, CheckCircle2, Loader2, X } from 'lucide-vue-next';
import { abrirCajaApi } from '@/api/caja';
import type { CajaTurno } from '@/types';

const props = defineProps<{
  open: boolean;
  sucursalId: string;
  sucursalNombre: string;
  cajeroNombre: string;
  cajeroId?: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'opened', caja: CajaTurno): void;
}>();

const fondoInicial = ref<number>(200);
const guardando = ref(false);
const errorMsg = ref('');

const montosSugeridos = [100, 200, 300, 500];

function seleccionarMonto(monto: number) {
  fondoInicial.value = monto;
}

async function handleAbrirCaja() {
  if (fondoInicial.value < 0) {
    errorMsg.value = 'El fondo inicial no puede ser negativo.';
    return;
  }

  guardando.value = true;
  errorMsg.value = '';

  try {
    const caja = await abrirCajaApi({
      sucursal_id: props.sucursalId,
      cajero_id: props.cajeroId,
      fondo_inicial: Number(fondoInicial.value)
    });
    emit('opened', caja);
    emit('close');
  } catch (err: any) {
    console.error('Error al aperturar caja:', err);
    errorMsg.value =
      err.response?.data?.detail ||
      err.response?.data?.error ||
      'No se pudo aperturar la caja. Verifica la conexión o si ya cuentas con un turno activo.';
  } finally {
    guardando.value = false;
  }
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fade-in"
  >
    <div
      class="relative w-full max-w-lg overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl transition-all"
    >
      <!-- Banner Superior -->
      <div class="px-6 py-5 bg-gradient-to-r from-emerald-600 to-teal-700 text-white flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center border border-white/20">
            <Store class="w-5 h-5 text-emerald-100" />
          </div>
          <div>
            <h3 class="text-base font-bold">Apertura de Turno de Caja (RF-09)</h3>
            <p class="text-xs text-emerald-100/90">{{ sucursalNombre }}</p>
          </div>
        </div>
        <button
          type="button"
          @click="emit('close')"
          class="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors"
          title="Cerrar modal"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Contenido del Formulario -->
      <form @submit.prevent="handleAbrirCaja" class="p-6 space-y-5">
        <!-- Info del Cajero -->
        <div class="p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700/60 flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">Responsable:</span>
          <span class="text-xs font-bold text-slate-800 dark:text-slate-200">{{ cajeroNombre }}</span>
        </div>

        <!-- Entrada de Fondo Inicial -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
            Fondo Inicial en Gaveta (Bs.)
          </label>
          <div class="relative">
            <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-400 font-bold text-sm">
              Bs.
            </span>
            <input
              v-model.number="fondoInicial"
              type="number"
              step="0.50"
              min="0"
              required
              class="w-full pl-12 pr-4 py-3 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 rounded-xl text-lg font-bold text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500 transition-colors"
              placeholder="0.00"
            />
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
            Efectivo inicial para cambio con el que inicias este turno de trabajo.
          </p>
        </div>

        <!-- Botones rápidos de selección -->
        <div>
          <span class="block text-[11px] font-semibold text-slate-400 mb-2">Montos habituales de fondo inicial:</span>
          <div class="grid grid-cols-4 gap-2">
            <button
              v-for="m in montosSugeridos"
              :key="m"
              type="button"
              @click="seleccionarMonto(m)"
              :class="fondoInicial === m ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700'"
              class="py-2 px-3 text-xs font-bold rounded-lg border transition-all hover:border-emerald-500"
            >
              Bs. {{ m }}
            </button>
          </div>
        </div>

        <!-- Mensaje de Error si ocurre -->
        <div
          v-if="errorMsg"
          class="p-3 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/60 rounded-xl flex items-start gap-2.5 text-xs text-red-600 dark:text-red-400"
        >
          <ShieldAlert class="w-4 h-4 shrink-0 mt-0.5" />
          <span>{{ errorMsg }}</span>
        </div>

        <!-- Botones de Acción -->
        <div class="pt-2 flex items-center justify-end gap-3">
          <button
            type="button"
            @click="emit('close')"
            :disabled="guardando"
            class="px-4 py-2.5 text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            :disabled="guardando"
            class="inline-flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-xs font-bold rounded-xl shadow-lg shadow-emerald-600/25 transition-all disabled:opacity-50 cursor-pointer"
          >
            <Loader2 v-if="guardando" class="w-4 h-4 animate-spin" />
            <CheckCircle2 v-else class="w-4 h-4" />
            <span>{{ guardando ? 'Aperturando...' : 'Confirmar Apertura' }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
