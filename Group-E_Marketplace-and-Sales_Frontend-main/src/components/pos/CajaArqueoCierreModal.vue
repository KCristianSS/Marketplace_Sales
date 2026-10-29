<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { 
  Calculator, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldAlert, 
  Printer, 
  Loader2, 
  X,
  CreditCard,
  QrCode,
  Banknote,
  FileSpreadsheet
} from 'lucide-vue-next';
import { cerrarCajaApi, obtenerCajaPorIdApi, listarMovimientosCajaApi } from '@/api/caja';
import type { CajaTurno, ArqueoCajaResultado } from '@/types';

const props = defineProps<{
  open: boolean;
  cajaId: string;
  cajeroNombre: string;
  sucursalNombre: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'closed', arqueo: ArqueoCajaResultado): void;
}>();

const cargando = ref(false);
const procesandoCierre = ref(false);
const errorMsg = ref('');

const cajaInfo = ref<CajaTurno | null>(null);
const montoReal = ref<number | ''>('');
const observaciones = ref('');
const arqueoCompletado = ref<ArqueoCajaResultado | null>(null);

const totalIngresosManuales = ref(0);
const totalEgresosManuales = ref(0);

async function cargarDatosCaja() {
  if (!props.cajaId) return;
  cargando.value = true;
  errorMsg.value = '';
  arqueoCompletado.value = null;

  try {
    const [caja, movimientos] = await Promise.all([
      obtenerCajaPorIdApi(props.cajaId),
      listarMovimientosCajaApi(props.cajaId)
    ]);
    cajaInfo.value = caja;

    let ingresos = 0;
    let egresos = 0;
    for (const m of movimientos) {
      if (m.tipo === 'ingreso') ingresos += Number(m.monto);
      if (m.tipo === 'egreso') egresos += Number(m.monto);
    }
    totalIngresosManuales.value = ingresos;
    totalEgresosManuales.value = egresos;

    // Por defecto sugerir el monto esperado para agilizar al cajero
    const esperado = Number(caja.fondo_inicial) + Number(caja.total_efectivo) + ingresos - egresos;
    montoReal.value = Number(esperado.toFixed(2));
  } catch (err: any) {
    console.error('Error al cargar datos para arqueo:', err);
    errorMsg.value = 'No se pudieron cargar los datos de la caja.';
  } finally {
    cargando.value = false;
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      observaciones.value = '';
      cargarDatosCaja();
    }
  }
);

const montoEsperadoEfectivo = computed(() => {
  if (!cajaInfo.value) return 0;
  return (
    Number(cajaInfo.value.fondo_inicial) +
    Number(cajaInfo.value.total_efectivo) +
    totalIngresosManuales.value -
    totalEgresosManuales.value
  );
});

const diferenciaCalculada = computed(() => {
  if (montoReal.value === '') return 0;
  return Number(montoReal.value) - montoEsperadoEfectivo.value;
});

const totalVentasGlobal = computed(() => {
  if (!cajaInfo.value) return 0;
  return (
    Number(cajaInfo.value.total_efectivo) +
    Number(cajaInfo.value.total_tarjeta) +
    Number(cajaInfo.value.total_qr)
  );
});

async function handleConfirmarCierre() {
  if (montoReal.value === '' || Number(montoReal.value) < 0) {
    errorMsg.value = 'Debes ingresar un monto físico válido contado en caja.';
    return;
  }

  procesandoCierre.value = true;
  errorMsg.value = '';

  try {
    const resultado = await cerrarCajaApi(props.cajaId, {
      monto_cierre_real: Number(montoReal.value),
      observaciones: observaciones.value.trim() || undefined
    });
    arqueoCompletado.value = resultado;
    emit('closed', resultado);
  } catch (err: any) {
    console.error('Error al cerrar caja:', err);
    errorMsg.value =
      err.response?.data?.detail ||
      err.response?.data?.error ||
      'Ocurrió un error al cerrar la caja y registrar el arqueo.';
  } finally {
    procesandoCierre.value = false;
  }
}

function imprimirComprobante() {
  window.print();
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-sm animate-fade-in"
  >
    <div
      class="relative w-full max-w-2xl max-h-[92vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl flex flex-col"
    >
      <!-- Header -->
      <div class="px-6 py-5 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white flex items-center justify-between shrink-0 border-b border-slate-800">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center border border-indigo-400/30">
            <Calculator class="w-5 h-5 text-indigo-300" />
          </div>
          <div>
            <h3 class="text-base font-bold">Arqueo y Cierre de Turno de Caja (RF-09)</h3>
            <p class="text-xs text-indigo-200/80">{{ sucursalNombre }} • {{ cajeroNombre }}</p>
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

      <!-- Pantalla de Éxito / Comprobante de Arqueo -->
      <div v-if="arqueoCompletado" class="p-6 overflow-y-auto space-y-6">
        <div class="text-center py-4 bg-emerald-50 dark:bg-emerald-950/40 rounded-2xl border border-emerald-200 dark:border-emerald-800/60 p-6">
          <div class="w-12 h-12 mx-auto mb-3 rounded-full bg-emerald-100 dark:bg-emerald-900/60 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 class="w-6 h-6" />
          </div>
          <h4 class="text-lg font-bold text-slate-900 dark:text-white">Caja Cerrada con Éxito</h4>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
            El turno ha sido finalizado y los totales quedaron asentados en el sistema contable.
          </p>
        </div>

        <!-- Ticket imprimible -->
        <div class="p-5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700 space-y-3 font-mono text-xs">
          <div class="border-b border-dashed border-slate-300 dark:border-slate-700 pb-2 text-center">
            <p class="font-bold text-sm">MAXICONECTA — COMPROBANTE DE ARQUEO</p>
            <p class="text-[11px] text-slate-500">{{ sucursalNombre }}</p>
            <p class="text-[10px] text-slate-400">Caja ID: {{ arqueoCompletado.caja_turno_id }}</p>
          </div>

          <div class="space-y-1.5 pt-1">
            <div class="flex justify-between">
              <span>Fondo Inicial:</span>
              <span class="font-bold">Bs. {{ Number(arqueoCompletado.fondo_inicial).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between">
              <span>Ventas Efectivo:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_efectivo).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>+ Ingresos Manuales:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_ingresos_manuales).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>- Egresos Manuales:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_egresos_manuales).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between border-t border-dashed border-slate-300 dark:border-slate-700 pt-1 font-bold">
              <span>Total Esperado en Gaveta:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_esperado).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between font-bold text-indigo-600 dark:text-indigo-400">
              <span>Monto Real Contado:</span>
              <span>Bs. {{ Number(arqueoCompletado.monto_cierre_real).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between border-t border-dashed border-slate-300 dark:border-slate-700 pt-1 font-bold">
              <span>Diferencia:</span>
              <span
                :class="Number(arqueoCompletado.diferencia) === 0 ? 'text-emerald-600' : Number(arqueoCompletado.diferencia) < 0 ? 'text-red-500' : 'text-amber-500'"
              >
                {{ Number(arqueoCompletado.diferencia) >= 0 ? '+' : '' }} Bs. {{ Number(arqueoCompletado.diferencia).toFixed(2) }}
              </span>
            </div>
          </div>

          <div class="border-t border-dashed border-slate-300 dark:border-slate-700 pt-2 space-y-1 text-slate-500">
            <div class="flex justify-between">
              <span>Ventas con Tarjeta:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_tarjeta).toFixed(2) }}</span>
            </div>
            <div class="flex justify-between">
              <span>Ventas con QR:</span>
              <span>Bs. {{ Number(arqueoCompletado.total_qr).toFixed(2) }}</span>
            </div>
          </div>

          <div v-if="arqueoCompletado.observaciones" class="border-t border-dashed border-slate-300 dark:border-slate-700 pt-2 text-[11px]">
            <span class="font-bold">Observaciones:</span> {{ arqueoCompletado.observaciones }}
          </div>
        </div>

        <div class="flex items-center justify-between pt-2">
          <button
            type="button"
            @click="imprimirComprobante"
            class="inline-flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold rounded-xl transition-all"
          >
            <Printer class="w-4 h-4" />
            <span>Imprimir Resumen</span>
          </button>
          <button
            type="button"
            @click="emit('close')"
            class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl shadow-lg transition-all"
          >
            Aceptar y Finalizar
          </button>
        </div>
      </div>

      <!-- Formulario de Arqueo -->
      <div v-else class="p-6 overflow-y-auto space-y-6">
        <div v-if="cargando" class="py-12 text-center text-slate-400 flex flex-col items-center gap-3">
          <Loader2 class="w-6 h-6 animate-spin text-indigo-500" />
          <p class="text-xs">Consolidando balance de caja...</p>
        </div>

        <div v-else-if="cajaInfo" class="space-y-5">
          <!-- Desglose de Totales del Sistema -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700/60">
              <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400">Fondo Inicial</span>
              <p class="text-sm font-bold text-slate-800 dark:text-slate-200 mt-0.5">
                Bs. {{ Number(cajaInfo.fondo_inicial).toFixed(2) }}
              </p>
            </div>
            <div class="p-3 bg-emerald-50/70 dark:bg-emerald-950/30 rounded-xl border border-emerald-200/60 dark:border-emerald-800/40">
              <span class="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">Ventas Efectivo</span>
              <p class="text-sm font-bold text-emerald-700 dark:text-emerald-300 mt-0.5">
                Bs. {{ Number(cajaInfo.total_efectivo).toFixed(2) }}
              </p>
            </div>
            <div class="p-3 bg-blue-50/70 dark:bg-blue-950/30 rounded-xl border border-blue-200/60 dark:border-blue-800/40">
              <span class="text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">Ventas Tarjeta</span>
              <p class="text-sm font-bold text-blue-700 dark:text-blue-300 mt-0.5">
                Bs. {{ Number(cajaInfo.total_tarjeta).toFixed(2) }}
              </p>
            </div>
            <div class="p-3 bg-purple-50/70 dark:bg-purple-950/30 rounded-xl border border-purple-200/60 dark:border-purple-800/40">
              <span class="text-[10px] font-bold uppercase tracking-wider text-purple-600 dark:text-purple-400">Ventas QR</span>
              <p class="text-sm font-bold text-purple-700 dark:text-purple-300 mt-0.5">
                Bs. {{ Number(cajaInfo.total_qr).toFixed(2) }}
              </p>
            </div>
          </div>

          <!-- Cuadro de Cálculo de Efectivo Esperado -->
          <div class="p-4 bg-slate-900 text-white rounded-2xl space-y-2 border border-slate-800">
            <div class="flex items-center justify-between text-xs text-slate-400">
              <span>Fondo Inicial + Ventas Efectivo:</span>
              <span class="font-mono">Bs. {{ (Number(cajaInfo.fondo_inicial) + Number(cajaInfo.total_efectivo)).toFixed(2) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs text-slate-400">
              <span>Movimientos Manuales Netos (+Ingresos / -Egresos):</span>
              <span class="font-mono" :class="totalIngresosManuales - totalEgresosManuales >= 0 ? 'text-emerald-400' : 'text-amber-400'">
                {{ totalIngresosManuales - totalEgresosManuales >= 0 ? '+' : '' }} Bs. {{ (totalIngresosManuales - totalEgresosManuales).toFixed(2) }}
              </span>
            </div>
            <div class="border-t border-slate-800 pt-2 flex items-center justify-between">
              <span class="text-xs font-bold text-slate-300">Total Esperado Físicamente en Gaveta:</span>
              <span class="text-lg font-mono font-bold text-cyan-300">Bs. {{ montoEsperadoEfectivo.toFixed(2) }}</span>
            </div>
          </div>

          <!-- Input de Efectivo Real Contado por el Cajero -->
          <div class="space-y-2">
            <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Efectivo Contado en Gaveta (Bs.)
            </label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-400 font-bold text-base">
                Bs.
              </span>
              <input
                v-model.number="montoReal"
                type="number"
                step="0.50"
                min="0"
                required
                class="w-full pl-12 pr-4 py-3 bg-white dark:bg-slate-800 border-2 border-slate-300 dark:border-slate-700 rounded-xl text-xl font-mono font-bold text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
                placeholder="0.00"
              />
            </div>
          </div>

          <!-- Indicador Dinámico de Cuadre / Diferencia -->
          <div
            class="p-4 rounded-xl border flex items-center justify-between transition-all"
            :class="
              diferenciaCalculada === 0
                ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-300 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
                : diferenciaCalculada < 0
                ? 'bg-red-50 dark:bg-red-950/40 border-red-300 dark:border-red-800 text-red-800 dark:text-red-300'
                : 'bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-300'
            "
          >
            <div class="flex items-center gap-2.5">
              <CheckCircle2 v-if="diferenciaCalculada === 0" class="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              <AlertTriangle v-else class="w-5 h-5" :class="diferenciaCalculada < 0 ? 'text-red-600' : 'text-amber-600'" />
              <div>
                <p class="text-xs font-bold uppercase tracking-wider">
                  {{ diferenciaCalculada === 0 ? 'Cuadre Exacto' : diferenciaCalculada < 0 ? 'Faltante en Caja' : 'Sobrante en Caja' }}
                </p>
                <p class="text-[11px] opacity-80">
                  {{ diferenciaCalculada === 0 ? 'Los montos físicos coinciden con el sistema al 100%' : 'Se registrará en el arqueo para revisión de supervisión' }}
                </p>
              </div>
            </div>
            <span class="text-base font-mono font-extrabold">
              {{ diferenciaCalculada >= 0 ? '+' : '' }} Bs. {{ diferenciaCalculada.toFixed(2) }}
            </span>
          </div>

          <!-- Observaciones / Justificación -->
          <div>
            <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
              Observaciones del Cierre (Opcional)
            </label>
            <textarea
              v-model="observaciones"
              rows="2"
              maxlength="500"
              placeholder="Notas sobre el turno, justificación de diferencias, novedades..."
              class="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:border-indigo-500"
            ></textarea>
          </div>

          <!-- Mensaje de error -->
          <div
            v-if="errorMsg"
            class="p-3 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/60 rounded-xl flex items-center gap-2 text-xs text-red-600 dark:text-red-400"
          >
            <ShieldAlert class="w-4 h-4 shrink-0" />
            <span>{{ errorMsg }}</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div v-if="!arqueoCompletado" class="px-6 py-4 bg-slate-50 dark:bg-slate-800/80 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between shrink-0">
        <button
          type="button"
          @click="emit('close')"
          :disabled="procesandoCierre"
          class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors cursor-pointer"
        >
          Cancelar
        </button>
        <button
          type="button"
          @click="handleConfirmarCierre"
          :disabled="procesandoCierre || cargando"
          class="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-700 hover:bg-indigo-600 active:scale-95 text-white text-xs font-bold rounded-xl shadow-lg shadow-indigo-700/25 transition-all cursor-pointer disabled:opacity-50"
        >
          <Loader2 v-if="procesandoCierre" class="w-4 h-4 animate-spin" />
          <Calculator v-else class="w-4 h-4" />
          <span>{{ procesandoCierre ? 'Procesando Arqueo...' : 'Confirmar Cierre de Caja' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
