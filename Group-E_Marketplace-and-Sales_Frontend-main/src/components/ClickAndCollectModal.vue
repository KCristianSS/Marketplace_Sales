<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { apiClient } from '@/api/client';
import type { 
  PedidoClickAndCollect, 
  ConfirmarEntregaPayload 
} from '@/types';
import DualCurrencyPrice from '@/components/DualCurrencyPrice.vue';
import {
  Scan,
  QrCode,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  PackageCheck,
  User,
  ShieldCheck,
  Printer,
  X,
  FileCheck,
  Building2,
  Clock,
  Check,
  AlertCircle,
  Sparkles,
  UserCheck,
  RefreshCw,
  ShoppingBag,
  ExternalLink
} from 'lucide-vue-next';

const props = defineProps<{
  isOpen: boolean;
  sucursalNombre: string;
  sucursalId?: string;
  cajeroId?: string;
  cajeroNombre: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

// Estado del buscador y lista
const searchInput = ref('');
const isSearching = ref(false);
const searchError = ref('');
const searchSuccessMsg = ref('');
const ordersList = ref<PedidoClickAndCollect[]>([]);
const isLoadingList = ref(false);
const filterStatus = ref<'todos' | 'pendientes' | 'entregados'>('todos');

// Pedido seleccionado actualmente
const selectedOrder = ref<PedidoClickAndCollect | null>(null);

// Modal de Confirmación de Entrega (KAN-327)
const isConfirmModalOpen = ref(false);
const isSubmittingDelivery = ref(false);
const deliveryError = ref('');

// Formulario de confirmación de receptor
const receptorTipo = ref<'titular' | 'tercero_autorizado'>('titular');
const receptorNombre = ref('');
const receptorDocumento = ref('');
const receptorTelefono = ref('');
const receptorObservaciones = ref('');

// Checklist de validación obligatoria (KAN-108 / KAN-327)
const checkDocumentoFisico = ref(false);
const checkPaqueteRevisado = ref(false);
const checkConformidad = ref(false);

const isChecklistComplete = computed(() => {
  return checkDocumentoFisico.value && checkPaqueteRevisado.value && checkConformidad.value;
});

// Comprobante de entrega emitido tras finalizar
const comprobanteEmitido = ref<any | null>(null);
const isReceiptModalOpen = ref(false);

// Cargar pedidos de Click & Collect desde backend
async function fetchOrders() {
  isLoadingList.value = true;
  searchError.value = '';
  try {
    const res = await apiClient.get<PedidoClickAndCollect[]>('/v1/pos/click-and-collect/pedidos', {
      params: {
        sucursal_id: props.sucursalId,
        filtro_estado: filterStatus.value === 'todos' ? undefined : filterStatus.value
      }
    });
    ordersList.value = res.data || [];
    
    // Si no hay seleccionado o fue actualizado, mantener o seleccionar el primero
    if (ordersList.value.length > 0 && !selectedOrder.value) {
      selectedOrder.value = ordersList.value[0];
    } else if (selectedOrder.value) {
      const updated = ordersList.value.find(o => o.codigo_retiro === selectedOrder.value?.codigo_retiro);
      if (updated) selectedOrder.value = updated;
    }
  } catch (err: any) {
    ordersList.value = [];
    searchError.value = err.response?.data?.detail || err.response?.data?.error || 'No se pudieron cargar los pedidos de retiro.';
  } finally {
    isLoadingList.value = false;
  }
}

// Búsqueda o escaneo de código QR / Alfanumérico (KAN-324)
async function buscarPorCodigo(codigoAConsultar?: string) {
  const code = (codigoAConsultar || searchInput.value).trim();
  if (!code) return;

  searchInput.value = code;
  isSearching.value = true;
  searchError.value = '';
  searchSuccessMsg.value = '';

  try {
    const res = await apiClient.post<PedidoClickAndCollect>('/v1/pos/click-and-collect/validar', {
      codigo: code,
      sucursal_id: props.sucursalId,
    });

    selectedOrder.value = res.data;
    searchSuccessMsg.value = `Pedido ${res.data.codigo_orden} cargado exitosamente.`;

    // Actualizar en la lista local si no estaba
    const idx = ordersList.value.findIndex(o => o.codigo_retiro === res.data.codigo_retiro);
    if (idx >= 0) {
      ordersList.value[idx] = res.data;
    } else {
      ordersList.value.unshift(res.data);
    }
  } catch (err: any) {
    searchError.value = err.response?.data?.detail || err.response?.data?.error || `No se encontró ningún pedido con el código '${code}'.`;
  } finally {
    isSearching.value = false;
  }
}

function selectOrder(order: PedidoClickAndCollect) {
  selectedOrder.value = order;
  searchError.value = '';
  searchSuccessMsg.value = '';
}

// Abrir modal de confirmación y precargar titular (KAN-327)
function abrirModalEntrega() {
  if (!selectedOrder.value || !selectedOrder.value.es_entregable) return;

  receptorTipo.value = 'titular';
  receptorNombre.value = selectedOrder.value.cliente_nombre;
  receptorDocumento.value = selectedOrder.value.cliente_documento;
  receptorTelefono.value = selectedOrder.value.cliente_telefono || '';
  receptorObservaciones.value = '';

  checkDocumentoFisico.value = false;
  checkPaqueteRevisado.value = false;
  checkConformidad.value = false;
  deliveryError.value = '';

  isConfirmModalOpen.value = true;
}

watch(receptorTipo, (newVal) => {
  if (!selectedOrder.value) return;
  if (newVal === 'titular') {
    receptorNombre.value = selectedOrder.value.cliente_nombre;
    receptorDocumento.value = selectedOrder.value.cliente_documento;
    receptorTelefono.value = selectedOrder.value.cliente_telefono || '';
  } else {
    receptorNombre.value = '';
    receptorDocumento.value = '';
    receptorTelefono.value = '';
  }
});

// Confirmar entrega física en mostrador (KAN-325, KAN-327)
async function procesarEntrega() {
  if (!selectedOrder.value) return;
  if (!isChecklistComplete.value) {
    deliveryError.value = 'Debe completar todas las verificaciones físicas antes de despachar.';
    return;
  }
  if (!receptorNombre.value.trim() || !receptorDocumento.value.trim()) {
    deliveryError.value = 'Debe ingresar el Nombre y Documento del receptor de la mercadería.';
    return;
  }

  isSubmittingDelivery.value = true;
  deliveryError.value = '';

  try {
    const payload: ConfirmarEntregaPayload = {
      orden_id: selectedOrder.value.orden_id,
      codigo_retiro: selectedOrder.value.codigo_retiro,
      receptor_nombre: receptorNombre.value.trim(),
      receptor_documento: receptorDocumento.value.trim(),
      receptor_tipo: receptorTipo.value,
      receptor_telefono: receptorTelefono.value.trim() || undefined,
      observaciones: receptorObservaciones.value.trim() || undefined,
      cajero_id: props.cajeroId,
      cajero_nombre: props.cajeroNombre,
      sucursal_id: props.sucursalId,
      sucursal_nombre: props.sucursalNombre,
    };

    const res = await apiClient.post('/v1/pos/click-and-collect/confirmar-entrega', payload);

    comprobanteEmitido.value = res.data.comprobante_entrega;
    isConfirmModalOpen.value = false;
    isReceiptModalOpen.value = true;

    // Actualizar estado del pedido local
    await fetchOrders();
    await buscarPorCodigo(selectedOrder.value.codigo_retiro);
  } catch (err: any) {
    deliveryError.value = err.response?.data?.detail || err.response?.data?.error || 'Error al confirmar la entrega del pedido.';
  } finally {
    isSubmittingDelivery.value = false;
  }
}

function imprimirComprobante() {
  window.print();
}

onMounted(() => {
  fetchOrders();
});

watch(() => props.isOpen, (open) => {
  if (open) {
    fetchOrders();
  }
});
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
    <!-- Ventana Principal Modal Click & Collect -->
    <div class="relative w-full max-w-6xl bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col max-h-[92vh] overflow-hidden">
      
      <!-- Encabezado del Módulo (RF-11) -->
      <div class="px-6 py-4 bg-slate-950 text-white flex flex-wrap items-center justify-between gap-4 border-b border-slate-800">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-teal-500/20 border border-teal-500/30 flex items-center justify-center text-teal-300">
            <PackageCheck class="w-6 h-6" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base font-bold text-white tracking-tight">Módulo Click & Collect — Retiro en Sucursal</h2>
              <span class="text-[10px] font-mono bg-teal-500/20 text-teal-300 border border-teal-500/30 px-2 py-0.5 rounded-full font-bold">
                RF-11 · KAN-27
              </span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
              <Building2 class="w-3.5 h-3.5 text-cyan-400" />
              <span>{{ sucursalNombre }}</span>
              <span>·</span>
              <User class="w-3.5 h-3.5 text-indigo-400" />
              <span>{{ cajeroNombre }}</span>
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2.5">
          <button
            type="button"
            @click="fetchOrders"
            class="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            title="Refrescar pedidos"
          >
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoadingList }" />
          </button>
          <button
            type="button"
            @click="emit('close')"
            class="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
            title="Cerrar módulo"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Barra de Escaneo Rápido de Código o QR (KAN-324, KAN-326) -->
      <div class="px-6 py-3.5 bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <form @submit.prevent="buscarPorCodigo()" class="flex-1 flex gap-2 max-w-2xl">
          <div class="relative flex-1">
            <Scan class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              v-model="searchInput"
              type="text"
              autofocus
              placeholder="Escanear código de barras, QR o ingresar código de retiro (ej: RET-789214)..."
              class="w-full pl-10 pr-4 py-2 text-sm bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-teal-600 focus:outline-none font-mono"
            />
          </div>
          <button
            type="submit"
            :disabled="isSearching || !searchInput.trim()"
            class="px-4 py-2 bg-teal-700 hover:bg-teal-800 disabled:opacity-50 text-white rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-sm transition-colors"
          >
            <Search class="w-3.5 h-3.5" />
            <span>{{ isSearching ? 'Buscando...' : 'Validar' }}</span>
          </button>
        </form>

        <!-- Presets para demostración rápida en mostrador -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 text-xs">
          <span class="text-slate-500 text-[11px] font-semibold whitespace-nowrap">Demos rápidas:</span>
          <button
            type="button"
            @click="buscarPorCodigo('RET-789214')"
            class="px-2.5 py-1 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 hover:bg-emerald-200 border border-emerald-300 dark:border-emerald-800 rounded font-mono text-[11px] font-semibold whitespace-nowrap"
            title="Pedido listo para retiro"
          >
            RET-789214 (Listo)
          </button>
          <button
            type="button"
            @click="buscarPorCodigo('RET-345091')"
            class="px-2.5 py-1 bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 hover:bg-amber-200 border border-amber-300 dark:border-amber-800 rounded font-mono text-[11px] font-semibold whitespace-nowrap"
            title="Pedido ya entregado con auditoría"
          >
            RET-345091 (Entregado)
          </button>
          <button
            type="button"
            @click="buscarPorCodigo('RET-992381')"
            class="px-2.5 py-1 bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-300 hover:bg-rose-200 border border-rose-300 dark:border-rose-800 rounded font-mono text-[11px] font-semibold whitespace-nowrap"
            title="Pedido cancelado"
          >
            RET-992381 (Cancelado)
          </button>
        </div>
      </div>

      <!-- Alertas de Búsqueda -->
      <div v-if="searchError" class="mx-6 mt-3 p-3 bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 rounded-xl flex items-center gap-2.5 text-xs text-rose-800 dark:text-rose-300">
        <AlertTriangle class="w-4 h-4 text-rose-500 shrink-0" />
        <span class="font-medium">{{ searchError }}</span>
      </div>
      <div v-if="searchSuccessMsg" class="mx-6 mt-3 p-3 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 rounded-xl flex items-center gap-2.5 text-xs text-emerald-800 dark:text-emerald-300">
        <CheckCircle2 class="w-4 h-4 text-emerald-500 shrink-0" />
        <span class="font-medium">{{ searchSuccessMsg }}</span>
      </div>

      <!-- Cuerpo Principal Dividido (Lista y Detalle) -->
      <div class="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden min-h-0">
        
        <!-- Columna Izquierda: Cola de Pedidos en Sucursal (4 columnas) -->
        <div class="lg:col-span-5 border-r border-slate-200 dark:border-slate-800 flex flex-col min-h-0 bg-slate-50/50 dark:bg-slate-900/50">
          <!-- Filtros de Estado -->
          <div class="p-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
            <span class="text-xs font-bold text-slate-700 dark:text-slate-300">Pedidos Click & Collect ({{ ordersList.length }})</span>
            <div class="inline-flex rounded-lg bg-slate-200 dark:bg-slate-800 p-0.5 text-xs">
              <button
                type="button"
                @click="filterStatus = 'todos'; fetchOrders()"
                :class="filterStatus === 'todos' ? 'bg-white dark:bg-slate-700 font-bold shadow-sm text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'"
                class="px-2.5 py-1 rounded-md transition-all"
              >
                Todos
              </button>
              <button
                type="button"
                @click="filterStatus = 'pendientes'; fetchOrders()"
                :class="filterStatus === 'pendientes' ? 'bg-white dark:bg-slate-700 font-bold shadow-sm text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'"
                class="px-2.5 py-1 rounded-md transition-all"
              >
                Listos
              </button>
              <button
                type="button"
                @click="filterStatus = 'entregados'; fetchOrders()"
                :class="filterStatus === 'entregados' ? 'bg-white dark:bg-slate-700 font-bold shadow-sm text-slate-900 dark:text-white' : 'text-slate-600 dark:text-slate-400'"
                class="px-2.5 py-1 rounded-md transition-all"
              >
                Entregados
              </button>
            </div>
          </div>

          <!-- Lista de Pedidos -->
          <div class="flex-1 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-800">
            <div
              v-for="order in ordersList"
              :key="order.codigo_retiro"
              @click="selectOrder(order)"
              :class="[
                selectedOrder?.codigo_retiro === order.codigo_retiro 
                  ? 'bg-teal-50 dark:bg-teal-950/40 border-l-4 border-l-teal-600' 
                  : 'hover:bg-slate-100/80 dark:hover:bg-slate-800/60'
              ]"
              class="p-3.5 cursor-pointer transition-colors"
            >
              <div class="flex items-start justify-between gap-2">
                <div>
                  <div class="flex items-center gap-1.5">
                    <span class="font-mono text-xs font-bold text-slate-900 dark:text-white">{{ order.codigo_retiro }}</span>
                    <span class="text-[11px] text-slate-500 font-mono">({{ order.codigo_orden }})</span>
                  </div>
                  <p class="text-xs font-semibold text-slate-700 dark:text-slate-200 mt-1">{{ order.cliente_nombre }}</p>
                  <p class="text-[11px] text-slate-500 font-mono">CI/NIT: {{ order.cliente_documento }}</p>
                </div>
                
                <div class="text-right">
                  <span
                    :class="[
                      order.estado === 'entregada' ? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300' :
                      order.estado === 'cancelada' ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border-rose-300' :
                      'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300'
                    ]"
                    class="inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border"
                  >
                    {{ order.estado === 'entregada' ? 'Entregado' : order.estado === 'cancelada' ? 'Cancelado' : 'Listo p/ Retiro' }}
                  </span>
                  <p class="text-xs font-bold text-slate-900 dark:text-white mt-1">BOB {{ order.total.toFixed(2) }}</p>
                  <p class="text-[10px] text-slate-400">{{ order.items.length }} ítem(s)</p>
                </div>
              </div>
            </div>

            <div v-if="ordersList.length === 0" class="p-8 text-center text-slate-400 text-xs">
              No hay pedidos que coincidan con el filtro seleccionado.
            </div>
          </div>
        </div>

        <!-- Columna Derecha: Detalle Completo del Pedido y Acciones (7 columnas) -->
        <div class="lg:col-span-7 flex flex-col min-h-0 bg-white dark:bg-slate-900 overflow-y-auto p-5">
          <div v-if="selectedOrder" class="space-y-5">
            
            <!-- Banner de Estado de Entregabilidad (KAN-108) -->
            <div
              :class="[
                selectedOrder.es_entregable ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200' :
                selectedOrder.estado === 'entregada' ? 'bg-slate-100 dark:bg-slate-800/80 border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-300' :
                'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800 text-rose-900 dark:text-rose-200'
              ]"
              class="p-4 rounded-xl border flex items-start gap-3"
            >
              <CheckCircle2 v-if="selectedOrder.es_entregable" class="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" />
              <ShieldCheck v-else-if="selectedOrder.estado === 'entregada'" class="w-6 h-6 text-slate-600 dark:text-slate-400 shrink-0 mt-0.5" />
              <XCircle v-else class="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />

              <div class="flex-1">
                <div class="flex items-center justify-between">
                  <h3 class="text-sm font-bold">
                    {{ selectedOrder.es_entregable ? 'Listo para Despacho en Mostrador' : selectedOrder.estado === 'entregada' ? 'Pedido Previamente Entregado' : 'Pedido No Entregable' }}
                  </h3>
                  <span class="text-xs font-mono font-bold px-2 py-0.5 rounded bg-black/10 dark:bg-white/10">
                    {{ selectedOrder.codigo_retiro }}
                  </span>
                </div>
                <p class="text-xs mt-1 opacity-90">
                  {{ selectedOrder.motivo_rechazo || 'El cliente completó el pago en línea y el stock está resguardado en la sucursal para entrega inmediata.' }}
                </p>
              </div>
            </div>

            <!-- Ficha Técnica de la Compra -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <!-- Datos del Titular -->
              <div class="p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-800">
                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <User class="w-3.5 h-3.5 text-teal-600" /> Titular del Pedido
                </span>
                <p class="text-xs font-bold text-slate-900 dark:text-white mt-1.5">{{ selectedOrder.cliente_nombre }}</p>
                <p class="text-xs text-slate-500 font-mono mt-0.5">CI/NIT: <span class="font-bold text-slate-700 dark:text-slate-300">{{ selectedOrder.cliente_documento }}</span></p>
                <p v-if="selectedOrder.cliente_telefono" class="text-xs text-slate-500 mt-0.5">Tel: {{ selectedOrder.cliente_telefono }}</p>
                <p v-if="selectedOrder.cliente_email" class="text-xs text-slate-500 truncate mt-0.5">{{ selectedOrder.cliente_email }}</p>
              </div>

              <!-- Datos de Despacho & Pago -->
              <div class="p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-200 dark:border-slate-800">
                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <ShoppingBag class="w-3.5 h-3.5 text-indigo-600" /> Sucursal y Pago
                </span>
                <p class="text-xs font-bold text-slate-900 dark:text-white mt-1.5">{{ selectedOrder.sucursal_nombre }}</p>
                <p class="text-xs text-slate-500 mt-0.5">Método: <span class="font-medium text-emerald-600">{{ selectedOrder.metodo_pago }}</span></p>
                <p v-if="selectedOrder.numero_factura" class="text-xs text-slate-500 font-mono mt-0.5">Factura #{{ selectedOrder.numero_factura }}</p>
                <p v-if="selectedOrder.cuf_factura" class="text-[10px] text-slate-400 font-mono truncate mt-0.5" :title="selectedOrder.cuf_factura">
                  CUF: {{ selectedOrder.cuf_factura.substring(0, 24) }}...
                </p>
              </div>
            </div>

            <!-- Detalle de Productos a Entregar -->
            <div class="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
              <div class="px-4 py-2.5 bg-slate-100 dark:bg-slate-800 flex items-center justify-between text-xs font-bold text-slate-700 dark:text-slate-300">
                <span>Productos a Despachar ({{ selectedOrder.items.length }} ítems)</span>
                <span>Subtotal: BOB {{ selectedOrder.total.toFixed(2) }}</span>
              </div>
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-50 dark:bg-slate-800/50 text-slate-500 border-b border-slate-200 dark:border-slate-800 font-semibold">
                  <tr>
                    <th class="p-3">SKU</th>
                    <th class="p-3">Descripción</th>
                    <th class="p-3 text-center">Cant.</th>
                    <th class="p-3 text-right">Unitario</th>
                    <th class="p-3 text-right">Total</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                  <tr v-for="it in selectedOrder.items" :key="it.sku" class="hover:bg-slate-50/50">
                    <td class="p-3 font-mono font-bold text-blue-600 dark:text-blue-400">{{ it.sku }}</td>
                    <td class="p-3 text-slate-800 dark:text-slate-200 font-medium">{{ it.nombre_producto }}</td>
                    <td class="p-3 text-center font-bold">
                      <span class="inline-block px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded">{{ it.cantidad }}</span>
                    </td>
                    <td class="p-3 text-right text-slate-500">BOB {{ it.precio_unitario.toFixed(2) }}</td>
                    <td class="p-3 text-right font-bold text-slate-900 dark:text-white">BOB {{ it.total_linea.toFixed(2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Sección de Auditoría Previa si ya fue entregado -->
            <div v-if="selectedOrder.despacho" class="p-4 bg-slate-100 dark:bg-slate-800/90 rounded-xl border border-slate-300 dark:border-slate-700 space-y-2">
              <div class="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-slate-200">
                <FileCheck class="w-4 h-4 text-emerald-600" />
                <span>Acta de Entrega Registrada ({{ selectedOrder.despacho.numero_acta || 'ACTA-CC' }})</span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-400">
                <p><span class="font-semibold text-slate-700 dark:text-slate-300">Receptor:</span> {{ selectedOrder.despacho.receptor_nombre }} (Doc: {{ selectedOrder.despacho.receptor_documento }})</p>
                <p><span class="font-semibold text-slate-700 dark:text-slate-300">Tipo de Receptor:</span> {{ selectedOrder.despacho.receptor_tipo === 'titular' ? 'Titular' : 'Tercero Autorizado' }}</p>
                <p><span class="font-semibold text-slate-700 dark:text-slate-300">Cajero Responsable:</span> {{ selectedOrder.despacho.cajero_nombre }}</p>
                <p><span class="font-semibold text-slate-700 dark:text-slate-300">Fecha/Hora:</span> {{ new Date(selectedOrder.despacho.fecha_entrega).toLocaleString() }}</p>
              </div>
              <p v-if="selectedOrder.despacho.observaciones" class="text-xs italic text-slate-500 border-t border-slate-200 dark:border-slate-700 pt-2">
                "{{ selectedOrder.despacho.observaciones }}"
              </p>
            </div>

            <!-- Botón Principal de Acción -->
            <div class="pt-2 flex items-center justify-between gap-4">
              <div class="text-xs text-slate-400">
                Código QR: <code class="font-mono text-[11px] bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded">{{ selectedOrder.codigo_qr || selectedOrder.codigo_retiro }}</code>
              </div>

              <button
                v-if="selectedOrder.es_entregable"
                type="button"
                @click="abrirModalEntrega"
                class="px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-xl font-bold text-sm flex items-center gap-2 shadow-lg shadow-teal-900/20 transition-all hover:scale-[1.02]"
              >
                <PackageCheck class="w-4 h-4" />
                <span>Confirmar Entrega y Registrar Receptor</span>
              </button>
              <div v-else class="text-xs font-bold text-slate-400 uppercase">
                Acción no disponible para este estado
              </div>
            </div>

          </div>

          <div v-else class="h-full flex flex-col items-center justify-center p-8 text-center text-slate-400">
            <PackageCheck class="w-12 h-12 text-slate-300 mb-2 stroke-1" />
            <p class="text-sm font-semibold">Seleccione un pedido o escanee un código de retiro</p>
            <p class="text-xs text-slate-400 mt-1 max-w-sm">
              Use el buscador superior o el lector de código de barras para cargar los datos del pedido Click & Collect.
            </p>
          </div>
        </div>

      </div>

    </div>

    <!-- MODAL DE CONFIRMACIÓN DE ENTREGA Y REGISTRO DE RECEPTOR (KAN-108, KAN-327) -->
    <div v-if="isConfirmModalOpen && selectedOrder" class="fixed inset-0 z-60 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 overflow-hidden">
        
        <div class="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
          <div class="flex items-center gap-2.5">
            <div class="p-2 bg-teal-50 dark:bg-teal-950/50 rounded-lg text-teal-600">
              <UserCheck class="w-5 h-5" />
            </div>
            <div>
              <h3 class="text-sm font-bold text-slate-900 dark:text-white">Confirmación de Entrega Física</h3>
              <p class="text-xs text-slate-500">Orden {{ selectedOrder.codigo_orden }} · {{ selectedOrder.codigo_retiro }}</p>
            </div>
          </div>
          <button @click="isConfirmModalOpen = false" class="p-1 text-slate-400 hover:text-slate-600">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div v-if="deliveryError" class="mt-3 p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 font-medium">
          {{ deliveryError }}
        </div>

        <form @submit.prevent="procesarEntrega" class="space-y-4 mt-4 text-xs">
          <!-- Selector: ¿Quién retira? -->
          <div>
            <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1.5">¿Quién retira la mercadería?</label>
            <div class="grid grid-cols-2 gap-2">
              <label
                :class="receptorTipo === 'titular' ? 'border-teal-600 bg-teal-50/50 dark:bg-teal-950/40 text-teal-900 dark:text-teal-200' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400'"
                class="p-2.5 rounded-lg border cursor-pointer flex items-center gap-2 font-semibold"
              >
                <input type="radio" value="titular" v-model="receptorTipo" class="text-teal-600" />
                <span>Titular de la Compra</span>
              </label>
              <label
                :class="receptorTipo === 'tercero_autorizado' ? 'border-teal-600 bg-teal-50/50 dark:bg-teal-950/40 text-teal-900 dark:text-teal-200' : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400'"
                class="p-2.5 rounded-lg border cursor-pointer flex items-center gap-2 font-semibold"
              >
                <input type="radio" value="tercero_autorizado" v-model="receptorTipo" class="text-teal-600" />
                <span>Tercero Autorizado</span>
              </label>
            </div>
          </div>

          <!-- Campos de Identidad del Receptor -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Nombre Completo del Receptor *</label>
              <input
                v-model="receptorNombre"
                type="text"
                required
                placeholder="Nombre y Apellidos"
                class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-teal-600 focus:outline-none"
              />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Documento de Identidad (CI/Doc) *</label>
              <input
                v-model="receptorDocumento"
                type="text"
                required
                placeholder="Número de CI"
                class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-teal-600 focus:outline-none font-mono"
              />
            </div>
          </div>

          <div>
            <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Teléfono de Contacto (Opcional)</label>
            <input
              v-model="receptorTelefono"
              type="text"
              placeholder="+591 7XXXXXXX"
              class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-teal-600 focus:outline-none font-mono"
            />
          </div>

          <div>
            <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Observaciones / Motivo de Autorización</label>
            <textarea
              v-model="receptorObservaciones"
              rows="2"
              placeholder="Ej: Presenta fotocopia de CI y carta poder simple..."
              class="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-teal-600 focus:outline-none"
            ></textarea>
          </div>

          <!-- Checklist Obligatorio de Verificación (KAN-108) -->
          <div class="p-3 bg-slate-50 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700 space-y-2">
            <span class="block font-bold text-slate-800 dark:text-slate-200 text-[11px] uppercase tracking-wider">
              Checklist de Seguridad en Mostrador (Obligatorio)
            </span>
            <label class="flex items-center gap-2 cursor-pointer font-medium text-slate-700 dark:text-slate-300">
              <input type="checkbox" v-model="checkDocumentoFisico" class="w-4 h-4 text-teal-600 rounded" />
              <span>Verificación de documento de identidad en físico original</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer font-medium text-slate-700 dark:text-slate-300">
              <input type="checkbox" v-model="checkPaqueteRevisado" class="w-4 h-4 text-teal-600 rounded" />
              <span>Paquete e ítems revisados físicamente completos ({{ selectedOrder.items.length }} productos)</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer font-medium text-slate-700 dark:text-slate-300">
              <input type="checkbox" v-model="checkConformidad" class="w-4 h-4 text-teal-600 rounded" />
              <span>Conformidad del receptor y mercadería en perfecto estado</span>
            </label>
          </div>

          <!-- Botones de Acción -->
          <div class="pt-2 flex justify-end gap-2.5">
            <button
              type="button"
              @click="isConfirmModalOpen = false"
              class="px-4 py-2 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-lg font-semibold hover:bg-slate-100"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="!isChecklistComplete || isSubmittingDelivery"
              class="px-5 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-40 text-white rounded-lg font-bold flex items-center gap-1.5 shadow-md shadow-teal-900/20"
            >
              <PackageCheck class="w-4 h-4" />
              <span>{{ isSubmittingDelivery ? 'Registrando Entrega...' : 'Confirmar y Despachar' }}</span>
            </button>
          </div>
        </form>

      </div>
    </div>

    <!-- MODAL DE COMPROBANTE DE ENTREGA / ACTA DE RETIRO DIGITAL IMPRIMIBLE (KAN-327) -->
    <div v-if="isReceiptModalOpen && comprobanteEmitido" class="fixed inset-0 z-70 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6 text-slate-900 overflow-hidden print:m-0 print:p-0 print:shadow-none print:w-full">
        
        <div class="text-center pb-4 border-b border-dashed border-slate-300">
          <div class="w-12 h-12 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto mb-2 print:hidden">
            <CheckCircle2 class="w-7 h-7" />
          </div>
          <h2 class="text-base font-extrabold tracking-tight uppercase">MAXICONECTA — ACTA DE ENTREGA</h2>
          <p class="text-xs text-slate-500 font-mono mt-0.5">Retiro en Sucursal Click & Collect (RF-11)</p>
          <p class="text-xs font-mono font-bold text-emerald-800 mt-1">{{ comprobanteEmitido.acta_numero }}</p>
        </div>

        <div class="py-4 space-y-2 text-xs font-mono">
          <div class="flex justify-between">
            <span class="text-slate-500">Orden de Venta:</span>
            <span class="font-bold">{{ comprobanteEmitido.codigo_orden }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Código Retiro:</span>
            <span class="font-bold">{{ comprobanteEmitido.codigo_retiro }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Sucursal:</span>
            <span class="font-bold truncate max-w-[200px]">{{ comprobanteEmitido.sucursal }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Fecha y Hora:</span>
            <span>{{ new Date(comprobanteEmitido.fecha).toLocaleString() }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Cajero Responsable:</span>
            <span>{{ comprobanteEmitido.cajero }}</span>
          </div>

          <div class="border-t border-dashed border-slate-300 pt-2 mt-2">
            <div class="flex justify-between">
              <span class="text-slate-500">Titular de Compra:</span>
              <span class="font-bold">{{ comprobanteEmitido.titular }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Receptor Físico:</span>
              <span class="font-bold">{{ comprobanteEmitido.receptor }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Doc. Receptor:</span>
              <span class="font-bold">{{ comprobanteEmitido.documento_receptor }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Tipo Receptor:</span>
              <span class="capitalize">{{ comprobanteEmitido.tipo_receptor === 'titular' ? 'Titular' : 'Tercero Autorizado' }}</span>
            </div>
          </div>

          <div class="border-t border-dashed border-slate-300 pt-2 mt-2 flex justify-between font-bold text-sm">
            <span>Total Mercadería ({{ comprobanteEmitido.total_items }} ítems):</span>
            <span>BOB {{ Number(comprobanteEmitido.monto_total).toFixed(2) }}</span>
          </div>
        </div>

        <!-- Firma de Conformidad -->
        <div class="pt-6 pb-2 text-center text-[10px] text-slate-400 font-mono border-t border-dashed border-slate-300">
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div class="border-t border-slate-400 pt-1">
              Firma Receptor
            </div>
            <div class="border-t border-slate-400 pt-1">
              Sello / Firma Cajero
            </div>
          </div>
          <p>Constancia legal de entrega física de mercadería adquirida vía comercio electrónico.</p>
        </div>

        <div class="pt-4 flex justify-end gap-2 print:hidden">
          <button
            type="button"
            @click="imprimirComprobante"
            class="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-sm"
          >
            <Printer class="w-3.5 h-3.5" />
            <span>Imprimir Acta</span>
          </button>
          <button
            type="button"
            @click="isReceiptModalOpen = false"
            class="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-bold text-xs"
          >
            Aceptar y Continuar
          </button>
        </div>

      </div>
    </div>

  </div>
</template>
