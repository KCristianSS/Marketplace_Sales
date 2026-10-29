<script setup lang="ts">
import { computed, watch } from 'vue';
import { Banknote, CreditCard, QrCode, Plus, Trash2, Wand2, CheckCircle2, AlertCircle } from 'lucide-vue-next';
import type { MetodoPagoPos, TramoPagoPos } from '@/types';

/**
 * Pago dividido en caja: permite cobrar una venta con varios métodos
 * (p. ej. parte en efectivo, parte con tarjeta y el resto con QR).
 * Valida en vivo que la suma de los tramos iguale el total a cobrar.
 */
const props = defineProps<{ modelValue: TramoPagoPos[]; total: number }>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: TramoPagoPos[]): void;
  (e: 'validity', value: boolean): void;
}>();

const MAX_TRAMOS = 6;
const METODOS: { id: MetodoPagoPos; etiqueta: string; icono: any; activo: string }[] = [
  { id: 'efectivo', etiqueta: 'Efectivo', icono: Banknote, activo: 'border-emerald-600 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40' },
  { id: 'tarjeta', etiqueta: 'Tarjeta', icono: CreditCard, activo: 'border-blue-600 bg-blue-50 text-blue-700 dark:bg-blue-950/40' },
  { id: 'qr', etiqueta: 'QR', icono: QrCode, activo: 'border-purple-600 bg-purple-50 text-purple-700 dark:bg-purple-950/40' },
];

const aCentavos = (n: number | null | undefined) => Math.round(((Number(n) || 0) + Number.EPSILON) * 100);
const aBs = (centavos: number) => (centavos / 100).toFixed(2);

const totalCent = computed(() => aCentavos(props.total));
const asignadoCent = computed(() => props.modelValue.reduce((acc, t) => acc + aCentavos(t.monto), 0));
const restanteCent = computed(() => totalCent.value - asignadoCent.value);
const porcentaje = computed(() =>
  totalCent.value > 0 ? Math.min(100, Math.round((asignadoCent.value / totalCent.value) * 100)) : 0
);

/** Mensaje de error por tramo (null si es válido). */
function errorDeTramo(t: TramoPagoPos): string | null {
  if (!(aCentavos(t.monto) > 0)) return 'Ingresa un monto mayor a 0.';
  if (t.metodo === 'efectivo' && t.recibido !== null && aCentavos(t.recibido) < aCentavos(t.monto)) {
    return 'El efectivo recibido es menor al monto de este tramo.';
  }
  return null;
}

const cambioTotal = computed(() =>
  props.modelValue
    .filter((t) => t.metodo === 'efectivo' && t.recibido !== null && aCentavos(t.recibido) >= aCentavos(t.monto))
    .reduce((acc, t) => acc + aCentavos(t.recibido) - aCentavos(t.monto), 0)
);

const esValido = computed(
  () => props.modelValue.length >= 2 && restanteCent.value === 0 && props.modelValue.every((t) => errorDeTramo(t) === null)
);
watch(esValido, (v) => emit('validity', v), { immediate: true });

let contador = 0;
const nuevoId = () => `tramo-${Date.now()}-${contador++}`;

function agregarTramo() {
  if (props.modelValue.length >= MAX_TRAMOS) return;
  const usados = new Set(props.modelValue.map((t) => t.metodo));
  const metodo = (METODOS.find((m) => !usados.has(m.id)) ?? METODOS[0]).id;
  const monto = restanteCent.value > 0 ? restanteCent.value / 100 : null;
  emit('update:modelValue', [...props.modelValue, { id: nuevoId(), metodo, monto, referencia: '', recibido: null }]);
}

function quitarTramo(id: string) {
  if (props.modelValue.length <= 2) return;
  emit('update:modelValue', props.modelValue.filter((t) => t.id !== id));
}

/** Asigna a este tramo lo que falta (o descuenta el exceso) para cuadrar el total. */
function completarCon(t: TramoPagoPos) {
  const nuevo = aCentavos(t.monto) + restanteCent.value;
  t.monto = nuevo > 0 ? nuevo / 100 : null;
}

function cambiarMetodo(t: TramoPagoPos, metodo: MetodoPagoPos) {
  t.metodo = metodo;
  if (metodo !== 'efectivo') t.recibido = null;
  if (metodo !== 'tarjeta') t.referencia = '';
}
</script>

<template>
  <div class="space-y-3" data-testid="split-payment-panel">
    <!-- Resumen de avance -->
    <div class="p-3 rounded-xl border bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 space-y-2">
      <div class="grid grid-cols-3 text-center text-[11px]">
        <div><p class="text-slate-500">Total</p><p class="font-black text-sm text-slate-800 dark:text-white">BOB {{ aBs(totalCent) }}</p></div>
        <div><p class="text-slate-500">Asignado</p><p class="font-black text-sm text-slate-800 dark:text-white">BOB {{ aBs(asignadoCent) }}</p></div>
        <div>
          <p class="text-slate-500">{{ restanteCent < 0 ? 'Excede' : 'Falta' }}</p>
          <p class="font-black text-sm" :class="restanteCent === 0 ? 'text-emerald-600' : restanteCent < 0 ? 'text-rose-600' : 'text-amber-600'">
            BOB {{ aBs(Math.abs(restanteCent)) }}
          </p>
        </div>
      </div>
      <div class="h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
        <div class="h-full transition-all" :class="restanteCent < 0 ? 'bg-rose-500' : restanteCent === 0 ? 'bg-emerald-500' : 'bg-amber-500'" :style="{ width: porcentaje + '%' }"></div>
      </div>
      <p class="flex items-center gap-1 text-[11px] font-semibold" :class="esValido ? 'text-emerald-600' : 'text-slate-500'" role="status">
        <CheckCircle2 v-if="esValido" class="w-3.5 h-3.5" /><AlertCircle v-else class="w-3.5 h-3.5" />
        {{ esValido ? 'Pago completo: los tramos suman el total.' : restanteCent > 0 ? 'Asigna el monto restante para continuar.' : restanteCent < 0 ? 'Los tramos superan el total: reduce algún monto.' : 'Revisa los datos de cada tramo.' }}
      </p>
    </div>

    <!-- Tramos -->
    <div v-for="(t, i) in modelValue" :key="t.id" class="p-3 rounded-xl border border-slate-200 dark:border-slate-700 space-y-2.5">
      <div class="flex items-center justify-between">
        <span class="text-[11px] font-bold text-slate-500">PAGO {{ i + 1 }}</span>
        <button v-if="modelValue.length > 2" type="button" @click="quitarTramo(t.id)" class="p-1 text-slate-400 hover:text-rose-600 rounded" title="Quitar tramo">
          <Trash2 class="w-3.5 h-3.5" />
        </button>
      </div>

      <div class="grid grid-cols-3 gap-2">
        <button
          v-for="m in METODOS" :key="m.id" type="button" @click="cambiarMetodo(t, m.id)"
          :class="['py-2 rounded-lg border flex items-center justify-center gap-1.5 text-[11px] font-bold transition-all', t.metodo === m.id ? m.activo : 'border-slate-200 dark:border-slate-700 text-slate-500']"
        >
          <component :is="m.icono" class="w-4 h-4" /> {{ m.etiqueta }}
        </button>
      </div>

      <div class="flex items-center gap-2">
        <label class="text-[11px] font-semibold text-slate-600 dark:text-slate-300 w-14">Monto</label>
        <input
          v-model.number="t.monto" type="number" min="0" step="0.01" inputmode="decimal"
          class="flex-1 text-right font-bold p-1.5 text-sm bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-emerald-500"
        />
        <button type="button" @click="completarCon(t)" :disabled="restanteCent === 0"
                class="inline-flex items-center gap-1 px-2 py-1.5 text-[11px] font-semibold rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40"
                title="Asignar a este pago lo que falta para completar el total">
          <Wand2 class="w-3 h-3" /> Completar
        </button>
      </div>

      <div v-if="t.metodo === 'efectivo'" class="flex items-center gap-2">
        <label class="text-[11px] font-semibold text-slate-600 dark:text-slate-300 w-14">Recibido</label>
        <input
          v-model.number="t.recibido" type="number" min="0" step="1" inputmode="decimal" placeholder="Opcional"
          class="flex-1 text-right p-1.5 text-sm bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-emerald-500"
        />
        <span class="text-[11px] font-bold text-emerald-600 w-28 text-right">
          Cambio: BOB {{ t.recibido !== null && aCentavos(t.recibido) >= aCentavos(t.monto) ? aBs(aCentavos(t.recibido) - aCentavos(t.monto)) : '0.00' }}
        </span>
      </div>

      <div v-if="t.metodo === 'tarjeta'" class="flex items-center gap-2">
        <label class="text-[11px] font-semibold text-slate-600 dark:text-slate-300 w-14">Voucher</label>
        <input
          v-model="t.referencia" type="text" maxlength="4" inputmode="numeric" placeholder="Últimos 4 dígitos"
          class="flex-1 p-1.5 text-sm font-mono bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
        />
      </div>

      <p v-if="errorDeTramo(t) && (t.monto !== null || t.recibido !== null)" class="text-[11px] font-semibold text-rose-600">{{ errorDeTramo(t) }}</p>
    </div>

    <div class="flex items-center justify-between">
      <button type="button" @click="agregarTramo" :disabled="modelValue.length >= MAX_TRAMOS"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-bold rounded-lg border border-dashed border-slate-400 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40">
        <Plus class="w-3.5 h-3.5" /> Agregar otro pago
      </button>
      <span v-if="cambioTotal > 0" class="text-xs font-bold text-emerald-600">Cambio total a entregar: BOB {{ aBs(cambioTotal) }}</span>
    </div>
  </div>
</template>
