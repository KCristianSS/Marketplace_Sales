<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { 
  DollarSign, 
  Plus, 
  Trash2, 
  Edit3, 
  Check, 
  X, 
  Layers, 
  Sparkles, 
  Calculator, 
  Store, 
  Globe, 
  Building2, 
  Clock, 
  RefreshCw,
  Search,
  CheckCircle2,
  AlertCircle
} from 'lucide-vue-next';
import { 
  obtenerListasPrecios, 
  crearListaPrecio, 
  actualizarListaPrecio, 
  eliminarListaPrecio,
  obtenerItemsListaPrecio,
  asignarPrecioItem,
  eliminarPrecioItem,
  resolverPrecioVariante
} from '@/api/catalogo';
import { apiClient } from '@/api/client';
import type { ListaPrecio, PrecioItem, PrecioResolucion, Producto } from '@/types';

const listas = ref<ListaPrecio[]>([]);
const isLoading = ref(false);
const errorMsg = ref('');
const successMsg = ref('');

// Moneda dual global de visualización
const displayCurrency = ref<'BOB' | 'USD'>('BOB');
const TIPO_CAMBIO_USD = 6.96; // 1 USD = 6.96 BOB

function formatCurrency(amount: number, sourceCurrency: string = 'BOB'): string {
  if (displayCurrency.value === 'USD') {
    const inUsd = sourceCurrency === 'USD' ? amount : amount / TIPO_CAMBIO_USD;
    return `$ ${inUsd.toFixed(2)} USD`;
  } else {
    const inBob = sourceCurrency === 'BOB' ? amount : amount * TIPO_CAMBIO_USD;
    return `Bs. ${inBob.toFixed(2)}`;
  }
}

// Catálogo de productos para asignación
const catalogProducts = ref<Producto[]>([]);

// Modal Crear/Editar Lista
const isListModalOpen = ref(false);
const isEditingList = ref(false);
const editingListId = ref<string | null>(null);
const listForm = ref({
  nombre: '',
  canal: 'web' as 'web' | 'pos' | 'b2b',
  tipo_cliente: 'retail' as 'retail' | 'corporativo_b2b',
  sucursal_id: '' as string,
  moneda: 'BOB' as 'BOB' | 'USD',
  activo: true
});

// Modal Gestión de Tarifas / Items
const isItemsModalOpen = ref(false);
const activeListForItems = ref<ListaPrecio | null>(null);
const currentListItems = ref<PrecioItem[]>([]);
const isLoadingItems = ref(false);
const newItemForm = ref({
  variante_id: '',
  precio: 0,
  fecha_inicio: '',
  fecha_fin: ''
});

// Simulador de Resolución de Precios
const simProduct = ref('');
const simCanal = ref<'web' | 'pos' | 'b2b'>('web');
const simTipoCliente = ref<'retail' | 'corporativo_b2b'>('retail');
const simSucursal = ref('');
const simResult = ref<PrecioResolucion | null>(null);
const isSimulating = ref(false);

const sucursalesDisponibles = [
  { id: '', nombre: 'Todas / Multicanal General' },
  { id: 'SUC-LP-CENTRAL', nombre: 'Sucursal Central - La Paz' },
  { id: 'SUC-LP-SOPOCACHI', nombre: 'Sucursal Sopocachi - La Paz' },
  { id: 'SUC-SCZ-EQUIPETROL', nombre: 'Sucursal Equipetrol - Santa Cruz' },
  { id: 'SUC-CBB-CENTRO', nombre: 'Sucursal Centro - Cochabamba' }
];

async function loadListas() {
  isLoading.value = true;
  errorMsg.value = '';
  try {
    listas.value = await obtenerListasPrecios();
  } catch (err: any) {
    errorMsg.value = 'No se pudieron cargar las listas de precios.';
  } finally {
    isLoading.value = false;
  }
}

async function loadProducts() {
  try {
    const res = await apiClient.get('/api/v1/catalogo/productos');
    const data = res.data.productos || res.data || [];
    catalogProducts.value = Array.isArray(data) ? data : [];
    if (catalogProducts.value.length > 0 && !simProduct.value) {
      simProduct.value = catalogProducts.value[0].id;
    }
  } catch (err) {
    console.warn('Error cargando catálogo:', err);
  }
}

onMounted(() => {
  loadListas();
  loadProducts();
});

function openCreateListModal() {
  isEditingList.value = false;
  editingListId.value = null;
  listForm.value = {
    nombre: '',
    canal: 'web',
    tipo_cliente: 'retail',
    sucursal_id: '',
    moneda: 'BOB',
    activo: true
  };
  isListModalOpen.value = true;
}

function openEditListModal(lp: ListaPrecio) {
  isEditingList.value = true;
  editingListId.value = lp.id;
  listForm.value = {
    nombre: lp.nombre,
    canal: lp.canal,
    tipo_cliente: lp.tipo_cliente,
    sucursal_id: lp.sucursal_id || '',
    moneda: lp.moneda,
    activo: lp.activo
  };
  isListModalOpen.value = true;
}

async function saveListForm() {
  if (!listForm.value.nombre.trim()) return;
  try {
    if (isEditingList.value && editingListId.value) {
      await actualizarListaPrecio(editingListId.value, {
        nombre: listForm.value.nombre,
        canal: listForm.value.canal,
        tipo_cliente: listForm.value.tipo_cliente,
        sucursal_id: listForm.value.sucursal_id || null,
        moneda: listForm.value.moneda,
        activo: listForm.value.activo
      });
      successMsg.value = 'Lista de precios actualizada con éxito.';
    } else {
      await crearListaPrecio({
        nombre: listForm.value.nombre,
        canal: listForm.value.canal,
        tipo_cliente: listForm.value.tipo_cliente,
        sucursal_id: listForm.value.sucursal_id || null,
        moneda: listForm.value.moneda,
        activo: listForm.value.activo
      });
      successMsg.value = 'Lista de precios creada con éxito.';
    }
    isListModalOpen.value = false;
    await loadListas();
    setTimeout(() => successMsg.value = '', 4000);
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Error al guardar lista de precios');
  }
}

async function handleDeleteList(id: string) {
  if (!confirm('¿Estás seguro de eliminar esta lista de precios?')) return;
  try {
    await eliminarListaPrecio(id);
    await loadListas();
    successMsg.value = 'Lista eliminada correctamente.';
    setTimeout(() => successMsg.value = '', 3500);
  } catch (err) {
    alert('Error al eliminar la lista de precios.');
  }
}

// Gestión de Tarifas por Ítem
async function openItemsModal(lp: ListaPrecio) {
  activeListForItems.value = lp;
  isItemsModalOpen.value = true;
  isLoadingItems.value = true;
  newItemForm.value = {
    variante_id: catalogProducts.value[0]?.id || '',
    precio: Number(catalogProducts.value[0]?.precio || 100),
    fecha_inicio: '',
    fecha_fin: ''
  };
  try {
    currentListItems.value = await obtenerItemsListaPrecio(lp.id);
  } catch (err) {
    currentListItems.value = [];
  } finally {
    isLoadingItems.value = false;
  }
}

function onSelectProductInItemForm() {
  const prod = catalogProducts.value.find(p => p.id === newItemForm.value.variante_id);
  if (prod && prod.precio) {
    if (activeListForItems.value?.tipo_cliente === 'corporativo_b2b') {
      newItemForm.value.precio = Math.round(Number(prod.precio) * 0.85); // Sugerir 15% B2B
    } else {
      newItemForm.value.precio = Number(prod.precio);
    }
  }
}

async function handleAddItem() {
  if (!activeListForItems.value || !newItemForm.value.variante_id) return;
  try {
    await asignarPrecioItem(activeListForItems.value.id, {
      variante_id: newItemForm.value.variante_id,
      precio: Number(newItemForm.value.precio),
      fecha_inicio: newItemForm.value.fecha_inicio ? new Date(newItemForm.value.fecha_inicio).toISOString() : undefined,
      fecha_fin: newItemForm.value.fecha_fin ? new Date(newItemForm.value.fecha_fin).toISOString() : undefined
    });
    currentListItems.value = await obtenerItemsListaPrecio(activeListForItems.value.id);
    await loadListas();
  } catch (err: any) {
    alert(err.response?.data?.detail || 'Error al asignar tarifa');
  }
}

async function handleDeleteItem(itemId: string) {
  if (!activeListForItems.value) return;
  try {
    await eliminarPrecioItem(activeListForItems.value.id, itemId);
    currentListItems.value = currentListItems.value.filter(i => i.id !== itemId);
    await loadListas();
  } catch (err) {
    alert('Error al remover tarifa');
  }
}

// Simulador de Motor de Precios
async function ejecutarSimulacion() {
  if (!simProduct.value) return;
  isSimulating.value = true;
  try {
    simResult.value = await resolverPrecioVariante({
      variante_id: simProduct.value,
      canal: simCanal.value,
      tipo_cliente: simTipoCliente.value,
      sucursal_id: simSucursal.value || undefined
    });
  } catch (err: any) {
    alert('Error en motor de precios: ' + (err.response?.data?.detail || err.message));
  } finally {
    isSimulating.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Barra Superior de Control y Moneda Dual -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <DollarSign class="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
          <h2 class="text-xl font-bold text-slate-900 dark:text-white">Listas de Precios Diferenciadas</h2>
        </div>
        <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
          Tarifas parametrizables por canal (Web/POS/B2B), sucursal y tipo de cliente (Retail/B2B).
        </p>
      </div>

      <div class="flex items-center gap-3">
        <!-- Switch de Moneda Dual (BOB / USD) -->
        <div class="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl border border-slate-200 dark:border-slate-700">
          <span class="text-[10px] font-bold text-slate-400 px-2 uppercase">Moneda:</span>
          <button
            type="button"
            @click="displayCurrency = 'BOB'"
            :class="[
              'px-2.5 py-1 rounded-lg text-xs font-bold transition-all',
              displayCurrency === 'BOB' 
                ? 'bg-emerald-600 text-white shadow-sm' 
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900'
            ]"
          >
            BOB (Bs.)
          </button>
          <button
            type="button"
            @click="displayCurrency = 'USD'"
            :class="[
              'px-2.5 py-1 rounded-lg text-xs font-bold transition-all',
              displayCurrency === 'USD' 
                ? 'bg-blue-600 text-white shadow-sm' 
                : 'text-slate-600 dark:text-slate-300 hover:text-slate-900'
            ]"
          >
            USD ($)
          </button>
        </div>

        <button
          type="button"
          @click="openCreateListModal"
          class="inline-flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl text-xs font-bold shadow-md transition-all active:scale-95"
        >
          <Plus class="w-4 h-4" />
          Nueva Lista
        </button>
      </div>
    </div>

    <!-- Feedback Toast -->
    <div v-if="successMsg" class="p-3 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded-xl text-xs font-semibold border border-emerald-200 dark:border-emerald-800 flex items-center gap-2">
      <CheckCircle2 class="w-4 h-4 text-emerald-500" />
      {{ successMsg }}
    </div>

    <!-- Cuadrícula de Listas de Precios Activas -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div 
        v-for="lp in listas" 
        :key="lp.id"
        class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
      >
        <div class="space-y-3">
          <div class="flex items-start justify-between gap-2">
            <span 
              :class="[
                'text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-md tracking-wider',
                lp.canal === 'web' ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800' :
                lp.canal === 'pos' ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800' :
                'bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800'
              ]"
            >
              Canal: {{ lp.canal.toUpperCase() }}
            </span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full" :class="lp.activo ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'">
              {{ lp.activo ? 'Activa' : 'Inactiva' }}
            </span>
          </div>

          <div>
            <h3 class="font-bold text-slate-900 dark:text-white text-base leading-tight">{{ lp.nombre }}</h3>
            <div class="mt-2 space-y-1 text-xs text-slate-500 dark:text-slate-400">
              <p class="flex items-center gap-1.5">
                <Building2 class="w-3.5 h-3.5 text-slate-400" />
                <span class="font-medium">Tipo:</span> {{ lp.tipo_cliente === 'corporativo_b2b' ? 'Corporativo B2B' : 'Minorista / Retail' }}
              </p>
              <p class="flex items-center gap-1.5">
                <Store class="w-3.5 h-3.5 text-slate-400" />
                <span class="font-medium">Sucursal:</span> {{ lp.sucursal_nombre || 'Todas las sucursales' }}
              </p>
              <p class="flex items-center gap-1.5">
                <DollarSign class="w-3.5 h-3.5 text-slate-400" />
                <span class="font-medium">Moneda base:</span> {{ lp.moneda }}
              </p>
            </div>
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
            <strong>{{ lp.total_items || 0 }}</strong> tarifas asignadas
          </span>

          <div class="flex items-center gap-1">
            <button
              type="button"
              @click="openItemsModal(lp)"
              class="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/40 rounded-lg text-xs font-bold"
              title="Gestionar tarifas por SKU"
            >
              Tarifas
            </button>
            <button
              type="button"
              @click="openEditListModal(lp)"
              class="p-1.5 text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg"
              title="Editar lista"
            >
              <Edit3 class="w-4 h-4" />
            </button>
            <button
              type="button"
              @click="handleDeleteList(lp.id)"
              class="p-1.5 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-lg"
              title="Eliminar lista"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Simulador Interactivo de Resolución de Precios (US-04) -->
    <div class="bg-gradient-to-br from-indigo-50/50 via-slate-50 to-blue-50/40 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800/80 p-6 rounded-3xl border border-indigo-100 dark:border-slate-800 shadow-sm space-y-4">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-md">
          <Calculator class="w-4 h-4" />
        </div>
        <div>
          <h3 class="text-base font-bold text-slate-900 dark:text-white">Simulador del Motor de Precios Dinámico</h3>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            Comprueba la jerarquía en tiempo real: <strong>Cliente B2B &gt; Sucursal Específica &gt; Canal General &gt; Base Catálogo</strong>.
          </p>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
        <div>
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">Producto</label>
          <select 
            v-model="simProduct" 
            class="w-full text-xs py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-600"
          >
            <option v-for="p in catalogProducts" :key="p.id" :value="p.id">
              {{ p.sku }} - {{ p.nombre }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">Canal de Venta</label>
          <select 
            v-model="simCanal" 
            class="w-full text-xs py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-600"
          >
            <option value="web">Web (E-commerce)</option>
            <option value="pos">POS (Punto de Venta Físico)</option>
            <option value="b2b">B2B (Portal Mayorista)</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">Tipo de Cliente</label>
          <select 
            v-model="simTipoCliente" 
            class="w-full text-xs py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-600"
          >
            <option value="retail">Retail / Cliente Final</option>
            <option value="corporativo_b2b">Corporativo / Mayorista B2B</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">Sucursal</label>
          <select 
            v-model="simSucursal" 
            class="w-full text-xs py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-600"
          >
            <option v-for="suc in sucursalesDisponibles" :key="suc.id" :value="suc.id">
              {{ suc.nombre }}
            </option>
          </select>
        </div>
      </div>

      <div class="flex items-center justify-between pt-2">
        <button
          type="button"
          @click="ejecutarSimulacion"
          :disabled="isSimulating"
          class="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-md transition-all active:scale-95"
        >
          <Sparkles class="w-4 h-4" />
          {{ isSimulating ? 'Calculando tarifa...' : 'Calcular Tarifa Vigente' }}
        </button>

        <div v-if="simResult" class="flex items-center gap-4 bg-white dark:bg-slate-800 px-4 py-2.5 rounded-2xl border border-indigo-200 dark:border-indigo-900 shadow-sm text-xs">
          <div>
            <span class="text-[10px] text-slate-400 block font-semibold">Lista Ganadora</span>
            <span class="font-extrabold text-indigo-700 dark:text-indigo-300">{{ simResult.lista_nombre }}</span>
          </div>

          <div class="border-l border-slate-200 dark:border-slate-700 pl-4 text-right">
            <span class="text-[10px] text-slate-400 block font-semibold">Precio Final Resuelto</span>
            <span class="text-base font-black text-slate-900 dark:text-white">
              {{ formatCurrency(Number(simResult.precio), simResult.moneda) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal Crear / Editar Lista de Precios -->
    <div v-if="isListModalOpen" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white dark:bg-slate-900 max-w-md w-full rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
          <h3 class="text-base font-bold text-slate-900 dark:text-white">
            {{ isEditingList ? 'Editar Lista de Precios' : 'Nueva Lista de Precios' }}
          </h3>
          <button @click="isListModalOpen = false" class="text-slate-400 hover:text-slate-700 dark:hover:text-white">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="space-y-3 text-xs">
          <div>
            <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Nombre de la Lista *</label>
            <input 
              v-model="listForm.nombre" 
              type="text" 
              placeholder="Ej: Mayoristas Santa Cruz"
              class="w-full py-2 px-3 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl"
            />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Canal *</label>
              <select v-model="listForm.canal" class="w-full py-2 px-3 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl">
                <option value="web">Web</option>
                <option value="pos">POS</option>
                <option value="b2b">B2B</option>
              </select>
            </div>

            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Tipo de Cliente *</label>
              <select v-model="listForm.tipo_cliente" class="w-full py-2 px-3 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl">
                <option value="retail">Retail</option>
                <option value="corporativo_b2b">Corporativo B2B</option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Sucursal Asignada</label>
              <select v-model="listForm.sucursal_id" class="w-full py-2 px-3 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl">
                <option v-for="suc in sucursalesDisponibles" :key="suc.id" :value="suc.id">
                  {{ suc.nombre }}
                </option>
              </select>
            </div>

            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Moneda Base *</label>
              <select v-model="listForm.moneda" class="w-full py-2 px-3 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl">
                <option value="BOB">BOB (Bolivianos)</option>
                <option value="USD">USD (Dólares)</option>
              </select>
            </div>
          </div>

          <div class="flex items-center gap-2 pt-2">
            <input type="checkbox" id="list_activo" v-model="listForm.activo" class="rounded text-blue-600" />
            <label for="list_activo" class="font-semibold text-slate-700 dark:text-slate-300 cursor-pointer">
              Lista de precios activa para transacciones
            </label>
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
          <button @click="isListModalOpen = false" class="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 rounded-xl">
            Cancelar
          </button>
          <button @click="saveListForm" class="px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-xl shadow-md">
            Guardar Lista
          </button>
        </div>
      </div>
    </div>

    <!-- Modal Gestión de Tarifas por Ítem -->
    <div v-if="isItemsModalOpen" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div class="bg-white dark:bg-slate-900 max-w-3xl w-full rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4 max-h-[85vh] flex flex-col">
        <div class="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
          <div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white">
              Tarifas: {{ activeListForItems?.nombre }}
            </h3>
            <p class="text-xs text-slate-400">
              Canal: {{ activeListForItems?.canal.toUpperCase() }} · Moneda: {{ activeListForItems?.moneda }}
            </p>
          </div>
          <button @click="isItemsModalOpen = false" class="text-slate-400 hover:text-slate-700 dark:hover:text-white">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Formulario para agregar/actualizar tarifa de producto -->
        <div class="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-2xl border border-slate-200 dark:border-slate-700 space-y-3">
          <h4 class="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Asignar Tarifa Específica</h4>
          <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
            <div class="sm:col-span-2">
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">Producto</label>
              <select 
                v-model="newItemForm.variante_id" 
                @change="onSelectProductInItemForm"
                class="w-full py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl"
              >
                <option v-for="p in catalogProducts" :key="p.id" :value="p.id">
                  {{ p.sku }} - {{ p.nombre }}
                </option>
              </select>
            </div>

            <div>
              <label class="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Precio ({{ activeListForItems?.moneda }}) *
              </label>
              <input 
                v-model.number="newItemForm.precio" 
                type="number" 
                step="0.01" 
                min="0"
                class="w-full py-2 px-3 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl font-bold"
              />
            </div>

            <div class="flex items-end">
              <button
                type="button"
                @click="handleAddItem"
                class="w-full py-2 px-4 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow transition-all active:scale-95"
              >
                Guardar Tarifa
              </button>
            </div>
          </div>
        </div>

        <!-- Listado de tarifas asignadas -->
        <div class="flex-1 overflow-y-auto space-y-2">
          <div v-if="isLoadingItems" class="text-center py-8 text-xs text-slate-400">
            Cargando tarifas...
          </div>
          <div v-else-if="currentListItems.length === 0" class="text-center py-8 text-xs text-slate-400">
            No hay tarifas individuales configuradas en esta lista. Se aplicará el precio base de catálogo como fallback.
          </div>
          <table v-else class="w-full text-xs text-left">
            <thead class="text-slate-500 border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th class="py-2 px-3 font-semibold">SKU / Producto</th>
                <th class="py-2 px-3 font-semibold text-right">Tarifa Asignada</th>
                <th class="py-2 px-3 font-semibold text-center">Acciones</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="item in currentListItems" :key="item.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <td class="py-2.5 px-3">
                  <span class="font-mono font-bold text-slate-800 dark:text-slate-200 block">{{ item.sku || 'SKU-01' }}</span>
                  <span class="text-slate-500">{{ item.nombre || 'Producto' }}</span>
                </td>
                <td class="py-2.5 px-3 text-right font-extrabold text-slate-900 dark:text-white">
                  {{ activeListForItems?.moneda }} {{ Number(item.precio).toFixed(2) }}
                </td>
                <td class="py-2.5 px-3 text-center">
                  <button 
                    @click="handleDeleteItem(item.id)" 
                    class="p-1.5 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/50 rounded-lg"
                    title="Eliminar tarifa"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
