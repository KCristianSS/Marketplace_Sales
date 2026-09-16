<script setup lang="ts">
import { ref, computed } from 'vue';
import { 
  Scan, 
  Trash2, 
  PauseCircle, 
  PlayCircle, 
  CreditCard, 
  Banknote, 
  QrCode, 
  Printer, 
  CheckCircle, 
  Store 
} from 'lucide-vue-next';

interface PosItem {
  id: string;
  sku: string;
  nombre: string;
  precio: number;
  cantidad: number;
}

const skuInput = ref('');
const cajaAbierta = ref(true);
const sucursalNombre = ref('Sucursal Central - La Paz');
const cajeroNombre = ref('Cajero: Oscar Menacho (Turno Mañana)');

const cartItems = ref<PosItem[]>([
  { id: '1', sku: 'LAP-DELL-XPS15', nombre: 'Laptop Dell XPS 15', precio: 8999.00, cantidad: 1 },
  { id: '2', sku: 'MOU-LOG-MX3S', nombre: 'Mouse Logitech MX Master 3S', precio: 799.00, cantidad: 2 }
]);

const suspendedSales = ref<{ id: string; ticket: string; total: number; items: PosItem[] }[]>([]);

const subtotal = computed(() => cartItems.value.reduce((acc, curr) => acc + (curr.precio * curr.cantidad), 0));
const total = computed(() => subtotal.value);

// Modal de Cobro
const isPayModalOpen = ref(false);
const payMethod = ref<'efectivo' | 'tarjeta' | 'qr'>('efectivo');
const cashGiven = ref<number>(11000);
const changeDue = computed(() => Math.max(0, (cashGiven.value || 0) - total.value));
const isReceiptReady = ref(false);

function addItemByBarcode() {
  if (!skuInput.value.trim()) return;
  const sku = skuInput.value.trim().toUpperCase();
  cartItems.value.push({
    id: Date.now().toString(),
    sku: sku,
    nombre: `Artículo Escaneado [${sku}]`,
    precio: 150.00,
    cantidad: 1
  });
  skuInput.value = '';
}

function removeItem(id: string) {
  cartItems.value = cartItems.value.filter(i => i.id !== id);
}

function suspenderVenta() {
  if (cartItems.value.length === 0) return;
  suspendedSales.value.push({
    id: Date.now().toString(),
    ticket: `Ticket #${suspendedSales.value.length + 1}`,
    total: total.value,
    items: [...cartItems.value]
  });
  cartItems.value = [];
}

function reanudarVenta(index: number) {
  const sale = suspendedSales.value.splice(index, 1)[0];
  cartItems.value = sale.items;
}

function finalizarCobro() {
  isReceiptReady.value = true;
}

function resetPos() {
  cartItems.value = [];
  isPayModalOpen.value = false;
  isReceiptReady.value = false;
}
</script>

<template>
  <div class="h-[calc(100vh-8rem)] flex flex-col gap-4">
    <!-- Header de Caja y Turno (RF-09) -->
    <div class="bg-slate-900 text-white px-5 py-3 rounded-xl flex justify-between items-center shadow-md">
      <div class="flex items-center gap-3">
        <Store class="w-5 h-5 text-cyan-400" />
        <div>
          <h2 class="text-sm font-bold">{{ sucursalNombre }}</h2>
          <p class="text-xs text-slate-400">{{ cajeroNombre }}</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Caja Abierta
        </span>
        <button class="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 font-medium">
          Arqueo / Cierre
        </button>
      </div>
    </div>

    <!-- Contenido Principal POS -->
    <div class="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden">
      <!-- Columna Izquierda: Escáner y Tabla de Ítems -->
      <div class="lg:col-span-2 flex flex-col bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-4 overflow-hidden">
        <!-- Input Barcode -->
        <form @submit.prevent="addItemByBarcode" class="flex gap-2 mb-4">
          <div class="relative flex-1">
            <Scan class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              v-model="skuInput"
              type="text"
              autofocus
              placeholder="Escanear código de barras o escribir SKU y presionar ENTER..."
              class="w-full pl-10 pr-4 py-2.5 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-600 focus:outline-none font-mono"
            />
          </div>
          <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-medium text-sm">
            Agregar
          </button>
        </form>

        <!-- Tabla de Productos Escaneados -->
        <div class="flex-1 overflow-y-auto border border-slate-100 dark:border-slate-800 rounded-lg">
          <table class="w-full text-left text-sm">
            <thead class="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold sticky top-0">
              <tr>
                <th class="p-3">SKU</th>
                <th class="p-3">Descripción</th>
                <th class="p-3 text-center">Cant.</th>
                <th class="p-3 text-right">Precio</th>
                <th class="p-3 text-right">Total</th>
                <th class="p-3 text-center">Acción</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="item in cartItems" :key="item.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td class="p-3 font-mono text-xs font-semibold text-blue-600 dark:text-blue-400">{{ item.sku }}</td>
                <td class="p-3 text-slate-800 dark:text-slate-200">{{ item.nombre }}</td>
                <td class="p-3 text-center">
                  <span class="inline-block px-2 py-0.5 bg-slate-100 dark:bg-slate-800 font-bold rounded">{{ item.cantidad }}</span>
                </td>
                <td class="p-3 text-right">BOB {{ item.precio.toFixed(2) }}</td>
                <td class="p-3 text-right font-bold text-slate-900 dark:text-white">BOB {{ (item.precio * item.cantidad).toFixed(2) }}</td>
                <td class="p-3 text-center">
                  <button @click="removeItem(item.id)" class="text-rose-500 hover:text-rose-700 p-1">
                    <Trash2 class="w-4 h-4" />
                  </button>
                </td>
              </tr>
              <tr v-if="cartItems.length === 0">
                <td colspan="6" class="p-8 text-center text-slate-400">
                  No hay productos escaneados en esta transacción.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Ventas Suspendidas (RF-12) -->
        <div v-if="suspendedSales.length > 0" class="mt-4 p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-lg flex items-center justify-between">
          <div class="flex items-center gap-2 text-amber-800 dark:text-amber-300 text-xs font-semibold">
            <PauseCircle class="w-4 h-4 text-amber-600" />
            <span>{{ suspendedSales.length }} venta(s) suspendida(s) en espera:</span>
          </div>
          <div class="flex gap-2">
            <button
              v-for="(s, idx) in suspendedSales"
              :key="s.id"
              @click="reanudarVenta(idx)"
              class="text-xs bg-amber-600 hover:bg-amber-700 text-white px-2.5 py-1 rounded font-medium flex items-center gap-1 shadow-sm"
            >
              <PlayCircle class="w-3.5 h-3.5" /> {{ s.ticket }} (BOB {{ s.total.toFixed(2) }})
            </button>
          </div>
        </div>
      </div>

      <!-- Columna Derecha: Panel de Cobro y Totales -->
      <div class="flex flex-col justify-between bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-5">
        <div class="space-y-4">
          <h3 class="text-base font-bold text-slate-800 dark:text-slate-100 border-b border-slate-100 dark:border-slate-800 pb-2">
            Resumen de Cobro
          </h3>

          <div class="space-y-2 text-sm text-slate-600 dark:text-slate-400">
            <div class="flex justify-between">
              <span>Ítems totales:</span>
              <span class="font-bold text-slate-800 dark:text-slate-200">{{ cartItems.reduce((a, c) => a + c.cantidad, 0) }}</span>
            </div>
            <div class="flex justify-between">
              <span>Subtotal:</span>
              <span>BOB {{ subtotal.toFixed(2) }}</span>
            </div>
            <div class="flex justify-between">
              <span>Impuestos (IVA 13% incluido):</span>
              <span>BOB {{ (total * 0.13).toFixed(2) }}</span>
            </div>
          </div>

          <!-- Total Destacado -->
          <div class="bg-blue-50 dark:bg-blue-950/40 p-4 rounded-xl border border-blue-200 dark:border-blue-900 text-center">
            <span class="text-xs uppercase font-bold text-blue-600 dark:text-blue-400 tracking-wider">Total a Cobrar</span>
            <div class="text-3xl font-extrabold text-blue-700 dark:text-blue-300 mt-1">
              BOB {{ total.toFixed(2) }}
            </div>
          </div>
        </div>

        <!-- Botonera de Acción -->
        <div class="space-y-2.5 pt-4">
          <button
            @click="isPayModalOpen = true"
            :disabled="cartItems.length === 0"
            class="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 active:scale-98"
          >
            <Banknote class="w-5 h-5" /> Cobrar Transacción [F12]
          </button>

          <button
            @click="suspenderVenta"
            :disabled="cartItems.length === 0"
            class="w-full py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-semibold text-xs rounded-xl flex items-center justify-center gap-2"
          >
            <PauseCircle class="w-4 h-4 text-amber-500" /> Suspender Venta [F4]
          </button>
        </div>
      </div>
    </div>

    <!-- Modal de Cobro y Factura Rápida (RF-10) -->
    <div v-if="isPayModalOpen" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white dark:bg-slate-900 w-full max-w-lg rounded-2xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-5">
        <div v-if="!isReceiptReady" class="space-y-4">
          <h3 class="text-lg font-bold text-slate-800 dark:text-white">Procesar Cobro en Caja</h3>
          
          <!-- Método de Pago -->
          <div class="grid grid-cols-3 gap-3">
            <button
              @click="payMethod = 'efectivo'"
              :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold', payMethod === 'efectivo' ? 'border-emerald-600 bg-emerald-50 text-emerald-700' : 'border-slate-200']"
            >
              <Banknote class="w-5 h-5" /> Efectivo
            </button>
            <button
              @click="payMethod = 'tarjeta'"
              :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold', payMethod === 'tarjeta' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200']"
            >
              <CreditCard class="w-5 h-5" /> Tarjeta POS
            </button>
            <button
              @click="payMethod = 'qr'"
              :class="['p-3 rounded-xl border flex flex-col items-center gap-1 text-xs font-bold', payMethod === 'qr' ? 'border-purple-600 bg-purple-50 text-purple-700' : 'border-slate-200']"
            >
              <QrCode class="w-5 h-5" /> QR Simple
            </button>
          </div>

          <!-- Monto Recibido y Cambio -->
          <div v-if="payMethod === 'efectivo'" class="space-y-3 bg-slate-50 dark:bg-slate-800 p-4 rounded-xl">
            <div class="flex justify-between items-center">
              <label class="text-xs font-semibold">Monto Recibido (BOB):</label>
              <input
                v-model.number="cashGiven"
                type="number"
                class="w-32 text-right font-bold text-base p-1.5 border border-slate-300 rounded-lg"
              />
            </div>
            <div class="flex justify-between items-center text-sm font-bold text-emerald-600">
              <span>Cambio a Entregar:</span>
              <span class="text-lg">BOB {{ changeDue.toFixed(2) }}</span>
            </div>
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button @click="isPayModalOpen = false" class="px-4 py-2 text-sm text-slate-500 font-medium">Cancelar</button>
            <button @click="finalizarCobro" class="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm rounded-lg">
              Confirmar e Imprimir Factura
            </button>
          </div>
        </div>

        <!-- Ticket Emitido y Timbrado CUF (RF-10, RIO-PAG-02) -->
        <div v-else class="space-y-4 text-center">
          <div class="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
            <CheckCircle class="w-6 h-6" />
          </div>
          <h3 class="text-lg font-bold text-slate-900 dark:text-white">¡Venta y Factura Electrónica Emitidas!</h3>
          <p class="text-xs text-slate-500">
            Factura timbrada con código CUF: <code class="font-mono bg-slate-100 p-1 rounded">CUF-9F2A-881B-2026</code>
          </p>
          <div class="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg text-left text-xs font-mono">
            <div>Orden: POS-A8B9</div>
            <div>Total: BOB {{ total.toFixed(2) }}</div>
            <div>Método: {{ payMethod.toUpperCase() }}</div>
          </div>
          <div class="flex justify-center gap-3">
            <button @click="resetPos" class="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg flex items-center gap-2">
              <Printer class="w-4 h-4" /> Imprimir Ticket y Nueva Venta
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
