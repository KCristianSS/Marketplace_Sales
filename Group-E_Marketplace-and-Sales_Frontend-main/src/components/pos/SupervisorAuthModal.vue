<script setup lang="ts">
import { useNotificationMessage } from '@/lib/feedback';
import { ref, computed, watch } from 'vue';
import { autorizarDescuentoManual, type AutorizacionDescuentoResponse } from '@/api/pos';
import { 
  ShieldCheck, 
  Lock, 
  UserCheck, 
  AlertTriangle, 
  X, 
  CheckCircle2, 
  Percent, 
  DollarSign, 
  FileText,
  KeyRound,
  RotateCcw,
  Sparkles
} from 'lucide-vue-next';

interface Props {
  isOpen: boolean;
  tipo: 'item' | 'total';
  itemSku?: string;
  itemNombre?: string;
  montoBase: number; // Precio del ítem o subtotal de la venta
  cajeroNombre?: string;
  sucursalId?: string;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'authorized', auth: AutorizacionDescuentoResponse): void;
}>();

// Datos del formulario
const supervisorUsername = ref('supervisor');
const pin = ref('');
const porcentaje = ref<number>(10);
const motivoSeleccionado = ref('Empaque dañado o deteriorado en almacén');
const motivoDetalle = ref('');
const showKeypad = ref(false);

// Estado de petición y errores
const isSubmitting = ref(false);
const errorMessage = ref('');
const successMessage = useNotificationMessage<string>('success', '');
const intentosFallidosInfo = ref('');

// Motivos frecuentes predefinidos
const MOTIVOS_DISPONIBLES = [
  'Empaque dañado o deteriorado en almacén',
  'Promoción o autorización excepcional de gerencia',
  'Producto en última unidad / exhibición de vitrina',
  'Fidelización cliente corporativo o especial',
  'Defecto estético menor (no compromete funcionamiento)',
  'Otro motivo justificado (especificar detalle)'
];

const PRESETS_PORCENTAJE = [5, 10, 15, 20, 30];

// Cálculo de montos
const montoDescuentoCalculado = computed(() => {
  const p = Number(porcentaje.value) || 0;
  return Number(((props.montoBase * p) / 100).toFixed(2));
});

const nuevoMontoCalculado = computed(() => {
  return Math.max(0, props.montoBase - montoDescuentoCalculado.value);
});

// Validación de tope máximo del 30% (Criterio 3)
const superaTope = computed(() => {
  return (Number(porcentaje.value) || 0) > 30;
});

const motivoFinal = computed(() => {
  if (motivoSeleccionado.value.startsWith('Otro')) {
    return motivoDetalle.value.trim() ? `Otro: ${motivoDetalle.value.trim()}` : 'Otro motivo justificado';
  }
  return motivoDetalle.value.trim() 
    ? `${motivoSeleccionado.value} - ${motivoDetalle.value.trim()}`
    : motivoSeleccionado.value;
});

const canSubmit = computed(() => {
  return (
    !superaTope.value &&
    (Number(porcentaje.value) || 0) > 0 &&
    supervisorUsername.value.trim().length >= 2 &&
    pin.value.trim().length >= 4 &&
    motivoFinal.value.trim().length >= 3 &&
    !isSubmitting.value
  );
});

// Reset al abrir
watch(() => props.isOpen, (val) => {
  if (val) {
    pin.value = '';
    errorMessage.value = '';
    successMessage.value = '';
    intentosFallidosInfo.value = '';
    if (!porcentaje.value || porcentaje.value <= 0) {
      porcentaje.value = 10;
    }
  }
});

function appendPinDigit(digit: string) {
  if (pin.value.length < 8) {
    pin.value += digit;
  }
}

function clearPin() {
  pin.value = '';
}

function backspacePin() {
  pin.value = pin.value.slice(0, -1);
}

async function solicitarAutorizacion() {
  if (!canSubmit.value) return;

  errorMessage.value = '';
  successMessage.value = '';
  intentosFallidosInfo.value = '';
  isSubmitting.value = true;

  try {
    const res = await autorizarDescuentoManual({
      supervisor_username: supervisorUsername.value.trim(),
      pin: pin.value.trim(),
      tipo: props.tipo,
      porcentaje: Number(porcentaje.value),
      monto_base: props.montoBase,
      motivo: motivoFinal.value,
      item_sku: props.tipo === 'item' ? props.itemSku : undefined,
      cajero_nombre: props.cajeroNombre,
      sucursal_id: props.sucursalId,
    });

    successMessage.value = res.mensaje;
    // Emitir tras breve pausa visual para confirmar autorización
    setTimeout(() => {
      emit('authorized', res);
      emit('close');
    }, 700);
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.response?.data?.error || 'Error al validar autorización de supervisor.';
    errorMessage.value = detail;
    if (detail.includes('intento(s)')) {
      intentosFallidosInfo.value = detail;
    }
    pin.value = '';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
    <div class="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl p-5 sm:p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4 animate-in fade-in max-h-[95vh] overflow-y-auto">

      <!-- Cabecera de Seguridad y Supervisor -->
      <div class="flex justify-between items-start border-b border-slate-100 dark:border-slate-800 pb-3">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-500">
            <ShieldCheck class="w-6 h-6" />
          </div>
          <div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
              <span>Autorización de Descuento Manual</span>
              <span class="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300/40">
                Supervisor
              </span>
            </h3>
            <p class="text-xs text-slate-500">
              {{ tipo === 'item' ? `Descuento excepcional por ítem: ${itemNombre || itemSku}` : 'Descuento global sobre el total del ticket' }}
            </p>
          </div>
        </div>
        <button 
          @click="emit('close')" 
          class="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          type="button"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Resumen del Ítem o Venta Base -->
      <div class="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-700 flex justify-between items-center text-xs">
        <div>
          <span class="text-slate-400 block text-[10px] uppercase font-bold">
            {{ tipo === 'item' ? 'Ítem seleccionado' : 'Base imponible' }}
          </span>
          <span class="font-bold text-slate-900 dark:text-white text-sm">
            {{ tipo === 'item' ? `${itemNombre} (${itemSku})` : 'Total Venta en Mostrador' }}
          </span>
        </div>
        <div class="text-right">
          <span class="text-slate-400 block text-[10px] uppercase font-bold">Precio / Base</span>
          <span class="font-mono font-bold text-slate-900 dark:text-white text-sm">BOB {{ montoBase.toFixed(2) }}</span>
        </div>
      </div>

      <!-- Configuración del Descuento & Tope 30% -->
      <div class="space-y-3">
        <div class="flex justify-between items-center">
          <label class="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1">
            <Percent class="w-3.5 h-3.5 text-teal-600" />
            Porcentaje de Descuento Solicitado:
          </label>
          <span class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
            Tope máx: 30%
          </span>
        </div>

        <!-- Presets rápidos -->
        <div class="grid grid-cols-5 gap-1.5">
          <button
            v-for="p in PRESETS_PORCENTAJE"
            :key="p"
            type="button"
            @click="porcentaje = p"
            :class="[
              'py-1.5 text-xs font-bold rounded-lg border transition-all text-center',
              porcentaje === p
                ? 'bg-teal-600 text-white border-teal-600 shadow-sm'
                : 'bg-slate-50 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-teal-500'
            ]"
          >
            {{ p }}%
          </button>
        </div>

        <!-- Input numérico directo -->
        <div class="relative">
          <input
            v-model.number="porcentaje"
            type="number"
            min="1"
            max="100"
            step="0.5"
            placeholder="Ingresa porcentaje (ej: 15)"
            class="w-full pl-3 pr-10 py-2 text-sm bg-white dark:bg-slate-900 border rounded-xl outline-none font-bold"
            :class="superaTope ? 'border-rose-500 focus:ring-rose-500' : 'border-slate-300 dark:border-slate-700 focus:border-teal-500'"
          />
          <span class="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-400">%</span>
        </div>

        <!-- Alerta de rechazo si supera el 30% (Criterio 3) -->
        <div v-if="superaTope" class="p-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs font-semibold">
          <AlertTriangle class="w-4 h-4 shrink-0 text-rose-600" />
          <span>El descuento solicitado ({{ porcentaje }}%) supera el tope máximo permitido del 30% fijado en política comercial.</span>
        </div>

        <!-- Cálculo en tiempo real -->
        <div class="p-3 bg-teal-50 dark:bg-teal-950/30 rounded-xl border border-teal-200 dark:border-teal-800 flex justify-between items-center text-xs">
          <div>
            <span class="text-teal-800 dark:text-teal-300 font-bold block">Descuento a descontar:</span>
            <span class="text-emerald-600 font-black text-sm font-mono">-BOB {{ montoDescuentoCalculado.toFixed(2) }}</span>
          </div>
          <div class="text-right">
            <span class="text-teal-800 dark:text-teal-300 font-bold block">Importe resultante:</span>
            <span class="text-slate-900 dark:text-white font-black text-sm font-mono">BOB {{ nuevoMontoCalculado.toFixed(2) }}</span>
          </div>
        </div>
      </div>

      <!-- Motivo Obligatorio (Criterio 4) -->
      <div class="space-y-1.5">
        <label class="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1">
          <FileText class="w-3.5 h-3.5 text-blue-600" />
          Motivo Obligatorio del Descuento:
        </label>
        <select
          v-model="motivoSeleccionado"
          class="w-full text-xs p-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white outline-none"
        >
          <option v-for="m in MOTIVOS_DISPONIBLES" :key="m" :value="m">{{ m }}</option>
        </select>
        <input
          v-model="motivoDetalle"
          type="text"
          placeholder="Comentarios adicionales o detalle específico de justificación..."
          class="w-full text-xs p-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white outline-none"
        />
      </div>

      <!-- Validación de Supervisor y PIN Seguro -->
      <div class="p-3.5 bg-slate-50 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 text-xs font-bold text-slate-800 dark:text-slate-200">
            <Lock class="w-4 h-4 text-amber-500" />
            <span>Credenciales de Supervisor</span>
          </div>
          <button
            type="button"
            @click="showKeypad = !showKeypad"
            class="text-[11px] text-teal-600 hover:underline font-semibold"
          >
            {{ showKeypad ? 'Ocultar Teclado Táctil' : 'Usar Teclado Táctil' }}
          </button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <!-- Supervisor -->
          <div>
            <label class="text-[11px] font-semibold text-slate-500 block mb-1">Usuario Supervisor:</label>
            <div class="relative">
              <input
                v-model="supervisorUsername"
                type="text"
                placeholder="supervisor / admin / gerente"
                class="w-full text-xs font-bold p-2 pl-7 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 outline-none focus:border-teal-500"
              />
              <UserCheck class="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2" />
            </div>
            <div class="flex gap-1 mt-1 text-[10px]">
              <span class="text-slate-400">Atajos:</span>
              <button type="button" @click="supervisorUsername = 'supervisor'" class="text-teal-600 hover:underline">supervisor</button>
              <span class="text-slate-400">·</span>
              <button type="button" @click="supervisorUsername = 'admin'" class="text-teal-600 hover:underline">admin</button>
              <span class="text-slate-400">·</span>
              <button type="button" @click="supervisorUsername = 'gerente'" class="text-teal-600 hover:underline">gerente</button>
            </div>
          </div>

          <!-- PIN -->
          <div>
            <label class="text-[11px] font-semibold text-slate-500 block mb-1">PIN del Supervisor:</label>
            <div class="relative">
              <input
                v-model="pin"
                type="password"
                maxlength="8"
                placeholder="PIN (ej: 1234)"
                class="w-full text-xs font-mono font-bold tracking-widest p-2 pl-7 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 outline-none focus:border-amber-500 text-center"
              />
              <KeyRound class="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2" />
            </div>
            <p class="text-[10px] text-slate-400 mt-1">PIN de 4 dígitos (Demo: 1234 para supervisor, 4321 para admin)</p>
          </div>
        </div>

        <!-- Teclado Numérico Táctil Opcional para POS -->
        <div v-if="showKeypad" class="pt-2 border-t border-slate-200 dark:border-slate-700">
          <div class="grid grid-cols-3 gap-1.5 max-w-[220px] mx-auto">
            <button
              v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
              :key="d"
              type="button"
              @click="appendPinDigit(d)"
              class="h-9 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-xs font-bold hover:bg-slate-100 dark:hover:bg-slate-800 active:scale-95 transition-transform"
            >
              {{ d }}
            </button>
            <button
              type="button"
              @click="clearPin"
              class="h-9 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-600 text-xs font-bold hover:bg-rose-100"
            >
              C
            </button>
            <button
              type="button"
              @click="appendPinDigit('0')"
              class="h-9 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-xs font-bold hover:bg-slate-100"
            >
              0
            </button>
            <button
              type="button"
              @click="backspacePin"
              class="h-9 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-600 text-xs font-bold"
            >
              ←
            </button>
          </div>
        </div>
      </div>

      <!-- Alertas de Error / Éxito -->
      <div v-if="errorMessage" class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 flex items-center gap-2 text-rose-700 dark:text-rose-300 text-xs font-semibold">
        <AlertTriangle class="w-4 h-4 shrink-0 text-rose-600" />
        <span>{{ errorMessage }}</span>
      </div>



      <!-- Footer y Acciones -->
      <div class="flex justify-between items-center pt-2 border-t border-slate-100 dark:border-slate-800">
        <span class="text-[11px] text-slate-400">
          * La autorización es de 1 solo uso y expira en 2 minutos.
        </span>
        <div class="flex gap-2">
          <button
            type="button"
            @click="emit('close')"
            class="px-3.5 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl"
          >
            Cancelar
          </button>
          <button
            type="button"
            @click="solicitarAutorizacion"
            :disabled="!canSubmit"
            class="px-5 py-2 text-xs font-bold rounded-xl text-white shadow-md flex items-center gap-1.5 transition-all"
            :class="canSubmit ? 'bg-amber-600 hover:bg-amber-700 shadow-amber-900/20 active:scale-95' : 'bg-slate-300 dark:bg-slate-800 cursor-not-allowed text-slate-500'"
          >
            <ShieldCheck class="w-4 h-4" />
            <span>{{ isSubmitting ? 'Verificando PIN...' : 'Autorizar Descuento' }}</span>
          </button>
        </div>
      </div>

    </div>
  </div>
</template>
