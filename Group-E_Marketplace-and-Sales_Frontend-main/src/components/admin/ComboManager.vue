<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { 
  Package, 
  Plus, 
  Trash2, 
  Edit3, 
  CheckCircle2, 
  AlertTriangle, 
  Sparkles, 
  RefreshCw, 
  DollarSign, 
  Layers, 
  Search, 
  X, 
  Tag, 
  Info,
  Check,
  PackageCheck,
  AlertCircle
} from 'lucide-vue-next';
import { 
  obtenerCombos, 
  crearCombo, 
  actualizarCombo, 
  eliminarCombo,
} from '@/api/catalogo';
import { apiClient } from '@/api/client';
import type { Combo, ComboItemCreatePayload, Producto, Variante } from '@/types';

// ============================================================================
// ESTADO REACTIVO
// ============================================================================
const combos = ref<Combo[]>([]);
const isLoadingCombos = ref(false);
const searchQuery = ref('');
const filterStatus = ref<'todos' | 'activos' | 'inactivos'>('todos');

// Catálogo de productos disponibles para armar combos
const productosDisponibles = ref<Producto[]>([]);
const isLoadingProductos = ref(false);
const busquedaProductoModal = ref('');

// Modal de Creación / Edición
const isModalOpen = ref(false);
const isEditing = ref(false);
const editingComboId = ref<string | null>(null);
const isSaving = ref(false);
const formError = ref<string | null>(null);

// Formulario reactivo de armado
interface ComboItemForm {
  variante_id: string;
  producto_id?: string;
  sku: string;
  nombre_producto: string;
  nombre_variante: string;
  precio_unitario: number;
  stock_disponible: number;
  cantidad: number;
  imagen_url?: string;
}

const formData = ref<{
  nombre: string;
  sku: string;
  descripcion: string;
  precio_combo: number | '';
  imagen_url: string;
  activo: boolean;
  items: ComboItemForm[];
}>({
  nombre: '',
  sku: '',
  descripcion: '',
  precio_combo: '',
  imagen_url: '',
  activo: true,
  items: [],
});

// Toast de notificación
const toastMessage = ref<{ type: 'success' | 'error'; text: string } | null>(null);

function showToast(text: string, type: 'success' | 'error' = 'success') {
  toastMessage.value = { text, type };
  setTimeout(() => {
    toastMessage.value = null;
  }, 4000);
}

// ============================================================================
// CARGA DE DATOS
// ============================================================================
async function cargarCombos() {
  isLoadingCombos.value = true;
  try {
    const data = await obtenerCombos({ solo_activos: false });
    combos.value = data;
  } catch (error: any) {
    showToast('Error al cargar la lista de combos comerciales', 'error');
  } finally {
    isLoadingCombos.value = false;
  }
}

async function cargarProductosParaArmador() {
  isLoadingProductos.value = true;
  try {
    const { data } = await apiClient.get<Producto[]>('/api/v1/catalogo/productos');
    productosDisponibles.value = data || [];
  } catch (error: any) {
    console.error('Error cargando productos para armado de combos:', error);
  } finally {
    isLoadingProductos.value = false;
  }
}

onMounted(() => {
  cargarCombos();
  cargarProductosParaArmador();
});

// ============================================================================
// COMPUTEDS & MOTOR DE CÁLCULO DE AHORRO EN TIEMPO REAL (LIVE SAVINGS ENGINE)
// ============================================================================
const combosFiltrados = computed(() => {
  return combos.value.filter((c) => {
    const matchText = !searchQuery.value.trim() || 
      c.nombre.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      (c.sku && c.sku.toLowerCase().includes(searchQuery.value.toLowerCase())) ||
      (c.descripcion && c.descripcion.toLowerCase().includes(searchQuery.value.toLowerCase()));

    const matchStatus = 
      filterStatus.value === 'todos' ||
      (filterStatus.value === 'activos' && c.activo) ||
      (filterStatus.value === 'inactivos' && !c.activo);

    return matchText && matchStatus;
  });
});

// Precio regular total acumulado de los ítems en el armado
const precioRegularTotal = computed(() => {
  return formData.value.items.reduce((acc, item) => {
    return acc + Number(item.precio_unitario) * Number(item.cantidad || 1);
  }, 0);
});

// Ahorro económico en Bs.
const ahorroEstimadoBs = computed(() => {
  const pCombo = Number(formData.value.precio_combo) || 0;
  if (!pCombo || precioRegularTotal.value <= 0) return 0;
  return Math.max(0, precioRegularTotal.value - pCombo);
});

// Porcentaje de ahorro promocional (% OFF)
const porcentajeAhorro = computed(() => {
  if (precioRegularTotal.value <= 0 || ahorroEstimadoBs.value <= 0) return 0;
  return Math.round((ahorroEstimadoBs.value / precioRegularTotal.value) * 100);
});

// Stock máximo armable conjunto del combo
const stockMaximoArmable = computed(() => {
  if (!formData.value.items.length) return 0;
  let minPosible = Infinity;
  for (const item of formData.value.items) {
    const cant = Number(item.cantidad) || 1;
    const stock = Number(item.stock_disponible) || 0;
    const armables = Math.floor(stock / cant);
    if (armables < minPosible) {
      minPosible = armables;
    }
  }
  return minPosible === Infinity ? 0 : minPosible;
});

// Lista plana de variantes seleccionables en el buscador del modal
const variantesSeleccionables = computed(() => {
  const q = busquedaProductoModal.value.toLowerCase().trim();
  const list: Array<{
    variante_id: string;
    producto_id: string;
    sku: string;
    nombre_producto: string;
    nombre_variante: string;
    precio: number;
    stock: number;
    imagen_url?: string;
  }> = [];

  for (const prod of productosDisponibles.value) {
    const imgUrl = prod.imagenes_producto?.[0]?.url || (prod as any).imagenes?.[0] || '';
    if (prod.variantes && prod.variantes.length > 0) {
      for (const v of prod.variantes) {
        list.push({
          variante_id: v.id,
          producto_id: prod.id,
          sku: v.sku || prod.sku,
          nombre_producto: prod.nombre,
          nombre_variante: v.nombre_variante || 'Estándar',
          precio: Number(v.precio || prod.precio || 0),
          stock: Number((prod as any).stock || 10),
          imagen_url: imgUrl,
        });
      }
    } else {
      list.push({
        variante_id: prod.id,
        producto_id: prod.id,
        sku: prod.sku,
        nombre_producto: prod.nombre,
        nombre_variante: 'Estándar',
        precio: Number(prod.precio || 0),
        stock: Number((prod as any).stock || 10),
        imagen_url: imgUrl,
      });
    }
  }

  if (!q) return list.slice(0, 8);
  return list.filter(
    (item) =>
      item.nombre_producto.toLowerCase().includes(q) ||
      item.sku.toLowerCase().includes(q) ||
      item.nombre_variante.toLowerCase().includes(q)
  );
});

// ============================================================================
// ACCIONES DE ARMADO Y GESTIÓN
// ============================================================================
function abrirModalCrear() {
  isEditing.value = false;
  editingComboId.value = null;
  formError.value = null;
  busquedaProductoModal.value = '';
  formData.value = {
    nombre: '',
    sku: '',
    descripcion: '',
    precio_combo: '',
    imagen_url: '',
    activo: true,
    items: [],
  };
  isModalOpen.value = true;
}

function abrirModalEditar(combo: Combo) {
  isEditing.value = true;
  editingComboId.value = combo.id;
  formError.value = null;
  busquedaProductoModal.value = '';

  formData.value = {
    nombre: combo.nombre,
    sku: combo.sku || '',
    descripcion: combo.descripcion || '',
    precio_combo: combo.precio_combo,
    imagen_url: combo.imagen_url || '',
    activo: combo.activo,
    items: combo.items.map((it) => ({
      variante_id: it.variante_id,
      producto_id: it.producto_id,
      sku: it.sku || 'SKU',
      nombre_producto: it.nombre_producto || 'Producto',
      nombre_variante: it.nombre_variante || 'Base',
      precio_unitario: Number(it.precio_unitario),
      stock_disponible: Number(it.stock_disponible || 0),
      cantidad: Number(it.cantidad || 1),
      imagen_url: it.imagen_url,
    })),
  };
  isModalOpen.value = true;
}

function agregarVarianteAlCombo(variante: any) {
  const index = formData.value.items.findIndex((it) => it.variante_id === variante.variante_id);
  if (index !== -1) {
    formData.value.items[index].cantidad += 1;
  } else {
    formData.value.items.push({
      variante_id: variante.variante_id,
      producto_id: variante.producto_id,
      sku: variante.sku,
      nombre_producto: variante.nombre_producto,
      nombre_variante: variante.nombre_variante,
      precio_unitario: Number(variante.precio),
      stock_disponible: Number(variante.stock),
      cantidad: 1,
      imagen_url: variante.imagen_url,
    });
  }
}

function removerItemDelCombo(index: number) {
  formData.value.items.splice(index, 1);
}

async function guardarCombo() {
  formError.value = null;
  if (!formData.value.nombre.trim()) {
    formError.value = 'El nombre del combo es obligatorio.';
    return;
  }
  const precioNum = Number(formData.value.precio_combo);
  if (!precioNum || precioNum <= 0) {
    formError.value = 'Debe ingresar un precio de venta para el combo mayor a 0.';
    return;
  }
  if (!formData.value.items.length) {
    formError.value = 'Debe incluir al menos 1 producto o componente en el paquete.';
    return;
  }

  isSaving.value = true;
  try {
    const payloadItems: ComboItemCreatePayload[] = formData.value.items.map((it) => ({
      variante_id: it.variante_id,
      cantidad: Number(it.cantidad) || 1,
    }));

    const payload = {
      nombre: formData.value.nombre.trim(),
      sku: formData.value.sku.trim() || undefined,
      descripcion: formData.value.descripcion.trim() || undefined,
      precio_combo: precioNum,
      imagen_url: formData.value.imagen_url.trim() || undefined,
      activo: formData.value.activo,
      items: payloadItems,
    };

    if (isEditing.value && editingComboId.value) {
      await actualizarCombo(editingComboId.value, payload);
      showToast('Combo comercial actualizado correctamente');
    } else {
      await crearCombo(payload);
      showToast('Nuevo combo comercial creado y publicado exitosamente');
    }

    isModalOpen.value = false;
    await cargarCombos();
  } catch (error: any) {
    formError.value = error.response?.data?.detail || 'Error al guardar el combo.';
  } finally {
    isSaving.value = false;
  }
}

async function toggleEstadoCombo(combo: Combo) {
  try {
    await actualizarCombo(combo.id, { activo: !combo.activo });
    combo.activo = !combo.activo;
    showToast(`Combo "${combo.nombre}" ${combo.activo ? 'activado' : 'desactivado'}`);
  } catch (error) {
    showToast('No se pudo cambiar el estado del combo', 'error');
  }
}

async function confirmarEliminarCombo(combo: Combo) {
  if (!confirm(`¿Está seguro de eliminar el paquete "${combo.nombre}"?`)) return;
  try {
    await eliminarCombo(combo.id);
    showToast(`Combo "${combo.nombre}" eliminado`);
    await cargarCombos();
  } catch (error) {
    showToast('Error al eliminar el combo', 'error');
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Feedback Toast -->
    <div
      v-if="toastMessage"
      class="fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl text-sm font-medium transition-all"
      :class="toastMessage.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'"
    >
      <CheckCircle2 v-if="toastMessage.type === 'success'" class="w-5 h-5 flex-shrink-0" />
      <AlertTriangle v-else class="w-5 h-5 flex-shrink-0" />
      <span>{{ toastMessage.text }}</span>
    </div>

    <!-- Header & Acciones Rápidas -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
      <div>
        <div class="flex items-center gap-2">
          <span class="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
            <Layers class="w-6 h-6" />
          </span>
          <h2 class="text-xl font-bold text-slate-900 dark:text-white">
            Combos y Paquetes Comerciales (US-18 / RF-18)
          </h2>
        </div>
        <p class="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Configura kits y bundles de múltiples productos con precio promocional y cálculo automático de disponibilidad conjunta.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <button
          @click="cargarCombos"
          class="p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          title="Refrescar catálogo"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': isLoadingCombos }" />
        </button>

        <button
          @click="abrirModalCrear"
          class="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-sm shadow-sm transition-all"
        >
          <Plus class="w-4 h-4" />
          Armar Nuevo Combo
        </button>
      </div>
    </div>

    <!-- Barra de Búsqueda y Filtros -->
    <div class="flex flex-col sm:flex-row gap-3 items-center justify-between">
      <div class="relative w-full sm:w-80">
        <Search class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Buscar combo por nombre, SKU..."
          class="w-full pl-10 pr-4 py-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
        />
      </div>

      <div class="flex items-center gap-2 w-full sm:w-auto">
        <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">Estado:</span>
        <div class="inline-flex rounded-xl bg-slate-100 dark:bg-slate-800 p-1 text-xs font-medium">
          <button
            @click="filterStatus = 'todos'"
            class="px-3 py-1.5 rounded-lg transition-all"
            :class="filterStatus === 'todos' ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-xs' : 'text-slate-600 dark:text-slate-400'"
          >
            Todos ({{ combos.length }})
          </button>
          <button
            @click="filterStatus = 'activos'"
            class="px-3 py-1.5 rounded-lg transition-all"
            :class="filterStatus === 'activos' ? 'bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-xs' : 'text-slate-600 dark:text-slate-400'"
          >
            Activos
          </button>
          <button
            @click="filterStatus = 'inactivos'"
            class="px-3 py-1.5 rounded-lg transition-all"
            :class="filterStatus === 'inactivos' ? 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 shadow-xs' : 'text-slate-600 dark:text-slate-400'"
          >
            Inactivos
          </button>
        </div>
      </div>
    </div>

    <!-- Listado de Combos Existentes -->
    <div v-if="isLoadingCombos" class="flex justify-center items-center py-20 text-slate-400">
      <RefreshCw class="w-8 h-8 animate-spin" />
    </div>

    <div v-else-if="combosFiltrados.length === 0" class="text-center py-16 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800">
      <Layers class="w-12 h-12 text-slate-300 dark:text-slate-700 mx-auto mb-3" />
      <h3 class="text-base font-semibold text-slate-800 dark:text-slate-200">No se encontraron combos</h3>
      <p class="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
        Comienza armando un paquete promocional agrupando dos o más artículos a precio especial.
      </p>
      <button
        @click="abrirModalCrear"
        class="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors"
      >
        Crear Primer Combo
      </button>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-5">
      <div
        v-for="combo in combosFiltrados"
        :key="combo.id"
        class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-xs hover:shadow-md transition-shadow flex flex-col justify-between"
      >
        <!-- Cabecera de la Tarjeta -->
        <div class="p-5 border-b border-slate-100 dark:border-slate-800">
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <div class="w-14 h-14 rounded-xl bg-slate-100 dark:bg-slate-800 overflow-hidden flex-shrink-0 border border-slate-200 dark:border-slate-700 flex items-center justify-center">
                <img
                  v-if="combo.imagen_url"
                  :src="combo.imagen_url"
                  :alt="combo.nombre"
                  class="w-full h-full object-cover"
                />
                <Package v-else class="w-6 h-6 text-slate-400" />
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {{ combo.sku || 'SIN-SKU' }}
                  </span>
                  <span
                    class="text-xs font-medium px-2 py-0.5 rounded-full"
                    :class="combo.activo ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500'"
                  >
                    {{ combo.activo ? 'Activo' : 'Inactivo' }}
                  </span>
                </div>
                <h3 class="text-base font-bold text-slate-900 dark:text-white mt-1 line-clamp-1">
                  {{ combo.nombre }}
                </h3>
              </div>
            </div>

            <div class="flex items-center gap-1">
              <button
                @click="abrirModalEditar(combo)"
                class="p-2 text-slate-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg transition-colors"
                title="Editar Combo"
              >
                <Edit3 class="w-4 h-4" />
              </button>
              <button
                @click="confirmarEliminarCombo(combo)"
                class="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 rounded-lg transition-colors"
                title="Eliminar Combo"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <p v-if="combo.descripcion" class="text-xs text-slate-500 dark:text-slate-400 mt-2 line-clamp-2">
            {{ combo.descripcion }}
          </p>
        </div>

        <!-- Métricas Comerciales & Disponibilidad Conjunta -->
        <div class="p-5 space-y-4">
          <!-- Comparativa de Precios y Ahorro -->
          <div class="grid grid-cols-3 gap-3 bg-slate-50 dark:bg-slate-800/60 p-3 rounded-xl text-center">
            <div>
              <span class="text-[11px] text-slate-500 block">Precio Regular</span>
              <span class="text-xs font-semibold text-slate-500 line-through">
                Bs. {{ Number(combo.precio_original).toFixed(2) }}
              </span>
            </div>
            <div>
              <span class="text-[11px] text-indigo-600 dark:text-indigo-400 font-medium block">Precio Combo</span>
              <span class="text-sm font-bold text-indigo-700 dark:text-indigo-300">
                Bs. {{ Number(combo.precio_combo).toFixed(2) }}
              </span>
            </div>
            <div>
              <span class="text-[11px] text-emerald-600 font-medium block">Ahorro Promocional</span>
              <span class="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-950/80 px-2 py-0.5 rounded-full">
                -{{ Number(combo.ahorro_porcentaje) }}% (Bs. {{ Number(combo.ahorro_monto).toFixed(2) }})
              </span>
            </div>
          </div>

          <!-- Disponibilidad Conjunta (Criterio 1 y 3) -->
          <div class="flex items-center justify-between p-3 rounded-xl border text-xs" :class="combo.disponible ? 'bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/40 text-emerald-800 dark:text-emerald-300' : 'bg-amber-50/50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/40 text-amber-800 dark:text-amber-300'">
            <div class="flex items-center gap-2">
              <PackageCheck v-if="combo.disponible" class="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <AlertCircle v-else class="w-4 h-4 text-amber-600 flex-shrink-0" />
              <span>
                <strong class="font-semibold">Disponibilidad Conjunta:</strong>
                {{ combo.disponible ? `${combo.stock_disponible} paquetes armables listos` : 'Agotado' }}
              </span>
            </div>
            <span v-if="combo.item_cuello_botella" class="text-[11px] text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/40 px-2 py-0.5 rounded-md">
              Falta: {{ combo.item_cuello_botella }}
            </span>
          </div>

          <!-- Desglose de Componentes / Existencias Individuales (Criterio 1) -->
          <div>
            <div class="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-between">
              <span>Componentes Incluidos ({{ combo.items.length }})</span>
              <span class="text-[11px] text-slate-400 font-normal">Stock Individual</span>
            </div>

            <div class="space-y-1.5 max-h-40 overflow-y-auto pr-1">
              <div
                v-for="it in combo.items"
                :key="it.variante_id"
                class="flex items-center justify-between text-xs p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <span class="font-bold text-slate-900 dark:text-white px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded text-[11px]">
                    {{ it.cantidad }}x
                  </span>
                  <span class="truncate font-medium text-slate-800 dark:text-slate-200" :title="it.nombre_producto">
                    {{ it.nombre_producto }}
                  </span>
                  <span class="text-[11px] text-slate-400 font-mono">({{ it.sku }})</span>
                </div>

                <div class="flex items-center gap-2 flex-shrink-0">
                  <span class="text-slate-500">
                    Bs. {{ Number(it.precio_unitario).toFixed(2) }}
                  </span>
                  <span
                    class="text-[11px] px-2 py-0.5 rounded-full font-medium"
                    :class="it.stock_disponible >= it.cantidad ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'"
                  >
                    Stock: {{ it.stock_disponible }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pie de Tarjeta / Toggle -->
        <div class="p-4 bg-slate-50 dark:bg-slate-800/40 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <span class="text-xs text-slate-500">
            Publicación: {{ combo.activo ? 'En vitrina' : 'Oculto' }}
          </span>
          <button
            @click="toggleEstadoCombo(combo)"
            class="text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
            :class="combo.activo ? 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-300' : 'bg-indigo-600 text-white hover:bg-indigo-700'"
          >
            {{ combo.activo ? 'Desactivar' : 'Activar' }}
          </button>
        </div>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- MODAL GESTOR DE ARMADO DE COMBOS (US-18 / RF-18)                     -->
    <!-- =================================================================== -->
    <div
      v-if="isModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      @click.self="isModalOpen = false"
    >
      <div class="w-full max-w-4xl bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-6 my-8 max-h-[90vh] overflow-y-auto">
        <!-- Encabezado Modal -->
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-4">
          <div>
            <h3 class="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Sparkles class="w-5 h-5 text-indigo-600" />
              {{ isEditing ? 'Editar Combo Comercial' : 'Gestor de Armado de Combos y Paquetes' }}
            </h3>
            <p class="text-xs text-slate-500 mt-0.5">
              Agrupa artículos, define el precio promocional y evalúa el ahorro y disponibilidad en tiempo real.
            </p>
          </div>
          <button
            @click="isModalOpen = false"
            class="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <div v-if="formError" class="p-3 bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle class="w-4 h-4 flex-shrink-0" />
          <span>{{ formError }}</span>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Columna Izquierda: Datos Generales y Componentes -->
          <div class="lg:col-span-7 space-y-5">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Nombre del Combo *
                </label>
                <input
                  v-model="formData.nombre"
                  type="text"
                  placeholder="Ej: Pack Pro Oficina 2026"
                  class="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Código SKU
                </label>
                <input
                  v-model="formData.sku"
                  type="text"
                  placeholder="Ej: CMB-OFICINA-PRO"
                  class="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                Descripción Comercial
              </label>
              <textarea
                v-model="formData.descripcion"
                rows="2"
                placeholder="Describe la ventaja de adquirir estos productos combinados..."
                class="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              ></textarea>
            </div>

            <div>
              <label class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                URL de Imagen / Banner de Portada
              </label>
              <input
                v-model="formData.imagen_url"
                type="text"
                placeholder="https://..."
                class="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <!-- Selector de Artículos para Incluir en el Combo -->
            <div class="border-t border-slate-100 dark:border-slate-800 pt-4 space-y-3">
              <div class="flex items-center justify-between">
                <label class="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                  Agregar Componentes al Paquete
                </label>
                <span class="text-xs text-slate-400">
                  {{ formData.items.length }} ítems en el combo
                </span>
              </div>

              <div class="relative">
                <Search class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  v-model="busquedaProductoModal"
                  type="text"
                  placeholder="Filtrar productos del catálogo para añadir..."
                  class="w-full pl-9 pr-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <!-- Lista de sugerencias para agregar -->
              <div class="max-h-40 overflow-y-auto space-y-1 bg-slate-50 dark:bg-slate-800/40 p-2 rounded-xl border border-slate-200 dark:border-slate-800">
                <div
                  v-for="item in variantesSeleccionables"
                  :key="item.variante_id"
                  @click="agregarVarianteAlCombo(item)"
                  class="flex items-center justify-between p-2 rounded-lg bg-white dark:bg-slate-800 hover:bg-indigo-50 dark:hover:bg-indigo-950/60 cursor-pointer border border-slate-100 dark:border-slate-700 text-xs transition-colors"
                >
                  <div class="flex items-center gap-2 truncate">
                    <span class="font-medium text-slate-800 dark:text-slate-200 truncate">
                      {{ item.nombre_producto }}
                    </span>
                    <span class="text-[10px] text-slate-400 font-mono">({{ item.sku }})</span>
                  </div>
                  <div class="flex items-center gap-3 flex-shrink-0">
                    <span class="text-slate-600 dark:text-slate-300 font-semibold">
                      Bs. {{ item.precio.toFixed(2) }}
                    </span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500">
                      Stock: {{ item.stock }}
                    </span>
                    <button class="p-1 rounded bg-indigo-600 text-white">
                      <Plus class="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Ítems actualmente agregados al combo -->
            <div class="space-y-2">
              <label class="text-xs font-semibold text-slate-700 dark:text-slate-300 block">
                Productos Seleccionados para el Combo:
              </label>

              <div v-if="!formData.items.length" class="text-center py-6 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl text-slate-400 text-xs">
                Haz clic en el botón '+' de la lista superior para agregar productos al combo.
              </div>

              <div
                v-for="(item, idx) in formData.items"
                :key="item.variante_id"
                class="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs"
              >
                <div class="min-w-0 pr-2">
                  <div class="font-medium text-slate-900 dark:text-white truncate">
                    {{ item.nombre_producto }}
                  </div>
                  <div class="text-[11px] text-slate-400">
                    Precio unitario: Bs. {{ item.precio_unitario.toFixed(2) }} | Stock individual: {{ item.stock_disponible }}
                  </div>
                </div>

                <div class="flex items-center gap-3 flex-shrink-0">
                  <div class="flex items-center gap-1.5">
                    <span class="text-[11px] text-slate-500">Cant:</span>
                    <input
                      v-model.number="item.cantidad"
                      type="number"
                      min="1"
                      class="w-14 px-2 py-1 text-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-semibold"
                    />
                  </div>
                  <span class="font-bold text-slate-800 dark:text-slate-200">
                    Bs. {{ (item.precio_unitario * (item.cantidad || 1)).toFixed(2) }}
                  </span>
                  <button
                    @click="removerItemDelCombo(idx)"
                    class="p-1.5 text-slate-400 hover:text-red-600 rounded-lg"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Columna Derecha: Motor de Cálculo y Resumen Comercial -->
          <div class="lg:col-span-5 bg-slate-50 dark:bg-slate-800/40 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 flex flex-col justify-between space-y-5">
            <div class="space-y-4">
              <h4 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <DollarSign class="w-4 h-4 text-emerald-600" />
                Motor de Precios y Ahorro
              </h4>

              <!-- Precio Promocional del Combo -->
              <div>
                <label class="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Precio Promocional del Combo (Bs.) *
                </label>
                <div class="relative">
                  <span class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm font-bold">Bs.</span>
                  <input
                    v-model.number="formData.precio_combo"
                    type="number"
                    step="0.50"
                    placeholder="0.00"
                    class="w-full pl-11 pr-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-base font-bold text-indigo-600 dark:text-indigo-400 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <!-- Tarjetas de métricas calculadas en vivo -->
              <div class="space-y-3 pt-2">
                <!-- Regular vs Combo -->
                <div class="p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-xs space-y-1.5">
                  <div class="flex justify-between text-slate-500">
                    <span>Precio Regular Sumado:</span>
                    <span class="font-semibold text-slate-700 dark:text-slate-300">
                      Bs. {{ precioRegularTotal.toFixed(2) }}
                    </span>
                  </div>
                  <div class="flex justify-between text-slate-900 dark:text-white font-bold border-t border-slate-100 dark:border-slate-800 pt-1.5">
                    <span>Precio Oferta Combo:</span>
                    <span class="text-indigo-600 dark:text-indigo-400">
                      Bs. {{ Number(formData.precio_combo || 0).toFixed(2) }}
                    </span>
                  </div>
                </div>

                <!-- Ahorro Proyectado -->
                <div class="p-4 bg-emerald-50 dark:bg-emerald-950/40 rounded-xl border border-emerald-200 dark:border-emerald-900/60 text-center">
                  <span class="text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider block">
                    Ahorro para el Cliente
                  </span>
                  <div class="text-2xl font-black text-emerald-600 dark:text-emerald-300 mt-1">
                    {{ porcentajeAhorro }}% OFF
                  </div>
                  <div class="text-xs font-semibold text-emerald-800 dark:text-emerald-400 mt-0.5">
                    (Ahorra Bs. {{ ahorroEstimadoBs.toFixed(2) }})
                  </div>
                </div>

                <!-- Alerta de Precio sin Descuento -->
                <div
                  v-if="formData.precio_combo && Number(formData.precio_combo) >= precioRegularTotal && precioRegularTotal > 0"
                  class="p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 rounded-xl text-xs flex items-center gap-2"
                >
                  <AlertTriangle class="w-4 h-4 flex-shrink-0 text-amber-600" />
                  <span>Aviso: El precio del combo es mayor o igual al regular, no representa un ahorro comercial.</span>
                </div>

                <!-- Proyección de Stock Conjunto -->
                <div class="p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 text-xs">
                  <span class="text-[11px] text-slate-400 block mb-1">Disponibilidad Conjunta Proyectada:</span>
                  <div class="flex items-center justify-between">
                    <span class="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                      <PackageCheck class="w-4 h-4 text-indigo-600" />
                      {{ stockMaximoArmable }} combos armables
                    </span>
                    <span
                      class="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      :class="stockMaximoArmable > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'"
                    >
                      {{ stockMaximoArmable > 0 ? 'Con stock' : 'Sin stock' }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Botones de Guardar / Cancelar -->
            <div class="space-y-2 pt-4 border-t border-slate-200 dark:border-slate-700">
              <button
                @click="guardarCombo"
                :disabled="isSaving"
                class="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm shadow-sm transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <Sparkles v-if="!isSaving" class="w-4 h-4" />
                <RefreshCw v-else class="w-4 h-4 animate-spin" />
                {{ isSaving ? 'Guardando Paquete...' : (isEditing ? 'Actualizar Combo' : 'Crear y Publicar Combo') }}
              </button>

              <button
                @click="isModalOpen = false"
                class="w-full py-2 bg-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 text-xs font-semibold rounded-xl"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
