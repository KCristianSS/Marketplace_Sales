<script setup lang="ts">
import { ref } from 'vue';
import { 
  TrendingUp, 
  ShoppingBag, 
  DollarSign, 
  Users, 
  Package, 
  FileText, 
  AlertTriangle,
  ArrowUpRight 
} from 'lucide-vue-next';

const kpis = ref({
  ventasHoy: 15420.50,
  ventasMes: 348920.00,
  ordenesHoy: 34,
  ticketPromedio: 453.54,
  tasaConversion: 3.85
});

const recentOrders = ref([
  { id: 'ORD-2026-081', cliente: 'Carlos Mendoza', total: 8999.00, canal: 'Web', estado: 'Confirmada', fecha: '12/09 10:45' },
  { id: 'ORD-2026-080', cliente: 'Empresa Minera San Cristóbal (B2B)', total: 45000.00, canal: 'B2B', estado: 'En Preparación', fecha: '12/09 09:30' },
  { id: 'POS-2026-112', cliente: 'Cliente Mostrador', total: 1598.00, canal: 'POS', estado: 'Entregada', fecha: '12/09 09:12' },
  { id: 'ORD-2026-079', cliente: 'Sofía Doria Medina', total: 2450.00, canal: 'Web', estado: 'Despachada', fecha: '11/09 18:20' }
]);

const lowStockAlerts = ref([
  { sku: 'MON-LG-27GP', nombre: 'Monitor LG UltraGear 27"', stockActual: 2, puntoReorden: 5 },
  { sku: 'LAP-DELL-XPS15', nombre: 'Laptop Dell XPS 15', stockActual: 3, puntoReorden: 8 }
]);
</script>

<template>
  <div class="space-y-8">
    <!-- Header Panel Administrativo -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
      <div>
        <h1 class="text-2xl font-extrabold text-slate-900 dark:text-white">Panel de Control y Analítica</h1>
        <p class="text-xs text-slate-500 mt-1">Supervisión omnicanal de ventas, catálogo y operaciones ERP en tiempo real.</p>
      </div>
      <div class="flex gap-2">
        <button class="px-3.5 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-xs font-semibold rounded-lg">
          Exportar Reporte
        </button>
        <button class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm">
          + Nuevo Producto
        </button>
      </div>
    </div>

    <!-- Cards de KPIs Clave (RF-46) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
        <div class="flex justify-between items-center text-slate-500">
          <span class="text-xs font-semibold">Ventas Totales Hoy</span>
          <span class="p-2 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 rounded-lg"><DollarSign class="w-4 h-4" /></span>
        </div>
        <div class="text-2xl font-bold text-slate-900 dark:text-white">BOB {{ kpis.ventasHoy.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}</div>
        <span class="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
          <ArrowUpRight class="w-3.5 h-3.5" /> +14.2% vs ayer
        </span>
      </div>

      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
        <div class="flex justify-between items-center text-slate-500">
          <span class="text-xs font-semibold">Ventas del Mes</span>
          <span class="p-2 bg-blue-50 dark:bg-blue-950/40 text-blue-600 rounded-lg"><TrendingUp class="w-4 h-4" /></span>
        </div>
        <div class="text-2xl font-bold text-slate-900 dark:text-white">BOB {{ kpis.ventasMes.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}</div>
        <span class="text-[11px] text-blue-600 font-semibold flex items-center gap-1">
          <ArrowUpRight class="w-3.5 h-3.5" /> Meta mensual: 87%
        </span>
      </div>

      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
        <div class="flex justify-between items-center text-slate-500">
          <span class="text-xs font-semibold">Órdenes Procesadas Hoy</span>
          <span class="p-2 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 rounded-lg"><ShoppingBag class="w-4 h-4" /></span>
        </div>
        <div class="text-2xl font-bold text-slate-900 dark:text-white">{{ kpis.ordenesHoy }}</div>
        <span class="text-[11px] text-slate-400">Canal Web (22) / POS (12)</span>
      </div>

      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
        <div class="flex justify-between items-center text-slate-500">
          <span class="text-xs font-semibold">Ticket Promedio</span>
          <span class="p-2 bg-purple-50 dark:bg-purple-950/40 text-purple-600 rounded-lg"><Users class="w-4 h-4" /></span>
        </div>
        <div class="text-2xl font-bold text-slate-900 dark:text-white">BOB {{ kpis.ticketPromedio.toFixed(2) }}</div>
        <span class="text-[11px] text-purple-600 font-semibold">Conversión: {{ kpis.tasaConversion }}%</span>
      </div>
    </div>

    <!-- Grilla de Tablas Operativas -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Tabla de Órdenes Recientes -->
      <div class="lg:col-span-2 bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-sm font-bold text-slate-800 dark:text-white flex items-center gap-2">
            <FileText class="w-4 h-4 text-blue-500" /> Órdenes y Ventas Recientes (RF-27 al RF-37)
          </h3>
          <router-link to="/admin" class="text-xs text-blue-600 hover:underline font-semibold">Ver todas</router-link>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 dark:bg-slate-800 text-slate-500 font-semibold">
              <tr>
                <th class="p-2.5">Código</th>
                <th class="p-2.5">Cliente</th>
                <th class="p-2.5">Canal</th>
                <th class="p-2.5">Total</th>
                <th class="p-2.5">Estado</th>
                <th class="p-2.5">Fecha</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="ord in recentOrders" :key="ord.id">
                <td class="p-2.5 font-mono font-bold text-blue-600">{{ ord.id }}</td>
                <td class="p-2.5 text-slate-800 dark:text-slate-200 font-medium">{{ ord.cliente }}</td>
                <td class="p-2.5">
                  <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 dark:bg-slate-800 uppercase">{{ ord.canal }}</span>
                </td>
                <td class="p-2.5 font-bold">BOB {{ ord.total.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}</td>
                <td class="p-2.5">
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                    {{ ord.estado }}
                  </span>
                </td>
                <td class="p-2.5 text-slate-400">{{ ord.fecha }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Alertas de Stock y Quiebre (RF-42) -->
      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div class="flex items-center gap-2 text-rose-600 font-bold text-sm">
          <AlertTriangle class="w-4 h-4" />
          <span>Alertas de Quiebre de Stock (RF-42)</span>
        </div>
        <p class="text-xs text-slate-400">Productos que alcanzaron el punto de reorden para Compras:</p>

        <div class="space-y-3">
          <div
            v-for="alert in lowStockAlerts"
            :key="alert.sku"
            class="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-lg space-y-1"
          >
            <div class="flex justify-between items-start">
              <span class="text-xs font-bold text-slate-800 dark:text-slate-200">{{ alert.nombre }}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 bg-rose-200 dark:bg-rose-900 text-rose-800 dark:text-rose-200 rounded font-bold">
                Quedan {{ alert.stockActual }}
              </span>
            </div>
            <div class="text-[11px] text-slate-500 flex justify-between">
              <span>SKU: {{ alert.sku }}</span>
              <span>Reorden: {{ alert.puntoReorden }}</span>
            </div>
          </div>
        </div>

        <button class="w-full py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300 text-xs font-bold rounded-lg mt-2">
          Disparar Solicitud a Compras (ERP)
        </button>
      </div>
    </div>
  </div>
</template>
