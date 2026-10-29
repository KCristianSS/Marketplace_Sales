<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { apiClient } from '@/api/client';
import { 
  Radio, 
  Send, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw, 
  X, 
  Terminal, 
  Server, 
  ShoppingBag, 
  RotateCcw,
  ExternalLink,
  ShieldCheck
} from 'lucide-vue-next';

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const loading = ref(false);
const statusData = ref<{
  projectId: string;
  topic: string;
  hasCredentialsFile: boolean;
  credentialsPath: string | null;
  mode: string;
  totalEventsLogged: number;
} | null>(null);

const activeTab = ref<'prueba_docente' | 'venta_stock' | 'reintegro' | 'historial'>('prueba_docente');

// Formulario de prueba docente
const responsable = ref('Kevin Sancalli');
const detalleMensaje = ref('Sincronización simulada enviando eventos de venta y stock al tópico del docente (Grupo E)');

// Formulario de venta
const ordenId = ref(`ORD-SYS-${Date.now().toString(36).toUpperCase()}`);
const ventaSku = ref('FAR-PARACETAMOL-500');
const ventaNombre = ref('Paracetamol 500mg - Caja 20 tabletas');
const ventaCantidad = ref(2);

// Formulario de reintegro
const reintegroOrdenId = ref(`ORD-DEV-${Date.now().toString(36).toUpperCase()}`);
const reintegroSku = ref('FAR-PARACETAMOL-500');
const reintegroMotivo = ref('anulacion_cliente_empaque_danado');
const reintegroCantidad = ref(1);

// Resultado de la última operación
const lastResult = ref<any>(null);
const errorMessage = ref('');
const historial = ref<any[]>([]);

async function fetchStatus() {
  try {
    const res = await apiClient.get('/v1/ordenes/integraciones/pubsub/status');
    statusData.value = res.data;
  } catch (err: any) {
    console.warn('Error obteniendo estado de Pub/Sub:', err);
    errorMessage.value = err.response?.data?.detail || 'No se pudo consultar el estado de Pub/Sub.';
  }
}

async function fetchHistorial() {
  try {
    const res = await apiClient.get('/v1/ordenes/integraciones/pubsub/historial');
    historial.value = res.data.eventos || [];
  } catch (err: any) {
    console.warn('Error obteniendo historial:', err);
    errorMessage.value = err.response?.data?.detail || 'No se pudo consultar el historial de Pub/Sub.';
  }
}

async function enviarPruebaDocente() {
  loading.value = true;
  errorMessage.value = '';
  lastResult.value = null;
  try {
    const res = await apiClient.post('/v1/ordenes/integraciones/pubsub/test', {
      responsable: responsable.value,
      detalle: detalleMensaje.value
    });
    lastResult.value = res.data.evento;
    await fetchStatus();
    await fetchHistorial();
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.response?.data?.error || err.message || 'Error al enviar evento';
  } finally {
    loading.value = false;
  }
}

async function enviarVentaStock() {
  loading.value = true;
  errorMessage.value = '';
  lastResult.value = null;
  try {
    const res = await apiClient.post('/v1/ordenes/integraciones/pubsub/descuento-stock', {
      orden_id: ordenId.value,
      origen: 'marketplace',
      sucursal_id: 'SUC-LP-CENTRAL',
      items: [
        {
          sku: ventaSku.value,
          nombre: ventaNombre.value,
          cantidad: ventaCantidad.value
        }
      ]
    });
    lastResult.value = res.data.evento;
    // Generar nuevo ID para la siguiente prueba
    ordenId.value = `ORD-SYS-${Date.now().toString(36).toUpperCase()}`;
    await fetchStatus();
    await fetchHistorial();
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.response?.data?.error || err.message || 'Error al enviar descuento';
  } finally {
    loading.value = false;
  }
}

async function enviarReintegroStock() {
  loading.value = true;
  errorMessage.value = '';
  lastResult.value = null;
  try {
    const res = await apiClient.post('/v1/ordenes/integraciones/pubsub/reintegro-stock', {
      orden_id: reintegroOrdenId.value,
      motivo: reintegroMotivo.value,
      origen: 'marketplace',
      sucursal_id: 'SUC-LP-CENTRAL',
      items: [
        {
          sku: reintegroSku.value,
          cantidad: reintegroCantidad.value
        }
      ]
    });
    lastResult.value = res.data.evento;
    reintegroOrdenId.value = `ORD-DEV-${Date.now().toString(36).toUpperCase()}`;
    await fetchStatus();
    await fetchHistorial();
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.response?.data?.error || err.message || 'Error al enviar reintegro';
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchStatus();
  fetchHistorial();
});
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
    <div class="relative w-full max-w-3xl bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 flex flex-col max-h-[90vh] overflow-hidden">
      
      <!-- Encabezado Modal -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-blue-600/10 via-cyan-500/10 to-transparent">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md">
            <Radio class="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-lg font-bold text-slate-900 dark:text-white">
                Sincronización con ERP de Inventarios
              </h2>
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                KAN-56 / RF-40
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400">
              Transmisión de eventos a Google Cloud Pub/Sub (Cátedra UCB SIS-323 · Grupo E)
            </p>
          </div>
        </div>

        <button 
          @click="emit('close')"
          class="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Banner de Estado de Conexión en Tiempo Real -->
      <div class="px-6 py-3 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div class="flex items-center gap-2">
          <span class="relative flex h-2.5 w-2.5">
            <span v-if="statusData?.hasCredentialsFile" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span :class="['relative inline-flex h-2.5 w-2.5 rounded-full', statusData?.hasCredentialsFile ? 'bg-emerald-500' : 'bg-amber-500']"></span>
          </span>
          <span class="font-semibold text-slate-700 dark:text-slate-200">
            {{ statusData?.hasCredentialsFile ? 'Credenciales detectadas (pendiente de validar envío)' : 'Modo offline: faltan credenciales' }}
          </span>
          <span class="text-slate-400">|</span>
          <span class="text-slate-600 dark:text-slate-300 font-mono text-[11px] truncate max-w-xs" :title="statusData?.topic">
            {{ statusData?.topic || 'projects/.../topics/ucb-sis323-sub-e' }}
          </span>
        </div>

        <div class="flex items-center gap-2 text-slate-500">
          <Terminal class="w-3.5 h-3.5 text-blue-500" />
          <span class="text-[11px] font-medium text-blue-600 dark:text-blue-400">
            Salida activa en la terminal
          </span>
          <button 
            @click="fetchStatus(); fetchHistorial()" 
            class="p-1 hover:text-blue-600 transition"
            title="Actualizar estado"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
          </button>
        </div>
      </div>

      <!-- Pestañas de Acción del Sistema -->
      <div class="flex border-b border-slate-200 dark:border-slate-800 px-6 pt-2 bg-slate-50/50 dark:bg-slate-900/50 gap-2 overflow-x-auto">
        <button
          @click="activeTab = 'prueba_docente'"
          :class="[
            'pb-2 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-all',
            activeTab === 'prueba_docente'
              ? 'border-blue-600 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          ]"
        >
          <Send class="w-3.5 h-3.5" />
          Prueba para el Docente
        </button>

        <button
          @click="activeTab = 'venta_stock'"
          :class="[
            'pb-2 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-all',
            activeTab === 'venta_stock'
              ? 'border-blue-600 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          ]"
        >
          <ShoppingBag class="w-3.5 h-3.5" />
          Simular Venta (Descuento Stock)
        </button>

        <button
          @click="activeTab = 'reintegro'"
          :class="[
            'pb-2 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-all',
            activeTab === 'reintegro'
              ? 'border-blue-600 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          ]"
        >
          <RotateCcw class="w-3.5 h-3.5" />
          Simular Reintegro / Devolución
        </button>

        <button
          @click="activeTab = 'historial'"
          :class="[
            'pb-2 px-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition-all',
            activeTab === 'historial'
              ? 'border-blue-600 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-slate-500 hover:text-slate-900'
          ]"
        >
          <Server class="w-3.5 h-3.5" />
          Historial de Eventos ({{ historial.length }})
        </button>
      </div>

      <!-- Contenido del Modal -->
      <div class="p-6 overflow-y-auto space-y-4 flex-1">
        
        <!-- PESTAÑA 1: PRUEBA DOCENTE -->
        <div v-if="activeTab === 'prueba_docente'" class="space-y-4">
          <div class="bg-blue-50 dark:bg-blue-950/40 p-4 rounded-xl border border-blue-200 dark:border-blue-800/60 text-xs text-blue-900 dark:text-blue-200">
            <p class="font-semibold mb-1 flex items-center gap-1.5">
              <ShieldCheck class="w-4 h-4 text-blue-600" />
              Verificación de Recepción de la Cátedra
            </p>
            Al pulsar el botón, el sistema intentará publicar el mensaje con tus datos en el tópico
            <code class="font-mono bg-blue-100 dark:bg-blue-900/60 px-1 py-0.5 rounded">projects/.../ucb-sis323-sub-e</code>.
            Si Pub/Sub lo acepta, verás aquí y en la <strong>terminal</strong> el <strong>Message ID</strong>. Para comprobar el consumo, consulta una suscripción del tópico.
          </div>

          <div class="grid grid-cols-1 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Responsable del Equipo (Alumno):
              </label>
              <input 
                v-model="responsable" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Detalle del Mensaje de Prueba:
              </label>
              <textarea 
                v-model="detalleMensaje" 
                rows="2"
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              ></textarea>
            </div>
          </div>

          <button
            @click="enviarPruebaDocente"
            :disabled="loading"
            class="w-full py-2.5 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl font-bold text-xs shadow-md flex items-center justify-center gap-2 transition disabled:opacity-50"
          >
            <Send class="w-4 h-4" :class="{ 'animate-pulse': loading }" />
            {{ loading ? 'Transmitiendo a Google Cloud Pub/Sub...' : 'Enviar Mensaje desde el Sistema al Docente' }}
          </button>
        </div>

        <!-- PESTAÑA 2: VENTA / DESCUENTO STOCK -->
        <div v-else-if="activeTab === 'venta_stock'" class="space-y-4">
          <div class="bg-slate-50 dark:bg-slate-800/40 p-3 rounded-xl border border-slate-200 dark:border-slate-700 text-xs">
            <p class="font-semibold text-slate-800 dark:text-slate-200 mb-1">
              Simulación de Compra — Requerimiento RIO-INV-03
            </p>
            Simula que un cliente compró productos en el Marketplace o en el POS. El sistema emite el evento <code>stock.descuento</code> hacia Google Cloud Pub/Sub para que el sistema de Inventarios descuente las existencias.
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Código de Orden:
              </label>
              <input 
                v-model="ordenId" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                SKU Producto:
              </label>
              <input 
                v-model="ventaSku" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Nombre Producto:
              </label>
              <input 
                v-model="ventaNombre" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Cantidad a Descontar:
              </label>
              <input 
                v-model.number="ventaCantidad" 
                type="number" 
                min="1"
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              />
            </div>
          </div>

          <button
            @click="enviarVentaStock"
            :disabled="loading"
            class="w-full py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold text-xs shadow-md flex items-center justify-center gap-2 transition disabled:opacity-50"
          >
            <ShoppingBag class="w-4 h-4" />
            {{ loading ? 'Publicando descuento a Pub/Sub...' : 'Simular Compra y Descontar Stock en Inventarios' }}
          </button>
        </div>

        <!-- PESTAÑA 3: REINTEGRO / DEVOLUCIÓN -->
        <div v-else-if="activeTab === 'reintegro'" class="space-y-4">
          <div class="bg-amber-50 dark:bg-amber-950/30 p-3 rounded-xl border border-amber-200 dark:border-amber-800/60 text-xs text-amber-900 dark:text-amber-200">
            <p class="font-semibold mb-1">
              Simulación de Devolución — Requerimiento RIO-INV-04
            </p>
            Simula la anulación de una compra o devolución de cliente. Emite el evento <code>stock.reintegro</code> hacia Pub/Sub para reponer las existencias en el inventario central.
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Orden a Anular:
              </label>
              <input 
                v-model="reintegroOrdenId" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                SKU Producto:
              </label>
              <input 
                v-model="reintegroSku" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono"
              />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Cantidad a Reintegrar:
              </label>
              <input
                v-model.number="reintegroCantidad"
                type="number"
                min="1"
                max="10000"
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              />
            </div>
            <div class="col-span-2">
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Motivo de Devolución:
              </label>
              <input 
                v-model="reintegroMotivo" 
                type="text" 
                class="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800"
              />
            </div>
          </div>

          <button
            @click="enviarReintegroStock"
            :disabled="loading"
            class="w-full py-2.5 px-4 bg-amber-600 hover:bg-amber-700 text-white rounded-xl font-bold text-xs shadow-md flex items-center justify-center gap-2 transition disabled:opacity-50"
          >
            <RotateCcw class="w-4 h-4" />
            {{ loading ? 'Publicando reintegro a Pub/Sub...' : 'Emitir Reintegro de Existencias a Inventarios' }}
          </button>
        </div>

        <!-- PESTAÑA 4: HISTORIAL -->
        <div v-else-if="activeTab === 'historial'" class="space-y-3">
          <div v-if="historial.length === 0" class="text-center py-8 text-xs text-slate-400">
            No se han emitido eventos en esta sesión todavía.
          </div>
          <div v-else class="space-y-2 max-h-72 overflow-y-auto pr-1">
            <div 
              v-for="item in historial" 
              :key="item.event_id"
              class="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 text-xs space-y-1"
            >
              <div class="flex items-center justify-between">
                <span class="font-bold text-blue-600 dark:text-blue-400 font-mono">
                  {{ item.event_type }}
                </span>
                <span 
                  :class="[
                    'px-2 py-0.5 rounded-full font-bold text-[10px]',
                    item.status === 'PUBLICADO' 
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300'
                  ]"
                >
                  {{ item.status }}
                </span>
              </div>
              <div class="text-[11px] text-slate-500 font-mono">
                Message ID: <strong class="text-slate-800 dark:text-slate-200">{{ item.message_id }}</strong>
              </div>
              <div class="text-[11px] text-slate-400">
                {{ item.timestamp }}
              </div>
            </div>
          </div>
        </div>

        <!-- ERROR SI EXISTIERA -->
        <div v-if="errorMessage" class="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ errorMessage }}</span>
        </div>

        <!-- CAJA DE CONFIRMACIÓN DE LLEGADA / RESPUESTA EN VIVO -->
        <div v-if="lastResult" :class="[
          'p-4 rounded-xl border space-y-2',
          lastResult.status === 'PUBLICADO'
            ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800'
            : 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800'
        ]">
          <div class="flex items-center justify-between">
            <div :class="[
              'flex items-center gap-2 font-bold text-xs',
              lastResult.status === 'PUBLICADO' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-200'
            ]">
              <CheckCircle2 v-if="lastResult.status === 'PUBLICADO'" class="w-4 h-4" />
              <AlertCircle v-else class="w-4 h-4" />
              <span>{{ lastResult.status === 'PUBLICADO' ? 'Pub/Sub aceptó el mensaje' : 'Mensaje no publicado en Google Cloud' }}</span>
            </div>
            <span :class="[
              'text-[11px] font-mono px-2 py-0.5 rounded-full font-bold',
              lastResult.status === 'PUBLICADO' ? 'bg-emerald-100 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200' : 'bg-amber-100 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200'
            ]">
              ID: {{ lastResult.message_id }}
            </span>
          </div>

          <div class="text-xs text-slate-600 dark:text-slate-300 space-y-1">
            <p><strong>Tópico:</strong> <span class="font-mono text-[11px]">{{ lastResult.topic }}</span></p>
            <p><strong>Evento:</strong> {{ lastResult.event_type }} ({{ lastResult.event_id }})</p>
            <p :class="[
              'text-[11px] font-medium',
              lastResult.status === 'PUBLICADO' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-200'
            ]">
              {{ lastResult.status === 'PUBLICADO' ? 'Confirmación de publicación registrada en la terminal.' : (lastResult.error || 'Agrega credenciales válidas y vuelve a intentar.') }}
            </p>
          </div>

          <div class="mt-2 bg-slate-900 text-slate-100 p-2.5 rounded-lg text-[11px] font-mono max-h-36 overflow-y-auto">
            <pre>{{ JSON.stringify(lastResult.payload, null, 2) }}</pre>
          </div>
        </div>

      </div>

      <!-- Pie del Modal -->
      <div class="px-6 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex items-center justify-between text-xs text-slate-500">
        <div class="flex items-center gap-1.5">
          <Terminal class="w-3.5 h-3.5" />
          <span>También puedes ejecutar: <code>python3 scripts/test_pubsub_cli.py --all</code></span>
        </div>
        <button 
          @click="emit('close')"
          class="px-4 py-1.5 bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg font-semibold transition"
        >
          Cerrar
        </button>
      </div>

    </div>
  </div>
</template>
