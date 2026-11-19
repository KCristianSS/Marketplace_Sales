<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { CheckoutMetodoPago, DatosTarjeta } from '@/types';
import {
  QrCode,
  CreditCard,
  Sparkles,
  ShieldCheck,
  Lock,
  CheckCircle2,
  AlertCircle
} from 'lucide-vue-next';

const props = defineProps<{
  modelValue: CheckoutMetodoPago;
  totalMonto: number;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', val: CheckoutMetodoPago): void;
  (e: 'update:cardData', val: DatosTarjeta): void;
  (e: 'validation-change', isValid: boolean): void;
}>();

// Datos de tarjeta
const numeroTarjeta = ref('');
const nombreTitular = ref('');
const fechaVencimiento = ref('');
const cvv = ref('');

// Formateador de tarjeta en bloques de 4 dígitos
function onNumeroTarjetaInput(e: Event) {
  const target = e.target as HTMLInputElement;
  const digits = target.value.replace(/\D/g, '').slice(0, 16);
  const formatted = digits.replace(/(\d{4})(?=\d)/g, '$1 ');
  numeroTarjeta.value = formatted;
  emitirDatos();
}

// Formateador de fecha MM/YY
function onFechaInput(e: Event) {
  const target = e.target as HTMLInputElement;
  let digits = target.value.replace(/\D/g, '').slice(0, 4);
  if (digits.length >= 2) {
    digits = `${digits.slice(0, 2)}/${digits.slice(2)}`;
  }
  fechaVencimiento.value = digits;
  emitirDatos();
}

function onCvvInput(e: Event) {
  const target = e.target as HTMLInputElement;
  cvv.value = target.value.replace(/\D/g, '').slice(0, 4);
  emitirDatos();
}

function onNombreInput(e: Event) {
  const target = e.target as HTMLInputElement;
  nombreTitular.value = target.value.toUpperCase();
  emitirDatos();
}

// Detección visual de marca de tarjeta
const cardBrand = computed<'visa' | 'mastercard' | 'generic'>(() => {
  const raw = numeroTarjeta.value.replace(/\s/g, '');
  if (raw.startsWith('4')) return 'visa';
  if (/^5[1-5]/.test(raw) || /^2[2-7]/.test(raw)) return 'mastercard';
  return 'generic';
});

// Validación de tarjeta
const isCardValid = computed(() => {
  if (props.modelValue !== 'tarjeta') return true;
  const rawNum = numeroTarjeta.value.replace(/\s/g, '');
  const hasValidNum = rawNum.length >= 15 && rawNum.length <= 16;
  const hasValidName = nombreTitular.value.trim().length >= 3;
  const hasValidExp = /^(0[1-9]|1[0-2])\/\d{2}$/.test(fechaVencimiento.value);
  const hasValidCvv = cvv.value.length >= 3;
  return hasValidNum && hasValidName && hasValidExp && hasValidCvv;
});

function emitirDatos() {
  emit('update:cardData', {
    numero_tarjeta: numeroTarjeta.value.replace(/\s/g, ''),
    nombre_titular: nombreTitular.value.trim(),
    fecha_vencimiento: fechaVencimiento.value.trim(),
    cvv: cvv.value.trim()
  });
  emit('validation-change', isCardValid.value);
}

function selectMetodo(metodo: CheckoutMetodoPago) {
  emit('update:modelValue', metodo);
}

watch(() => props.modelValue, () => {
  emit('validation-change', isCardValid.value);
}, { immediate: true });
</script>

<template>
  <div class="space-y-4">
    <!-- Métodos de Pago: Grid de Selección Rápida -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
      <!-- Opción 1: QR Simple Interoperable -->
      <button
        type="button"
        @click="selectMetodo('qr')"
        :class="[
          'relative p-4 rounded-2xl border text-left transition-all duration-200 flex flex-col justify-between gap-3 group',
          modelValue === 'qr'
            ? 'border-blue-600 dark:border-blue-500 bg-blue-50/70 dark:bg-blue-950/40 ring-2 ring-blue-500/20 shadow-md'
            : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700'
        ]"
      >
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-900/60 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
            <QrCode class="w-5 h-5" />
          </div>
          <span
            v-if="modelValue === 'qr'"
            class="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs"
          >
            <CheckCircle2 class="w-4 h-4" />
          </span>
        </div>

        <div>
          <div class="flex items-center gap-1.5">
            <h4 class="font-extrabold text-xs sm:text-sm text-slate-900 dark:text-white">
              QR Simple
            </h4>
            <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-300">
              0% Comis.
            </span>
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
            BCP, BNB, Banco Unión y billeteras móviles.
          </p>
        </div>
      </button>

      <!-- Opción 2: Tarjeta de Crédito / Débito -->
      <button
        type="button"
        @click="selectMetodo('tarjeta')"
        :class="[
          'relative p-4 rounded-2xl border text-left transition-all duration-200 flex flex-col justify-between gap-3 group',
          modelValue === 'tarjeta'
            ? 'border-blue-600 dark:border-blue-500 bg-blue-50/70 dark:bg-blue-950/40 ring-2 ring-blue-500/20 shadow-md'
            : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700'
        ]"
      >
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-indigo-100 dark:bg-indigo-900/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center shrink-0">
            <CreditCard class="w-5 h-5" />
          </div>
          <span
            v-if="modelValue === 'tarjeta'"
            class="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs"
          >
            <CheckCircle2 class="w-4 h-4" />
          </span>
        </div>

        <div>
          <div class="flex items-center gap-1.5">
            <h4 class="font-extrabold text-xs sm:text-sm text-slate-900 dark:text-white">
              Tarjeta
            </h4>
            <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-950/80 dark:text-blue-300">
              Visa / MC
            </span>
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
            Cifrado TLS 1.3 con token seguro RIO-PAG-01.
          </p>
        </div>
      </button>

      <!-- Opción 3: Pasarela Externa -->
      <button
        type="button"
        @click="selectMetodo('pasarela')"
        :class="[
          'relative p-4 rounded-2xl border text-left transition-all duration-200 flex flex-col justify-between gap-3 group',
          modelValue === 'pasarela'
            ? 'border-blue-600 dark:border-blue-500 bg-blue-50/70 dark:bg-blue-950/40 ring-2 ring-blue-500/20 shadow-md'
            : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700'
        ]"
      >
        <div class="flex items-start justify-between">
          <div class="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/60 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
            <Sparkles class="w-5 h-5" />
          </div>
          <span
            v-if="modelValue === 'pasarela'"
            class="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs"
          >
            <CheckCircle2 class="w-4 h-4" />
          </span>
        </div>

        <div>
          <div class="flex items-center gap-1.5">
            <h4 class="font-extrabold text-xs sm:text-sm text-slate-900 dark:text-white">
              Pasarela
            </h4>
            <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300">
              Multi-canal
            </span>
          </div>
          <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
            Libélula, Red Enlace o PagoFácil corporativo.
          </p>
        </div>
      </button>
    </div>

    <!-- PANEL DINÁMICO SEGÚN MÉTODO DE PAGO SELECCIONADO -->
    <div class="bg-white dark:bg-slate-900/90 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 transition-all">
      <!-- 1. Vista previa / Información de QR Simple -->
      <div v-if="modelValue === 'qr'" class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 flex items-center justify-center text-blue-600 shrink-0">
          <QrCode class="w-7 h-7" />
        </div>
        <div class="space-y-1 text-xs">
          <p class="font-bold text-slate-900 dark:text-white flex items-center gap-2">
            Código QR Dinámico con Token Bancario
            <span class="px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300">
              RIO-PAG-01
            </span>
          </p>
          <p class="text-slate-500 dark:text-slate-400 text-[11px]">
            Al presionar <strong>"Confirmar y Pagar"</strong> se generará en pantalla un código QR dinámico timbrado por BOB {{ totalMonto.toFixed(2) }} con detección de pago en tiempo real.
          </p>
        </div>
      </div>

      <!-- 2. Formulario de Tarjeta de Crédito / Débito -->
      <div v-else-if="modelValue === 'tarjeta'" class="space-y-3">
        <div class="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
          <span class="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
            <Lock class="w-3.5 h-3.5 text-blue-600" /> Datos de la Tarjeta (Protegidos por Cifrado)
          </span>
          <div class="flex items-center gap-1.5 text-[10px] font-bold">
            <span :class="['px-2 py-0.5 rounded', cardBrand === 'visa' ? 'bg-blue-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-400']">
              VISA
            </span>
            <span :class="['px-2 py-0.5 rounded', cardBrand === 'mastercard' ? 'bg-amber-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-400']">
              MASTERCARD
            </span>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <!-- Número de Tarjeta -->
          <div class="sm:col-span-2">
            <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
              Número de Tarjeta (16 dígitos)
            </label>
            <div class="relative">
              <input
                :value="numeroTarjeta"
                @input="onNumeroTarjetaInput"
                type="text"
                placeholder="4532 8812 3456 7890"
                class="w-full px-3 py-2 text-xs font-mono rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <CreditCard class="w-4 h-4 text-slate-400 absolute right-3 top-2.5" />
            </div>
          </div>

          <!-- Nombre del Titular -->
          <div>
            <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
              Nombre en la Tarjeta
            </label>
            <input
              :value="nombreTitular"
              @input="onNombreInput"
              type="text"
              placeholder="JUAN PÉREZ"
              class="w-full px-3 py-2 text-xs uppercase rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-medium"
            />
          </div>

          <!-- Expiración y CVV -->
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
                Exp. (MM/AA)
              </label>
              <input
                :value="fechaVencimiento"
                @input="onFechaInput"
                type="text"
                placeholder="12/28"
                class="w-full px-3 py-2 text-xs font-mono text-center rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-600 dark:text-slate-300 mb-1">
                CVV / CVC
              </label>
              <input
                :value="cvv"
                @input="onCvvInput"
                type="password"
                placeholder="•••"
                class="w-full px-3 py-2 text-xs font-mono text-center rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        <div v-if="!isCardValid && (numeroTarjeta || nombreTitular || fechaVencimiento || cvv)" class="flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400">
          <AlertCircle class="w-3.5 h-3.5 shrink-0" />
          <span>Completa los 16 dígitos, nombre del titular, fecha MM/AA y código CVV de 3 dígitos.</span>
        </div>
      </div>

      <!-- 3. Pasarela Externa de Pagos -->
      <div v-else class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-2xl bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 flex items-center justify-center text-amber-600 shrink-0">
          <Sparkles class="w-7 h-7" />
        </div>
        <div class="space-y-1 text-xs">
          <p class="font-bold text-slate-900 dark:text-white">
            Pasarela Bancaria Unificada (Libélula / Cybersource)
          </p>
          <p class="text-slate-500 dark:text-slate-400 text-[11px]">
            Al continuar serás transferido con un token cifrado de cobro para abonar mediante banca por internet de cualquier entidad del sistema financiero nacional.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
