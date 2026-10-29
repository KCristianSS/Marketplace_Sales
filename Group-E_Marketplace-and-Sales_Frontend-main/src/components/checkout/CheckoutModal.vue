<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useCartStore } from '@/stores/cart';
import CouponInput from '@/components/cart/CouponInput.vue';
import { useAuthStore } from '@/stores/auth';
import FiscalBillingForm from '@/components/FiscalBillingForm.vue';
import PaymentMethodSelector from './PaymentMethodSelector.vue';
import DynamicPaymentProcessingModal from './DynamicPaymentProcessingModal.vue';
import DeliveryMethodSelector from '@/components/DeliveryMethodSelector.vue';
import { pagosApi } from '@/api/pagos';
import { apiClient } from '@/api/client';
import type {
  CheckoutMetodoPago,
  DatosFiscales,
  DatosTarjeta,
  DireccionCliente,
  IniciarPagoResponse,
  SeleccionEntregaData,
  TransaccionPagoResponse
} from '@/types';
import {
  Clock,
  ShieldCheck,
  AlertTriangle,
  X,
  Truck,
  Store,
  CreditCard,
  QrCode,
  Lock,
  ChevronRight,
  RotateCcw,
  CheckCircle2,
  Copy,
  Check,
  Sparkles,
  MapPin,
  Loader2,
  PackageCheck,
  Tag,
  Printer,
  FileText,
  ExternalLink,
  Download
} from 'lucide-vue-next';

const router = useRouter();
const cartStore = useCartStore();
const authStore = useAuthStore();

// Estados del formulario de Checkout
const step = ref<'formulario' | 'exito'>('formulario');
const orderError = ref('');
const metodoPago = ref<CheckoutMetodoPago>('qr');
const notasEntrega = ref('');

// Entrega (RF-15) y libreta de direcciones (RF-23)
const entregaData = ref<SeleccionEntregaData>({
  tipo_despacho: 'domicilio',
  ciudad: 'La Paz',
  zona: 'Centro',
  direccion_exacta: '',
  referencia_entrega: '',
  tipo_envio: 'estandar',
  costo_flete: 0,
  flete_gratis: false,
  tiempo_estimado: '',
  sucursal_seleccionada: null
});
const isEntregaValid = ref(false);
const direccionesGuardadas = ref<DireccionCliente[]>([]);
const direccionGuardadaId = ref<string | null>(null);

const direccionGuardadaActiva = computed(() =>
  direccionesGuardadas.value.find((direccion) => direccion.id === direccionGuardadaId.value) || null
);

const entregaInicial = computed<Partial<SeleccionEntregaData>>(() => {
  const guardada = direccionGuardadaActiva.value;
  return guardada
    ? {
        tipo_despacho: entregaData.value.tipo_despacho,
        ciudad: guardada.ciudad,
        direccion_exacta: guardada.direccion,
        referencia_entrega: guardada.referencia || ''
      }
    : { tipo_despacho: entregaData.value.tipo_despacho };
});

async function cargarDireccionesGuardadas() {
  const clienteId = authStore.user?.id;
  direccionesGuardadas.value = [];
  direccionGuardadaId.value = null;
  if (!clienteId) return;
  try {
    const { data } = await apiClient.get<DireccionCliente[]>(`/api/v1/clientes/${clienteId}/direcciones`);
    direccionesGuardadas.value = Array.isArray(data) ? data : [];
    const predeterminada = direccionesGuardadas.value.find((direccion) => direccion.es_predeterminada)
      || direccionesGuardadas.value[0];
    direccionGuardadaId.value = predeterminada?.id || null;
  } catch {
    direccionesGuardadas.value = [];
  }
}

// Estados de pago (US-16 · RIO-PAG-01)
const cardData = ref<DatosTarjeta | null>(null);
const isPaymentMethodValid = ref(true);
const activePaymentData = ref<IniciarPagoResponse | null>(null);
const isPaymentProcessingModalOpen = ref(false);
const isProcessingPayment = ref(false);

const saldoPuntos = ref(0);
const puntosCanjeados = ref(0);
const puntosError = ref('');
const valorPuntoBob = ref(0.5);
const bobPorPuntoGanado = ref(10);
const descuentoPuntos = computed(() => puntosCanjeados.value * valorPuntoBob.value);
const maxPuntosCanjeables = computed(() => Math.min(saldoPuntos.value, Math.floor(cartStore.total / valorPuntoBob.value)));

async function cargarSaldoPuntos() {
  const clienteId = authStore.user?.id;
  saldoPuntos.value = 0;
  puntosCanjeados.value = 0;
  if (!clienteId) return;
  try {
    const { data } = await apiClient.get(`/v1/clientes/${clienteId}/fidelidad/puntos`);
    saldoPuntos.value = Math.max(0, Number(data?.puntos_saldo) || 0);
    valorPuntoBob.value = Math.max(0.01, Number(data?.valor_punto_bob) || 0.5);
    bobPorPuntoGanado.value = Math.max(1, Number(data?.regla_acumulacion_bob) || 10);
  } catch {
    saldoPuntos.value = authStore.pointsBalance;
  }
}

function aplicarPuntos() {
  puntosError.value = '';
  const cantidad = Math.floor(Number(puntosCanjeados.value) || 0);
  if (cantidad < 0 || cantidad > maxPuntosCanjeables.value) {
    puntosError.value = `Puedes canjear hasta ${maxPuntosCanjeables.value} puntos en esta compra.`;
    puntosCanjeados.value = Math.max(0, Math.min(cantidad, maxPuntosCanjeables.value));
    return;
  }
  puntosCanjeados.value = cantidad;
}

onMounted(() => {
  cargarSaldoPuntos();
  cargarDireccionesGuardadas();
});
watch(() => authStore.user?.id, () => {
  cargarSaldoPuntos();
  cargarDireccionesGuardadas();
});

// Datos simulados de tarjeta
const numeroTarjeta = ref('4532 •••• •••• 8892');
const nombreTitular = ref('CÉSAR LÓPEZ');
const fechaVencimiento = ref('08/28');
const cvv = ref('782');

// Copiar QR / Enlace
const isCopied = ref(false);

// Datos de Facturación Legal Electrónica (NIT / CI)
const fiscalData = ref<DatosFiscales>({
  modalidad: 'con_factura',
  tipo_documento: 'NIT',
  nit_ci: authStore.user?.nit_ci || '',
  razon_social: authStore.user?.razon_social || authStore.user?.nombre_completo || '',
  email_facturacion: authStore.user?.email || '',
  guardar_perfil: true
});

const isFiscalValid = ref(true);

function imprimirFactura() {
  window.print();
}

async function descargarComprobantePdf() {
  const orderId = cartStore.lastCreatedOrderId;
  if (!orderId) {
    orderError.value = 'No se encontró el identificador de la orden para descargar el comprobante.';
    return;
  }
  try {
    const { data } = await apiClient.get(`/v1/ordenes/${orderId}/comprobante.pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `comprobante-${cartStore.lastCreatedOrderCode || orderId}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error: any) {
    orderError.value = error.response?.data?.detail || 'No se pudo descargar el comprobante PDF.';
  }
}

const costoEnvio = computed(() => {
  const amount = Number(entregaData.value.costo_flete);
  return entregaData.value.tipo_despacho === 'domicilio' && Number.isFinite(amount) ? amount : 0;
});

const totalFinal = computed(() => {
  return Math.max(0, cartStore.total + costoEnvio.value - descuentoPuntos.value);
});

// Estilos dinámicos para el banner del temporizador
const bannerStyles = computed(() => {
  if (cartStore.isUrgentTimer) {
    return {
      wrapper: 'bg-rose-500/10 border-rose-500/40 text-rose-800 dark:text-rose-200',
      badge: 'bg-rose-600 text-white animate-pulse',
      progressBar: 'bg-rose-500',
      timerText: 'text-rose-600 dark:text-rose-400 font-extrabold animate-pulse'
    };
  }
  if (cartStore.isWarningTimer) {
    return {
      wrapper: 'bg-amber-500/10 border-amber-500/40 text-amber-800 dark:text-amber-200',
      badge: 'bg-amber-500 text-slate-900 font-bold',
      progressBar: 'bg-amber-500',
      timerText: 'text-amber-600 dark:text-amber-400 font-bold'
    };
  }
  return {
    wrapper: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-800 dark:text-emerald-200',
    badge: 'bg-emerald-600 text-white font-semibold',
    progressBar: 'bg-gradient-to-r from-emerald-500 to-blue-500',
    timerText: 'text-emerald-700 dark:text-emerald-300 font-bold'
  };
});

async function handleConfirmarOrden() {
  if (cartStore.reservaStatus === 'expirada') return;
  aplicarPuntos();

  if (!isEntregaValid.value) {
    orderError.value = entregaData.value.tipo_despacho === 'domicilio'
      ? 'Completa la dirección de entrega (mínimo 5 caracteres) para calcular el envío.'
      : 'Selecciona la sucursal donde retirarás tu compra.';
    return;
  }

  if (fiscalData.value.modalidad === 'con_factura' && !isFiscalValid.value) {
    alert('Por favor verifica el NIT/CI y la Razón Social antes de procesar el pago.');
    return;
  }

  if (metodoPago.value === 'tarjeta' && !isPaymentMethodValid.value) {
    alert('Por favor completa todos los datos requeridos de tu tarjeta (16 dígitos, titular, vencimiento y CVV).');
    return;
  }

  const clienteId = authStore.user?.id || 'cliente-anonimo';
  orderError.value = '';
  isProcessingPayment.value = true;

  try {
    // Iniciar cobro con pasarela digital y emisión de token (RIO-PAG-01)
    const initRes = await pagosApi.iniciarPago({
      monto: totalFinal.value,
      moneda: 'BOB',
      metodo_pago: metodoPago.value,
      cliente_id: clienteId,
      reserva_id: cartStore.reservaId || undefined,
      datos_tarjeta: metodoPago.value === 'tarjeta' && cardData.value ? cardData.value : undefined,
      descripcion: `MaxiConecta Orden - ${cartStore.itemCount} items`
    });

    // Para QR y Pasarela: Abrir pantalla de procesamiento y visualización de QR dinámico
    if (metodoPago.value === 'qr' || metodoPago.value === 'pasarela') {
      activePaymentData.value = initRes;
      isPaymentProcessingModalOpen.value = true;
      return;
    }

    // Para Tarjeta aprobada directamente:
    await completarOrdenFinal(initRes.transaccion_id);
  } catch (error: any) {
    orderError.value = error.response?.data?.detail || error.message || 'Error al procesar el pago digital.';
  } finally {
    isProcessingPayment.value = false;
  }
}

async function onPaymentApproved(tx: TransaccionPagoResponse) {
  isPaymentProcessingModalOpen.value = false;
  activePaymentData.value = null;
  await completarOrdenFinal(tx.transaccion_id);
}

function onPaymentRejected(motivo: string) {
  orderError.value = `Transacción rechazada: ${motivo}`;
}

async function completarOrdenFinal(transaccionId?: string) {
  const clienteId = authStore.user?.id || 'cliente-anonimo';
  const entrega = entregaData.value;
  const esDomicilio = entrega.tipo_despacho === 'domicilio';
  const guardada = direccionGuardadaActiva.value;
  const usaDireccionGuardada = esDomicilio && guardada !== null && guardada.direccion === entrega.direccion_exacta;
  try {
    await cartStore.finalizarOrdenConReserva(
      {
        tipo_despacho: entrega.tipo_despacho,
        metodo_pago: metodoPago.value,
        sucursal_id: esDomicilio ? undefined : entrega.sucursal_seleccionada?.id,
        direccion_entrega: esDomicilio ? `${entrega.direccion_exacta}, ${entrega.zona}, ${entrega.ciudad}` : undefined,
        direccion_entrega_id: usaDireccionGuardada ? guardada!.id : undefined,
        costo_envio: costoEnvio.value,
        puntos_canjeados: puntosCanjeados.value,
        descuento_puntos: descuentoPuntos.value,
        notas: notasEntrega.value,
        datos_fiscales: fiscalData.value,
        transaccion_id: transaccionId
      },
      clienteId
    );
    if (authStore.isAuthenticated) await authStore.fetchProfile();
    step.value = 'exito';
  } catch (error: any) {
    orderError.value = error.message;
  }
}

function handleCerrar() {
  if (step.value === 'exito') {
    cartStore.cancelarReserva();
    step.value = 'formulario';
    router.push('/mi-cuenta');
  } else {
    // Si aún tiene reserva activa, cancelarla y liberar stock
    if (confirm('¿Deseas salir del checkout? Se cancelará tu reserva y el stock volverá al inventario general.')) {
      cartStore.cancelarReserva();
    }
  }
}

function handleRenovarReserva() {
  const clienteId = authStore.user?.id || 'cliente-anonimo';
  cartStore.renovarReserva(clienteId);
}
</script>

<template>
  <!-- Modal Backdrop -->
  <div
    v-if="cartStore.isCheckoutModalOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/70 backdrop-blur-md overflow-y-auto animate-fade-in"
  >
    <div
      class="relative w-full max-w-4xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]"
    >
      <!-- Cabecera del Modal -->
      <header class="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50/80 dark:bg-slate-900/80 sticky top-0 z-10">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
            <Lock class="w-5 h-5" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base sm:text-lg font-extrabold text-slate-900 dark:text-white">
                Checkout Seguro · MaxiConecta
              </h2>
              
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              Compra rápida y protegida
            </p>
          </div>
        </div>

        <button
          @click="handleCerrar"
          class="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title="Cerrar y cancelar reserva"
        >
          <X class="w-5 h-5" />
        </button>
      </header>

      <!-- BANNER DE RESERVA TEMPORAL DE STOCK CON CONTADOR EN TIEMPO REAL -->
      <section
        v-if="step === 'formulario'"
        :class="['px-6 py-3.5 border-b transition-colors duration-300 flex flex-col gap-2', bannerStyles.wrapper]"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <!-- Información y estado -->
          <div class="flex items-center gap-2.5">
            <span :class="['px-2.5 py-1 rounded-full text-xs flex items-center gap-1.5 shadow-sm', bannerStyles.badge]">
              <Clock class="w-3.5 h-3.5" />
              <span v-if="cartStore.isUrgentTimer">¡Últimos Minutos!</span>
              <span v-else-if="cartStore.isWarningTimer">Por Vencer</span>
              <span v-else>Stock Bloqueado</span>
            </span>
            <div class="text-xs">
              <span class="font-semibold">Reserva activa:</span>
              <span class="ml-1 font-mono font-bold tracking-wider opacity-90">{{ cartStore.reservaId }}</span>
            </div>
          </div>

          <!-- Reloj Digital con Cuenta Regresiva -->
          <div class="flex items-center gap-2">
            <span class="text-xs opacity-80 hidden sm:inline">Tiempo para completar:</span>
            <div class="flex items-baseline gap-1 bg-white/60 dark:bg-slate-800/80 px-3 py-1 rounded-xl border border-black/5 dark:border-white/5 shadow-inner">
              <Clock class="w-4 h-4 opacity-70" />
              <span :class="['text-xl font-mono tracking-wider', bannerStyles.timerText]">
                {{ cartStore.formattedTimeLeft }}
              </span>
            </div>
          </div>
        </div>

        <!-- Barra de Progreso Decreciente -->
        <div class="w-full bg-black/10 dark:bg-white/10 h-1.5 rounded-full overflow-hidden">
          <div
            :class="['h-full transition-all duration-1000 ease-linear rounded-full', bannerStyles.progressBar]"
            :style="{ width: `${cartStore.timerProgressPercent}%` }"
          ></div>
        </div>

        <p class="text-[11px] opacity-75 flex items-center gap-1.5">
          <ShieldCheck class="w-3.5 h-3.5 shrink-0" />
          Tus productos están reservados temporalmente para que nadie te los quite mientras completas tu compra.
        </p>
      </section>

      <!-- CUERPO PRINCIPAL DEL CHECKOUT -->
      <div class="p-6 overflow-y-auto flex-1 space-y-6 relative">
        <!-- VISTA DE ÉXITO -->
        <div v-if="step === 'exito'" class="py-6 px-4 text-center space-y-5">
          <div class="w-16 h-16 mx-auto rounded-3xl bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shadow-lg border border-emerald-200 dark:border-emerald-800 animate-bounce">
            <CheckCircle2 class="w-8 h-8" />
          </div>

          <div class="space-y-1 max-w-md mx-auto">
            <h3 class="text-xl sm:text-2xl font-black text-slate-900 dark:text-white">
              ¡Compra Confirmada con Éxito!
            </h3>
            <p class="text-xs text-slate-600 dark:text-slate-400">
              Tu orden y comprobante fiscal electrónico han sido emitidos y registrados en el sistema.
            </p>
          </div>

          <!-- Factura Electrónica Timbrada Oficial (SIN / Impuestos Nacionales) -->
          <div class="max-w-md mx-auto p-5 bg-white dark:bg-slate-800/90 border border-slate-200 dark:border-slate-700 rounded-2xl text-left space-y-3 shadow-md">
            <div class="flex justify-between items-center pb-3 border-b border-slate-200 dark:border-slate-700">
              <div class="flex items-center gap-2">
                <FileText class="w-5 h-5 text-blue-600" />
                <div>
                  <h4 class="text-xs font-black uppercase text-slate-900 dark:text-white">Factura Electrónica en Línea</h4>
                  <p class="text-[10px] text-slate-500">MaxiConecta Bolivia S.R.L. · NIT: 1028374029</p>
                </div>
              </div>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                TIMBRADA (SIN)
              </span>
            </div>

            <div class="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span class="text-[10px] text-slate-500">N° Factura:</span>
                <p class="font-mono font-bold text-slate-900 dark:text-white">
                  {{ cartStore.lastEmittedInvoice?.numero_factura || '1001' }}
                </p>
              </div>
              <div>
                <span class="text-[10px] text-slate-500">Código de Orden:</span>
                <p class="font-mono font-bold text-blue-600 dark:text-blue-400">
                  {{ cartStore.lastCreatedOrderCode }}
                </p>
              </div>
              <div>
                <span class="text-[10px] text-slate-500">Razón Social:</span>
                <p class="font-bold text-slate-800 dark:text-slate-200 uppercase truncate">
                  {{ cartStore.lastEmittedInvoice?.datos_comprador?.razon_social || fiscalData.razon_social || 'CONSUMIDOR FINAL' }}
                </p>
              </div>
              <div>
                <span class="text-[10px] text-slate-500">NIT / CI:</span>
                <p class="font-mono font-bold text-slate-800 dark:text-slate-200">
                  {{ cartStore.lastEmittedInvoice?.datos_comprador?.nit_ci || fiscalData.nit_ci || '0' }}
                </p>
              </div>
            </div>

            <div class="pt-2 pb-1 border-t border-slate-100 dark:border-slate-700/60">
              <span class="text-[10px] text-slate-500 block">Código Único de Facturación (CUF):</span>
              <p class="text-[10px] font-mono break-all text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-900/50 p-1.5 rounded border border-slate-200 dark:border-slate-700">
                {{ cartStore.lastEmittedInvoice?.cuf || 'CUF-PROCESADO-SIN' }}
              </p>
            </div>

            <div class="flex items-center justify-between pt-2 border-t border-slate-200 dark:border-slate-700 text-xs">
              <div>
                <span class="text-[10px] text-slate-500">IVA (13% Crédito Fiscal):</span>
                <p class="font-bold text-slate-700 dark:text-slate-300">
                  BOB {{ (cartStore.lastEmittedInvoice?.monto_iva || ((cartStore.lastOrderSummary?.total ?? totalFinal) * 0.13)).toFixed(2) }}
                </p>
              </div>
              <div class="text-right">
                <span class="text-[10px] text-slate-500">Total Facturado:</span>
                <p class="text-sm font-extrabold text-blue-600 dark:text-blue-400">
                  BOB {{ (cartStore.lastOrderSummary?.total ?? totalFinal).toFixed(2) }}
                </p>
              </div>
            </div>

            <div v-if="cartStore.lastEmittedInvoice?.codigo_qr" class="pt-2 flex items-center justify-between text-[10px] text-slate-500 bg-blue-50/50 dark:bg-blue-950/20 p-2 rounded-xl">
              <span class="flex items-center gap-1.5">
                <QrCode class="w-3.5 h-3.5 text-blue-600" /> Verificación oficial en SIAT
              </span>
              <a :href="cartStore.lastEmittedInvoice.codigo_qr" target="_blank" rel="noopener noreferrer" class="font-bold text-blue-600 hover:underline flex items-center gap-1">
                Consultar QR <ExternalLink class="w-3 h-3" />
              </a>
            </div>
          </div>

          <div v-if="cartStore.lastOrderSummary" class="max-w-md mx-auto p-4 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-2xl text-left space-y-2">
            <h4 class="text-xs font-black uppercase tracking-wide text-slate-800 dark:text-slate-200">Resumen del pedido</h4>
            <div v-for="(item, index) in cartStore.lastOrderSummary.items" :key="`${item.nombre}-${index}`" class="flex justify-between gap-3 text-xs">
              <span class="text-slate-600 dark:text-slate-400">{{ item.cantidad }} × {{ item.nombre }}</span>
              <span class="shrink-0 font-semibold">BOB {{ item.total_linea.toFixed(2) }}</span>
            </div>
            <div class="pt-2 border-t border-slate-200 dark:border-slate-700 space-y-1 text-xs">
              <div class="flex justify-between"><span>Subtotal</span><span>BOB {{ cartStore.lastOrderSummary.subtotal.toFixed(2) }}</span></div>
              <div v-if="cartStore.lastOrderSummary.descuento > 0" class="flex justify-between text-emerald-600"><span>Descuentos</span><span>- BOB {{ cartStore.lastOrderSummary.descuento.toFixed(2) }}</span></div>
              <div class="flex justify-between"><span>Envío</span><span>BOB {{ cartStore.lastOrderSummary.costo_envio.toFixed(2) }}</span></div>
              <div class="flex justify-between font-bold"><span>Pago ({{ cartStore.lastOrderSummary.metodo_pago }})</span><span>BOB {{ cartStore.lastOrderSummary.total.toFixed(2) }}</span></div>
            </div>
          </div>

          <div class="pt-2 flex flex-col sm:flex-row justify-center gap-3">
            <button
              @click="descargarComprobantePdf"
              type="button"
              class="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs sm:text-sm rounded-xl transition-all flex items-center justify-center gap-2"
            >
              <Download class="w-4 h-4" /> Descargar comprobante PDF
            </button>
            <button
              @click="imprimirFactura"
              type="button"
              class="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold text-xs sm:text-sm rounded-xl transition-all flex items-center justify-center gap-2 border border-slate-300 dark:border-slate-600"
            >
              <Printer class="w-4 h-4" /> Imprimir Factura
            </button>
            <button
              @click="handleCerrar"
              class="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs sm:text-sm rounded-xl shadow-lg transition-all"
            >
              Ver mi pedido en Mi Cuenta
            </button>
          </div>
          <p v-if="orderError" role="alert" class="max-w-md mx-auto text-xs font-semibold text-rose-600">{{ orderError }}</p>
        </div>

        <!-- VISTA DE FORMULARIO DE CHECKOUT -->
        <div v-else class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Columna Izquierda: Pasos de Entrega y Pago (7 cols) -->
          <div class="lg:col-span-7 space-y-6">
            <!-- PASO 1: Modalidad de Entrega -->
            <div class="bg-slate-50 dark:bg-slate-800/40 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">1</span>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">
                  Modalidad de Entrega
                </h3>
              </div>

              <div v-if="direccionesGuardadas.length && entregaData.tipo_despacho === 'domicilio'" class="space-y-1.5">
                <label for="direccion-guardada" class="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                  <MapPin class="w-3.5 h-3.5 text-blue-600" /> Usar una dirección de mi libreta:
                </label>
                <select
                  id="direccion-guardada"
                  v-model="direccionGuardadaId"
                  class="w-full px-3 py-2 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white"
                >
                  <option :value="null">Ingresar otra dirección</option>
                  <option v-for="direccion in direccionesGuardadas" :key="direccion.id" :value="direccion.id">
                    {{ direccion.direccion }} — {{ direccion.ciudad }}{{ direccion.es_predeterminada ? ' (predeterminada)' : '' }}
                  </option>
                </select>
              </div>

              <!-- Remount on address change so the saved address seeds the selector fields -->
              <DeliveryMethodSelector
                :key="direccionGuardadaId || 'nueva-direccion'"
                :initial-data="entregaInicial"
                :subtotal="cartStore.total"
                @update:model-value="entregaData = $event"
                @validation-change="isEntregaValid = $event"
              />
            </div>

            <!-- PASO 2: Método de Pago (US-16 · RIO-PAG-01) -->
            <div class="bg-slate-50 dark:bg-slate-800/40 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">2</span>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">
                  Método de Pago
                </h3>
              </div>

              <PaymentMethodSelector
                v-model="metodoPago"
                :total-monto="totalFinal"
                @update:card-data="val => cardData = val"
                @validation-change="valid => isPaymentMethodValid = valid"
              />
            </div>


            <!-- PASO 3: Factura Legal Electrónica (NIT / CI y Razón Social) -->
            <div class="bg-slate-50 dark:bg-slate-800/40 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">3</span>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <FileText class="w-4 h-4 text-blue-600" />
                  Factura Legal Electrónica (NIT / CI)
                </h3>
              </div>
              <p class="text-[11px] text-slate-500 dark:text-slate-400">
                Ingresa el NIT o Carnet de Identidad y la Razón Social a cuyo nombre se emitirá la factura oficial timbrada ante el Servicio de Impuestos Nacionales.
              </p>

              <FiscalBillingForm
                v-model="fiscalData"
                :compact="true"
                context="web"
                @validation-change="valid => isFiscalValid = valid"
              />
            </div>
          </div>

          <!-- Columna Derecha: Resumen de Compra y Botón de Pago (5 cols) -->
          <div class="lg:col-span-5 space-y-5">
            <div class="bg-slate-50 dark:bg-slate-800/60 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
              <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                Ítems con Stock Bloqueado ({{ cartStore.itemCount }})
              </h3>

              <!-- Lista de ítems en carrito -->
              <div class="max-h-56 overflow-y-auto space-y-3 pr-1">
                <div
                  v-for="item in cartStore.items"
                  :key="item.variante_id"
                  class="flex items-start justify-between gap-3 text-xs pb-2 border-b border-slate-200/60 dark:border-slate-700/60"
                >
                  <div class="space-y-0.5">
                    <p class="font-bold text-slate-900 dark:text-white line-clamp-1">{{ item.nombre }}</p>
                    <p class="text-[11px] text-slate-500">Cant: {{ item.cantidad }} × BOB {{ item.precio_unitario.toFixed(2) }}</p>
                    <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                      <ShieldCheck class="w-3 h-3" /> 1 unidad reservada
                    </span>
                  </div>
                  <span class="font-bold text-slate-900 dark:text-white shrink-0">
                    BOB {{ item.total_linea.toFixed(2) }}
                  </span>
                </div>
              </div>

              <!-- Input Cupón Promocional (RF-17) -->
              <div class="pt-3 border-t border-slate-200 dark:border-slate-700">
                <CouponInput />
              </div>

              <!-- Fidelización y canje de puntos (RF-25 / KAN-181) -->
              <div v-if="authStore.user" class="pt-3 border-t border-slate-200 dark:border-slate-700 space-y-2">
                <div class="flex items-center justify-between text-xs">
                  <span class="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5"><Sparkles class="w-3.5 h-3.5 text-amber-500" /> MaxiPuntos</span>
                  <span class="font-semibold text-amber-700 dark:text-amber-300">{{ saldoPuntos }} disponibles</span>
                </div>
                <div class="flex items-center gap-2">
                  <label for="checkout-points" class="sr-only">Puntos a canjear</label>
                  <input
                    id="checkout-points"
                    v-model.number="puntosCanjeados"
                    type="number"
                    min="0"
                    :max="maxPuntosCanjeables"
                    step="1"
                    :disabled="maxPuntosCanjeables === 0"
                    placeholder="Puntos a canjear"
                    class="flex-1 min-w-0 px-3 py-2 text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-lg focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-50"
                  />
                  <span class="text-[10px] text-slate-500">1 punto = BOB {{ valorPuntoBob.toFixed(2) }}</span>
                  <button type="button" @click="aplicarPuntos" class="px-3 py-2 text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white rounded-lg">Aplicar</button>
                </div>
                <p class="text-[10px] text-slate-500">Ganas 1 punto por cada BOB {{ bobPorPuntoGanado }} de compra elegible.</p>
                <p v-if="puntosError" role="alert" class="text-[11px] text-rose-600">{{ puntosError }}</p>
              </div>

              <!-- Desglose de Precios -->
              <div class="space-y-1.5 pt-2 text-xs border-t border-slate-200 dark:border-slate-700">
                <div class="flex justify-between text-slate-600 dark:text-slate-400">
                  <span>Subtotal productos:</span>
                  <span>BOB {{ cartStore.subtotal.toFixed(2) }}</span>
                </div>
                <div v-if="cartStore.descuento > 0" class="flex justify-between text-emerald-600 font-semibold">
                  <span>Descuento cupón:</span>
                  <span>- BOB {{ cartStore.descuento.toFixed(2) }}</span>
                </div>
                <div v-if="descuentoPuntos > 0" class="flex justify-between text-amber-700 dark:text-amber-300 font-semibold">
                  <span>Descuento MaxiPuntos ({{ puntosCanjeados }} pts):</span>
                  <span>- BOB {{ descuentoPuntos.toFixed(2) }}</span>
                </div>
                <div class="flex justify-between text-slate-600 dark:text-slate-400">
                  <span>Costo de envío:</span>
                  <span v-if="costoEnvio === 0" class="text-emerald-600 font-semibold">¡Gratis!</span>
                  <span v-else>+ BOB {{ costoEnvio.toFixed(2) }}</span>
                </div>
                <div class="flex justify-between text-base font-extrabold text-slate-900 dark:text-white pt-2 border-t border-slate-300 dark:border-slate-700">
                  <span>Total Final:</span>
                  <span class="text-blue-600 dark:text-blue-400">BOB {{ totalFinal.toFixed(2) }}</span>
                </div>
              </div>

              <!-- Botones de Acción -->
              <div class="space-y-2 pt-2">
                <p v-if="orderError" role="alert" class="p-2.5 rounded-lg bg-rose-50 text-rose-700 text-xs font-semibold border border-rose-200">
                  {{ orderError }}
                </p>
                <button
                  @click="handleConfirmarOrden"
                  :disabled="cartStore.isProcessingOrder || isProcessingPayment || cartStore.reservaStatus === 'expirada'"
                  class="w-full py-3.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-extrabold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-transform hover:scale-[1.01] active:scale-[0.99]"
                >
                  <Loader2 v-if="cartStore.isProcessingOrder || isProcessingPayment" class="w-4 h-4 animate-spin" />
                  <span v-else class="flex items-center gap-2">
                    Confirmar Compra y Pagar <ChevronRight class="w-4 h-4" />
                  </span>
                </button>

                <button
                  type="button"
                  @click="handleCerrar"
                  class="w-full py-2 text-xs font-semibold text-slate-500 hover:text-rose-600 dark:hover:text-rose-400 transition-colors"
                >
                  Cancelar compra y liberar stock reservado
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- OVERLAY DE EXPIRACIÓN DEL TTL (900 SEGUNDOS AGOTADOS) -->
        <div
          v-if="cartStore.reservaStatus === 'expirada'"
          class="absolute inset-0 bg-slate-950/80 backdrop-blur-md rounded-2xl flex items-center justify-center p-6 z-20 animate-fade-in"
        >
          <div class="max-w-md bg-white dark:bg-slate-900 p-6 rounded-3xl border border-rose-500/40 shadow-2xl text-center space-y-4">
            <div class="w-16 h-16 mx-auto rounded-2xl bg-rose-100 dark:bg-rose-950/80 text-rose-600 flex items-center justify-center animate-pulse">
              <AlertTriangle class="w-8 h-8" />
            </div>

            <div class="space-y-2">
              <h4 class="text-lg font-black text-slate-900 dark:text-white">
                ¡Tu Reserva de Stock ha Expirado!
              </h4>
              <p class="text-xs text-slate-600 dark:text-slate-400">
                El tiempo de 15 minutos asignado para tu compra ha concluido. Para evitar sobreventas concurrentes, las existencias han sido liberadas automáticamente en el inventario general.
              </p>
            </div>

            <div class="pt-2 flex flex-col gap-2">
              <button
                @click="handleRenovarReserva"
                class="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-xl shadow flex items-center justify-center gap-2"
              >
                <RotateCcw class="w-4 h-4" />
                Renovar Reserva y Continuar
              </button>

              <button
                @click="handleCerrar"
                class="w-full py-2 text-xs font-medium text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              >
                Regresar a la tienda
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- MODAL DE PAGO DIGITAL EN TIEMPO REAL (US-16 · RIO-PAG-01) -->
  <DynamicPaymentProcessingModal
    v-if="isPaymentProcessingModalOpen && activePaymentData"
    :pago-data="activePaymentData"
    :nombre-cliente="authStore.user?.nombre_completo || 'Cliente'"
    @approved="onPaymentApproved"
    @rejected="onPaymentRejected"
    @cancel="isPaymentProcessingModalOpen = false"
  />
</template>

