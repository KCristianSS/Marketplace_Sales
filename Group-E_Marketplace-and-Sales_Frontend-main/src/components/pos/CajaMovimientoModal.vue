<script setup lang="ts">
import { ref, watch } from 'vue';
import { 
  ArrowDownLeft, 
  ArrowUpRight, 
  Banknote, 
  PlusCircle, 
  MinusCircle, 
  ShieldAlert, 
  Loader2, 
  X,
  History
} from 'lucide-vue-next';
import { registrarMovimientoCajaApi, listarMovimientosCajaApi } from '@/api/caja';
import type { MovimientoCaja } from '@/types';

const props = defineProps<{
  open: boolean;
  cajaId: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'movement-added'): void;
}>();

const tipo = ref<'ingreso' | 'egreso'>('ingreso');
const monto = ref<number | ''>('');
const descripcion = ref('');
const guardando = ref(false);
const cargandoHistorial = ref(false);
const errorMsg = ref('');
const movimientos = ref<MovimientoCaja[]>([]);

async function cargarMovimientos() {
  if (!props.cajaId) return;
  cargandoHistorial.value = true;
  try {
    movimientos.value = await listarMovimientosCajaApi(props.cajaId);
  } catch (err) {
    console.error('Error al listar movimientos de caja:', err);
  } finally {
    cargandoHistorial.value = false;
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      monto.value = '';
      descripcion.value = '';
      errorMsg.value = '';
      cargarMovimientos();
    }
  }
);

async function handleRegistrar() {
  if (!monto.value || Number(monto.value) <= 0) {
    errorMsg.value = 'El monto debe ser mayor a 0.';
    return;
  }
  if (!descripcion.value.trim()) {
    errorMsg.value = 'Por favor ingresa el motivo o justificación del movimiento.';
    return;
  }

  guardando.value = true;
  errorMsg.value = '';

  try {
    await registrarMovimientoCajaApi(props.cajaId, {
      tipo: tipo.value,
      monto: Number(monto.value),
      descripcion: descripcion.value.trim()
    });
    
    monto.value = '';
    descripcion.value = '';
    await cargarMovimientos();
    emit('movement-added');
  } catch (err: any) {
    console.error('Error al registrar movimiento:', err);
    errorMsg.value =
      err.response?.data?.detail ||
      err.response?.data?.error ||
      'No se pudo registrar el movimiento.';
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
      class="relative w-full max-w-xl max-h-[90vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl flex flex-col"
    >
      <!-- Header -->
      <div class="px-6 py-5 bg-gradient-to-r from-cyan-700 to-blue-800 text-white flex items-center justify-between shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center border border-white/20">
            <Banknote class="w-5 h-5 text-cyan-200" />
          </div>
          <div>
            <h3 class="text-base font-bold">Movimientos Manuales de Caja (RF-09)</h3>
            <p class="text-xs text-cyan-200/90">Registro de ingresos y retiros de efectivo</p>
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

      <!-- Contenido scrolleable -->
      <div class="p-6 overflow-y-auto space-y-6">
        <!-- Formulario de nuevo movimiento -->
        <form @submit.prevent="handleRegistrar" class="space-y-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
          <span class="block text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
            Nuevo Movimiento
          </span>

          <!-- Selector de Tipo -->
          <div class="grid grid-cols-2 gap-3">
            <button
              type="button"
              @click="tipo = 'ingreso'"
              :class="tipo === 'ingreso' ? 'bg-emerald-600 text-white border-emerald-600 ring-2 ring-emerald-400/40' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700'"
              class="py-2.5 px-4 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <ArrowDownLeft class="w-4 h-4 text-emerald-300" />
              <span>Ingreso (+)</span>
            </button>
            <button
              type="button"
              @click="tipo = 'egreso'"
              :class="tipo === 'egreso' ? 'bg-amber-600 text-white border-amber-600 ring-2 ring-amber-400/40' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700'"
              class="py-2.5 px-4 rounded-xl border font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer"
            >
              <ArrowUpRight class="w-4 h-4 text-amber-300" />
              <span>Retiro / Egreso (-)</span>
            </button>
          </div>

          <!-- Campos Monto y Motivo -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div class="sm:col-span-1">
              <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
                Monto (Bs.)
              </label>
              <div class="relative">
                <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-slate-400 text-xs font-bold">
                  Bs.
                </span>
                <input
                  v-model.number="monto"
                  type="number"
                  step="0.50"
                  min="0.10"
                  required
                  placeholder="0.00"
                  class="w-full pl-9 pr-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-sm font-bold text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div class="sm:col-span-2">
              <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
                Motivo / Descripción
              </label>
              <input
                v-model="descripcion"
                type="text"
                maxlength="200"
                required
                placeholder="Ej. Ingreso de cambio, retiro parcial de seguridad..."
                class="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <!-- Error si ocurre -->
          <div
            v-if="errorMsg"
            class="p-2.5 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/60 rounded-lg flex items-center gap-2 text-xs text-red-600 dark:text-red-400"
          >
            <ShieldAlert class="w-4 h-4 shrink-0" />
            <span>{{ errorMsg }}</span>
          </div>

          <!-- Botón Registrar -->
          <div class="flex justify-end pt-1">
            <button
              type="submit"
              :disabled="guardando"
              class="inline-flex items-center gap-2 px-4 py-2 bg-cyan-700 hover:bg-cyan-600 active:scale-95 text-white text-xs font-bold rounded-lg shadow transition-all cursor-pointer disabled:opacity-50"
            >
              <Loader2 v-if="guardando" class="w-3.5 h-3.5 animate-spin" />
              <PlusCircle v-else class="w-3.5 h-3.5" />
              <span>{{ guardando ? 'Registrando...' : 'Registrar Movimiento' }}</span>
            </button>
          </div>
        </form>

        <!-- Historial de Movimientos de este turno -->
        <div>
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <History class="w-4 h-4 text-slate-500" />
              <h4 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">
                Movimientos Registrados en este Turno
              </h4>
            </div>
            <span class="text-xs text-slate-400">Total: {{ movimientos.length }}</span>
          </div>

          <div v-if="cargandoHistorial" class="py-8 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
            <Loader2 class="w-4 h-4 animate-spin text-cyan-500" />
            <span>Cargando movimientos...</span>
          </div>

          <div v-else-if="movimientos.length === 0" class="py-8 text-center bg-slate-50 dark:bg-slate-800/30 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-xs text-slate-400">
            No se han registrado ingresos ni egresos manuales en esta caja.
          </div>

          <div v-else class="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden divide-y divide-slate-100 dark:divide-slate-800 max-h-60 overflow-y-auto">
            <div
              v-for="m in movimientos"
              :key="m.id"
              class="p-3 bg-white dark:bg-slate-900 flex items-center justify-between gap-3 text-xs"
            >
              <div class="flex items-center gap-2.5">
                <span
                  :class="m.tipo === 'ingreso' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400'"
                  class="p-1.5 rounded-lg shrink-0"
                >
                  <ArrowDownLeft v-if="m.tipo === 'ingreso'" class="w-3.5 h-3.5" />
                  <ArrowUpRight v-else class="w-3.5 h-3.5" />
                </span>
                <div>
                  <p class="font-bold text-slate-800 dark:text-slate-200">{{ m.descripcion }}</p>
                  <p class="text-[10px] text-slate-400">
                    {{ m.tipo === 'ingreso' ? 'Ingreso de efectivo' : 'Retiro de efectivo' }}
                    <span v-if="m.created_at"> • {{ new Date(m.created_at).toLocaleTimeString() }}</span>
                  </p>
                </div>
              </div>
              <div class="text-right shrink-0">
                <span
                  :class="m.tipo === 'ingreso' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'"
                  class="font-mono font-bold"
                >
                  {{ m.tipo === 'ingreso' ? '+' : '-' }} Bs. {{ Number(m.monto).toFixed(2) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 bg-slate-50 dark:bg-slate-800/80 border-t border-slate-200 dark:border-slate-700 flex justify-end shrink-0">
        <button
          type="button"
          @click="emit('close')"
          class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors cursor-pointer"
        >
          Cerrar
        </button>
      </div>
    </div>
  </div>
</template>
