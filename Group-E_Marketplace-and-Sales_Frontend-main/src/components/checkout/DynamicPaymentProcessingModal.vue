<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import QRCode from 'qrcode';
import { pagosApi } from '@/api/pagos';
import type { IniciarPagoResponse, TransaccionPagoResponse } from '@/types';
import {
  QrCode,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  RefreshCw,
  ExternalLink,
  Loader2,
  X,
  CreditCard,
  Sparkles,
  Zap
} from 'lucide-vue-next';

const props = defineProps<{
  pagoData: IniciarPagoResponse;
  nombreCliente: string;
}>();

const emit = defineEmits<{
  (e: 'approved', tx: TransaccionPagoResponse): void;
  (e: 'rejected', motivo: string): void;
  (e: 'cancel'): void;
}>();

const qrDataUrl = ref<string>('');
const isCopied = ref(false);
const secondsLeft = ref(props.pagoData.expira_en_segundos || 900);
const currentStatus = ref<'pendiente' | 'aprobado' | 'rechazado'>(props.pagoData.estado);
const motivoRechazo = ref<string>('');
const isSimulating = ref(false);
const isPolling = ref(true);

let timerInterval: any = null;
let pollInterval: any = null;

// Generar QR dinámico como Data URL
async function generarQR() {
  if (props.pagoData.qr_payload) {
    try {
      qrDataUrl.value = await QRCode.toDataURL(props.pagoData.qr_payload, {
        width: 280,
        margin: 2,
        color: {
          dark: '#0f172a',
          light: '#ffffff'
        }
      });
    } catch (e) {
      console.error('Error generando QR DataURL:', e);
    }
  }
}

// Cuenta regresiva
function iniciarTemporizador() {
  timerInterval = setInterval(() => {
    if (secondsLeft.value > 0) {
      secondsLeft.value--;
    } else {
      detenerTemporizador();
      currentStatus.value = 'rechazado';
      motivoRechazo.value = 'El tiempo límite de 15 minutos para efectuar el pago ha expirado.';
      emit('rejected', motivoRechazo.value);
    }
  }, 1000);
}

function detenerTemporizador() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = null;
}

const formattedTimeLeft = computed(() => {
  const m = Math.floor(secondsLeft.value / 60);
  const s = secondsLeft.value % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
});

// Polling de estado de transacción
function iniciarPolling() {
  pollInterval = setInterval(async () => {
    if (currentStatus.value !== 'pendiente') {
      detenerPolling();
      return;
    }
    try {
      const res = await pagosApi.consultarEstado(props.pagoData.transaccion_id);
      if (res.estado === 'aprobado') {
        currentStatus.value = 'aprobado';
        detenerPolling();
        detenerTemporizador();
        emit('approved', res);
      } else if (res.estado === 'rechazado') {
        currentStatus.value = 'rechazado';
        motivoRechazo.value = res.motivo_rechazo || 'Transacción rechazada por el banco o pasarela.';
        detenerPolling();
        detenerTemporizador();
        emit('rejected', motivoRechazo.value);
      }
    } catch (e) {
      // Continuar polling
    }
  }, 2500);
}

function detenerPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = null;
  isPolling.value = false;
}

// Copiar código o glosa
function copiarGlosa() {
  const text = `MAXI-PAGO|${props.pagoData.transaccion_id}|BOB ${props.pagoData.monto.toFixed(2)}`;
  navigator.clipboard.writeText(text);
  isCopied.value = true;
  setTimeout(() => {
    isCopied.value = false;
  }, 2000);
}

// Simulación de Webhooks bancarios (QA / Demostración)
async function simularRespuestaBancaria(resultado: 'aprobado' | 'rechazado') {
  isSimulating.value = true;
  try {
    const res = await pagosApi.simularWebhook(
      props.pagoData.transaccion_id,
      resultado,
      resultado === 'rechazado' ? 'Fondos insuficientes en la cuenta del cliente' : undefined
    );
    if (resultado === 'aprobado') {
      currentStatus.value = 'aprobado';
      detenerPolling();
      detenerTemporizador();
      emit('approved', {
        transaccion_id: props.pagoData.transaccion_id,
        token_pago: props.pagoData.token_pago,
        estado: 'aprobado',
        metodo_pago: props.pagoData.metodo_pago,
        monto: props.pagoData.monto,
        moneda: props.pagoData.moneda,
        codigo_autorizacion: res.transaccion_id,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      });
    } else {
      currentStatus.value = 'rechazado';
      motivoRechazo.value = 'Fondos insuficientes o timeout de pasarela bancaria.';
      detenerPolling();
      detenerTemporizador();
      emit('rejected', motivoRechazo.value);
    }
  } catch (e: any) {
    alert(`Error al simular webhook: ${e.message}`);
  } finally {
    isSimulating.value = false;
  }
}

onMounted(() => {
  generarQR();
  iniciarTemporizador();
  iniciarPolling();
});

onUnmounted(() => {
  detenerTemporizador();
  detenerPolling();
});
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in overflow-y-auto">
    <div class="relative w-full max-w-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-2xl overflow-hidden flex flex-col">
      <!-- Encabezado -->
      <header class="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/80 dark:bg-slate-900/80">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
            <QrCode v-if="pagoData.metodo_pago === 'qr'" class="w-5 h-5" />
            <CreditCard v-else-if="pagoData.metodo_pago === 'tarjeta'" class="w-5 h-5" />
            <Sparkles v-else class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-base font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
              Procesamiento de Pago Digital
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                RIO-PAG-01
              </span>
            </h3>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              Token transaccional seguro emitido por la pasarela
            </p>
          </div>
        </div>

        <button
          @click="emit('cancel')"
          class="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Cancelar transacción"
        >
          <X class="w-5 h-5" />
        </button>
      </header>

      <!-- Barra de tiempo y estado de transacción -->
      <div class="px-6 py-3 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="relative flex h-2.5 w-2.5">
            <span :class="['animate-ping absolute inline-flex h-full w-full rounded-full opacity-75', currentStatus === 'aprobado' ? 'bg-emerald-400' : currentStatus === 'rechazado' ? 'bg-rose-400' : 'bg-blue-400']"></span>
            <span :class="['relative inline-flex rounded-full h-2.5 w-2.5', currentStatus === 'aprobado' ? 'bg-emerald-500' : currentStatus === 'rechazado' ? 'bg-rose-500' : 'bg-blue-500']"></span>
          </span>
          <span class="text-xs font-bold text-slate-700 dark:text-slate-300">
            <span v-if="currentStatus === 'aprobado'" class="text-emerald-600 dark:text-emerald-400">¡Pago Confirmado!</span>
            <span v-else-if="currentStatus === 'rechazado'" class="text-rose-600 dark:text-rose-400">Pago Rechazado</span>
            <span v-else>Esperando abono bancario...</span>
          </span>
        </div>

        <div class="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 px-3 py-1 rounded-xl border border-slate-200 dark:border-slate-700">
          <Clock class="w-3.5 h-3.5 text-blue-600" />
          <span>{{ formattedTimeLeft }}</span>
        </div>
      </div>

      <!-- Contenido Principal -->
      <div class="p-6 space-y-6">
        <!-- CASO 1: ESTADO APROBADO -->
        <div v-if="currentStatus === 'aprobado'" class="py-8 text-center space-y-4">
          <div class="w-16 h-16 mx-auto rounded-3xl bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shadow-lg border border-emerald-200 dark:border-emerald-800 animate-bounce">
            <CheckCircle2 class="w-8 h-8" />
          </div>
          <div>
            <h4 class="text-lg font-black text-slate-900 dark:text-white">
              ¡Transacción Aprobada Exitosamente!
            </h4>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
              La pasarela bancaria ha validado la liquidación. Emitiendo orden oficial y factura electrónica...
            </p>
          </div>
        </div>

        <!-- CASO 2: ESTADO RECHAZADO -->
        <div v-else-if="currentStatus === 'rechazado'" class="py-6 text-center space-y-4">
          <div class="w-16 h-16 mx-auto rounded-3xl bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 flex items-center justify-center shadow-lg border border-rose-200 dark:border-rose-800">
            <AlertTriangle class="w-8 h-8" />
          </div>
          <div class="space-y-1">
            <h4 class="text-lg font-black text-slate-900 dark:text-white">
              Pago No Completado
            </h4>
            <p class="text-xs text-rose-600 dark:text-rose-400 font-medium">
              {{ motivoRechazo || 'La entidad bancaria rechazó la transacción.' }}
            </p>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 pt-1">
              Tu reserva de stock temporal continúa activa. Puedes reintentar o seleccionar otro método.
            </p>
          </div>
          <div class="pt-2 flex justify-center gap-3">
            <button
              @click="emit('cancel')"
              class="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow transition-colors"
            >
              Cambiar Método de Pago
            </button>
          </div>
        </div>

        <!-- CASO 3: ESTADO PENDIENTE (QR DINÁMICO O PASARELA) -->
        <div v-else class="space-y-6">
          <!-- Vista de QR Dinámico -->
          <div v-if="pagoData.metodo_pago === 'qr'" class="flex flex-col items-center gap-4">
            <!-- QR Canvas Wrapper -->
            <div class="relative p-4 bg-white dark:bg-slate-800 rounded-3xl border-2 border-slate-200 dark:border-slate-700 shadow-xl flex flex-col items-center">
              <img
                v-if="qrDataUrl"
                :src="qrDataUrl"
                alt="QR Dinámico de Pago"
                class="w-56 h-56 rounded-xl object-contain"
              />
              <div v-else class="w-56 h-56 flex items-center justify-center">
                <Loader2 class="w-8 h-8 text-blue-600 animate-spin" />
              </div>

              <!-- Badge central con branding -->
              <div class="mt-2 text-center">
                <span class="text-[11px] font-black uppercase text-slate-800 dark:text-slate-200 tracking-wider">
                  QR Simple · Interoperable
                </span>
              </div>
            </div>

            <!-- Desglose de Pago -->
            <div class="text-center space-y-1">
              <p class="text-xs text-slate-500 dark:text-slate-400">Total a Pagar:</p>
              <p class="text-2xl font-black text-blue-600 dark:text-blue-400">
                BOB {{ pagoData.monto.toFixed(2) }}
              </p>
              <p class="text-[11px] text-slate-500">
                Abono inmediato a: <strong class="text-slate-700 dark:text-slate-300">MaxiConecta Bolivia S.R.L.</strong>
              </p>
            </div>

            <!-- Botón Copiar Glosa -->
            <button
              @click="copiarGlosa"
              type="button"
              class="px-4 py-2 text-xs font-semibold rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 flex items-center gap-2 transition-colors border border-slate-200 dark:border-slate-700"
            >
              <Check v-if="isCopied" class="w-4 h-4 text-emerald-600" />
              <Copy v-else class="w-4 h-4" />
              <span>{{ isCopied ? '¡Glosa Copiada!' : 'Copiar Glosa de Referencia' }}</span>
            </button>
          </div>

          <!-- Vista de Pasarela Externa -->
          <div v-else-if="pagoData.metodo_pago === 'pasarela'" class="p-6 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-200 dark:border-slate-700 text-center space-y-4">
            <div class="w-14 h-14 mx-auto rounded-2xl bg-amber-100 dark:bg-amber-950/60 text-amber-600 flex items-center justify-center">
              <Sparkles class="w-7 h-7" />
            </div>
            <div class="space-y-1">
              <h4 class="font-bold text-sm text-slate-900 dark:text-white">
                Redirección a Pasarela Segura
              </h4>
              <p class="text-xs text-slate-500 dark:text-slate-400">
                Haz clic en el enlace para abrir la pasarela de pago bancaria externa en una nueva pestaña.
              </p>
            </div>
            <a
              v-if="pagoData.redirect_url"
              :href="pagoData.redirect_url"
              target="_blank"
              class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-900 font-extrabold text-xs shadow-lg transition-all"
            >
              Abrir Pasarela de Pago <ExternalLink class="w-4 h-4" />
            </a>
          </div>

          <!-- Metadata de la Transacción RIO-PAG-01 -->
          <div class="p-3.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-200 dark:border-slate-700 text-[11px] space-y-1.5">
            <div class="flex justify-between text-slate-500">
              <span>Token Transaccional:</span>
              <span class="font-mono font-bold text-slate-800 dark:text-slate-200">{{ pagoData.token_pago }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>N° Transacción:</span>
              <span class="font-mono text-slate-700 dark:text-slate-300">{{ pagoData.transaccion_id }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>Cifrado y Seguridad:</span>
              <span class="text-emerald-600 font-semibold flex items-center gap-1">
                <ShieldCheck class="w-3.5 h-3.5" /> TLS 1.3 / Verificado
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- HERRAMIENTAS DE PRUEBA Y SIMULACIÓN DE WEBHOOK (DEV / QA) -->
      <footer class="px-6 py-3.5 bg-slate-100/90 dark:bg-slate-950/80 border-t border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
        <div class="flex items-center gap-1.5 text-slate-500 dark:text-slate-400 text-[11px]">
          <Zap class="w-3.5 h-3.5 text-amber-500" />
          <span>Simulador de Webhook Bancario:</span>
        </div>

        <div class="flex items-center gap-2 w-full sm:w-auto">
          <button
            type="button"
            @click="simularRespuestaBancaria('aprobado')"
            :disabled="isSimulating || currentStatus !== 'pendiente'"
            class="flex-1 sm:flex-initial px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-[11px] rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition-colors"
          >
            <Loader2 v-if="isSimulating" class="w-3 h-3 animate-spin" />
            <CheckCircle2 v-else class="w-3 h-3" />
            <span>Simular Aprobado</span>
          </button>

          <button
            type="button"
            @click="simularRespuestaBancaria('rechazado')"
            :disabled="isSimulating || currentStatus !== 'pendiente'"
            class="flex-1 sm:flex-initial px-3 py-1.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white font-bold text-[11px] rounded-lg shadow-sm flex items-center justify-center gap-1.5 transition-colors"
          >
            <AlertTriangle class="w-3 h-3" />
            <span>Simular Rechazo</span>
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
