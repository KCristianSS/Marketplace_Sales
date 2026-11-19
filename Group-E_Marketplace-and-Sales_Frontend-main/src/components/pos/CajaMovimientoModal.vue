<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ArrowDownLeft, ArrowUpRight, Banknote, PlusCircle, ShieldAlert, ShieldCheck, Loader2, X, History, Printer } from 'lucide-vue-next';
import { listarMovimientosCajaApi, obtenerTokenSupervisorApi, registrarMovimientoCajaApi } from '@/api/caja';
import { bs, imprimirDocumento } from '@/lib/imprimir';
import { htmlComprobanteMovimiento } from '@/lib/reportesCaja';
import type { MovimientoCaja, TipoMovimientoEfectivo } from '@/types';

/** KAN-342 — Entradas extraordinarias y retiros parciales a bóveda (motivo obligatorio + confirmación de supervisor). */
const props = defineProps<{
  open: boolean;
  cajaId: string;
  sucursalNombre?: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'movement-added'): void;
}>();

const LIMITE_POR_DEFECTO = 2000;

const tipo = ref<TipoMovimientoEfectivo>('entrada');
const monto = ref<number | ''>('');
const motivo = ref('');
const guardando = ref(false);
const cargandoHistorial = ref(false);
const errorMsg = ref('');
const movimientos = ref<MovimientoCaja[]>([]);
const ultimo = ref<MovimientoCaja | null>(null);

// Confirmación del supervisor (cuando el retiro supera el límite)
const pideSupervisor = ref(false);
const limite = ref<number>(LIMITE_POR_DEFECTO);
const supEmail = ref('');
const supPassword = ref('');

const motivoValido = computed(() => motivo.value.trim().length >= 3);

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

function limpiarFormulario() {
  monto.value = '';
  motivo.value = '';
  errorMsg.value = '';
  pideSupervisor.value = false;
  supEmail.value = '';
  supPassword.value = '';
}

watch(
  () => props.open,
  (abierto) => {
    if (abierto) {
      limpiarFormulario();
      ultimo.value = null;
      cargarMovimientos();
    }
  }
);

watch(tipo, () => {
  pideSupervisor.value = false;
  errorMsg.value = '';
});

function mensajeError(err: any): string {
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return 'Revisa los datos: el monto debe ser mayor a 0 y el motivo es obligatorio.';
  return err.message || 'No se pudo registrar el movimiento.';
}

async function handleRegistrar() {
  if (!monto.value || Number(monto.value) <= 0) {
    errorMsg.value = 'El monto debe ser mayor a 0.';
    return;
  }
  if (!motivoValido.value) {
    errorMsg.value = 'El motivo es obligatorio (mínimo 3 caracteres).';
    return;
  }
  guardando.value = true;
  errorMsg.value = '';
  try {
    let supervisor_token: string | undefined;
    if (pideSupervisor.value) {
      if (!supEmail.value || !supPassword.value) {
        errorMsg.value = 'El supervisor debe ingresar su correo y contraseña.';
        return;
      }
      supervisor_token = await obtenerTokenSupervisorApi(supEmail.value.trim(), supPassword.value);
    }
    const mov = await registrarMovimientoCajaApi(props.cajaId, {
      tipo: tipo.value,
      monto: Number(monto.value),
      motivo: motivo.value.trim(),
      supervisor_token
    });
    ultimo.value = mov;
    limpiarFormulario();
    await cargarMovimientos();
    emit('movement-added');
  } catch (err: any) {
    const detail = err.response?.data?.detail;
    if (err.response?.status === 428 && detail?.codigo === 'SUPERVISOR_REQUERIDO') {
      pideSupervisor.value = true;
      limite.value = Number(detail.limite) || LIMITE_POR_DEFECTO;
      errorMsg.value = detail.mensaje;
    } else if (pideSupervisor.value && err.response?.status === 401 && !detail?.codigo) {
      errorMsg.value = 'Credenciales del supervisor incorrectas.';
    } else {
      errorMsg.value = mensajeError(err);
    }
  } finally {
    guardando.value = false;
    supPassword.value = '';
  }
}

function imprimir(m: MovimientoCaja) {
  if (m.comprobante) {
    imprimirDocumento(`Comprobante ${m.numero_comprobante}`, htmlComprobanteMovimiento(m.comprobante, props.sucursalNombre || '-'));
  }
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm" data-testid="modal-movimientos">
    <div class="relative w-full max-w-xl max-h-[90vh] overflow-hidden bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl flex flex-col">
      <div class="px-6 py-5 bg-gradient-to-r from-cyan-700 to-blue-800 text-white flex items-center justify-between shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center border border-white/20"><Banknote class="w-5 h-5 text-cyan-200" /></div>
          <div>
            <h3 class="text-base font-bold">Movimientos de efectivo</h3>
            <p class="text-xs text-cyan-200/90">Entradas de cambio y retiros a bóveda</p>
          </div>
        </div>
        <button type="button" class="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10" title="Cerrar" @click="emit('close')"><X class="w-5 h-5" /></button>
      </div>

      <div class="p-6 overflow-y-auto space-y-6">
        <form class="space-y-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700" @submit.prevent="handleRegistrar">
          <span class="block text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Nuevo movimiento</span>

          <div class="grid grid-cols-2 gap-3">
            <button type="button" data-testid="tipo-entrada" :class="tipo === 'entrada' ? 'bg-emerald-600 text-white border-emerald-600 ring-2 ring-emerald-400/40' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700'" class="py-2.5 px-4 rounded-xl border font-bold text-xs flex items-center justify-center gap-2" @click="tipo = 'entrada'">
              <ArrowDownLeft class="w-4 h-4" /> Entrada de cambio (+)
            </button>
            <button type="button" data-testid="tipo-retiro" :class="tipo === 'retiro' ? 'bg-amber-600 text-white border-amber-600 ring-2 ring-amber-400/40' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700'" class="py-2.5 px-4 rounded-xl border font-bold text-xs flex items-center justify-center gap-2" @click="tipo = 'retiro'">
              <ArrowUpRight class="w-4 h-4" /> Retiro a bóveda (−)
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">Monto (Bs.)</label>
              <input v-model.number="monto" type="number" step="0.01" min="0.01" required placeholder="0.00" data-testid="mov-monto" class="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-sm font-bold focus:outline-none focus:border-cyan-500" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">Motivo <span class="text-red-500">*</span></label>
              <input v-model="motivo" type="text" maxlength="255" required placeholder="Ej. Cambio adicional / Exceso de efectivo en gaveta" data-testid="mov-motivo" class="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500" />
            </div>
          </div>

          <p v-if="tipo === 'retiro'" class="text-[11px] text-slate-500">
            Los retiros mayores a {{ bs(limite) }} requieren la confirmación de un supervisor. No se puede retirar más del efectivo disponible en la gaveta.
          </p>

          <!-- Confirmación del supervisor -->
          <div v-if="pideSupervisor" class="p-3 rounded-xl border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 space-y-2" data-testid="panel-supervisor">
            <div class="flex items-center gap-2 text-xs font-bold text-amber-800 dark:text-amber-300"><ShieldCheck class="w-4 h-4" /> Confirmación del supervisor</div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input v-model="supEmail" type="email" autocomplete="off" placeholder="Correo del supervisor" data-testid="sup-email" class="px-3 py-2 text-sm bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg" />
              <input v-model="supPassword" type="password" autocomplete="new-password" placeholder="Contraseña" data-testid="sup-password" class="px-3 py-2 text-sm bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg" />
            </div>
            <p class="text-[11px] text-amber-700 dark:text-amber-300">Las credenciales solo se usan para esta confirmación; no cambian tu sesión.</p>
          </div>

          <div v-if="errorMsg" class="p-2.5 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/60 rounded-lg flex items-center gap-2 text-xs text-red-600 dark:text-red-400" role="alert">
            <ShieldAlert class="w-4 h-4 shrink-0" /><span>{{ errorMsg }}</span>
          </div>

          <div class="flex justify-end">
            <button type="submit" :disabled="guardando || !motivoValido" data-testid="mov-registrar" class="inline-flex items-center gap-2 px-4 py-2 bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold rounded-lg shadow disabled:opacity-50">
              <Loader2 v-if="guardando" class="w-3.5 h-3.5 animate-spin" /><PlusCircle v-else class="w-3.5 h-3.5" />
              {{ guardando ? 'Registrando...' : pideSupervisor ? 'Confirmar y registrar' : 'Registrar movimiento' }}
            </button>
          </div>
        </form>

        <!-- Comprobante del último movimiento -->
        <div v-if="ultimo" class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900 flex items-center justify-between gap-3 text-xs" data-testid="movimiento-registrado">
          <div class="text-emerald-800 dark:text-emerald-300">
            <b>{{ ultimo.tipo === 'entrada' ? 'Entrada' : 'Retiro' }} registrado</b> · {{ bs(ultimo.monto) }}<br />
            Comprobante {{ ultimo.numero_comprobante }}
          </div>
          <button type="button" class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 text-white font-bold rounded-lg" @click="imprimir(ultimo)"><Printer class="w-3.5 h-3.5" /> Imprimir</button>
        </div>

        <!-- Historial -->
        <div>
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2"><History class="w-4 h-4 text-slate-500" /><h4 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Movimientos de este turno</h4></div>
            <span class="text-xs text-slate-400">Total: {{ movimientos.length }}</span>
          </div>
          <div v-if="cargandoHistorial" class="py-8 text-center text-slate-400 text-xs flex items-center justify-center gap-2"><Loader2 class="w-4 h-4 animate-spin text-cyan-500" /> Cargando...</div>
          <div v-else-if="movimientos.length === 0" class="py-8 text-center bg-slate-50 dark:bg-slate-800/30 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 text-xs text-slate-400">Aún no hay movimientos en este turno.</div>
          <div v-else class="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden divide-y divide-slate-100 dark:divide-slate-800 max-h-60 overflow-y-auto">
            <div v-for="m in movimientos" :key="m.id" class="p-3 bg-white dark:bg-slate-900 flex items-center justify-between gap-3 text-xs">
              <div class="flex items-center gap-2.5 min-w-0">
                <span :class="m.tipo === 'entrada' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/70 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-400'" class="p-1.5 rounded-lg shrink-0">
                  <ArrowDownLeft v-if="m.tipo === 'entrada'" class="w-3.5 h-3.5" /><ArrowUpRight v-else class="w-3.5 h-3.5" />
                </span>
                <div class="min-w-0">
                  <p class="font-bold text-slate-800 dark:text-slate-200 truncate">{{ m.motivo }}</p>
                  <p class="text-[10px] text-slate-400">
                    {{ m.numero_comprobante }}<span v-if="m.requiere_supervisor"> · con supervisor</span>
                    <span v-if="m.created_at"> · {{ new Date(m.created_at).toLocaleTimeString() }}</span>
                  </p>
                </div>
              </div>
              <div class="text-right shrink-0 flex items-center gap-2">
                <span :class="m.tipo === 'entrada' ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'" class="font-mono font-bold">{{ m.tipo === 'entrada' ? '+' : '−' }} {{ bs(m.monto) }}</span>
                <button type="button" class="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500" title="Imprimir comprobante" @click="imprimir(m)"><Printer class="w-3.5 h-3.5" /></button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="px-6 py-4 bg-slate-50 dark:bg-slate-800/80 border-t border-slate-200 dark:border-slate-700 flex justify-end shrink-0">
        <button type="button" class="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg" @click="emit('close')">Cerrar</button>
      </div>
    </div>
  </div>
</template>
