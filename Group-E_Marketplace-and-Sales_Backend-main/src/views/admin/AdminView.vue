<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { apiClient } from '@/api/client';
import type { Producto, Categoria } from '@/types';
import ProductMultimediaManager from '@/components/ProductMultimediaManager.vue';
import { 
  TrendingUp, 
  ShoppingBag, 
  DollarSign, 
  Users, 
  Package, 
  FileText, 
  AlertTriangle,
  ArrowUpRight,
  Image as ImageIcon,
  Plus,
  Search,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Edit2,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Filter,
  Check,
  Archive,
  Eye,
  RefreshCw,
  Tag
} from 'lucide-vue-next';

// Pestaña activa: 'productos' | 'multimedia' | 'dashboard'
const activeTab = ref<'productos' | 'multimedia' | 'dashboard'>('productos');

// Estado de productos y categorías desde Supabase
const productos = ref<Producto[]>([]);
const categorias = ref<Categoria[]>([]);
const isLoadingCatalog = ref(false);
const catalogSearch = ref('');
const selectedCategoriaFilter = ref('Todas');
const selectedEstadoFilter = ref('Todos');

// Paginación (KAN-291)
const currentPage = ref(1);
const itemsPerPage = ref(6);

// Producto seleccionado para gestionar su galería
const selectedProduct = ref<Producto | null>(null);

// Modal para Crear / Editar Producto (KAN-307)
const showProductModal = ref(false);
const isEditing = ref(false);
const editingProductId = ref<string | null>(null);
const isSavingProduct = ref(false);
const productModalError = ref<string | null>(null);
const toastSuccess = ref<string | null>(null);

// Formulario reactivo con validaciones y precios (KAN-307)
const productForm = ref({
  sku: '',
  nombre: '',
  marca: '',
  categoria_id: '',
  precio: 0,
  precio_costo: 0,
  descripcion: '',
  estado: 'publicado'
});

const formErrors = ref({
  sku: '',
  nombre: '',
  precio: ''
});

// KPIs simulados para el dashboard
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

function showToast(msg: string) {
  toastSuccess.value = msg;
  setTimeout(() => {
    toastSuccess.value = null;
  }, 4000);
}

// Cargar catálogo de Supabase
async function fetchCatalog() {
  isLoadingCatalog.value = true;
  try {
    const [pRes, cRes] = await Promise.all([
      apiClient.get('/productos'),
      apiClient.get('/categorias')
    ]);
    productos.value = pRes.data.productos || [];
    categorias.value = cRes.data.categorias || [];

    // Si había un producto seleccionado en galería, actualizarlo
    if (selectedProduct.value) {
      const refreshed = productos.value.find(p => p.id === selectedProduct.value?.id);
      if (refreshed) {
        selectedProduct.value = refreshed;
      }
    }
  } catch (err) {
    console.error('Error cargando catálogo desde Supabase:', err);
  } finally {
    isLoadingCatalog.value = false;
  }
}

onMounted(() => {
  fetchCatalog();
});

// Filtrado de productos (búsqueda + categoría + estado de ciclo de vida)
const filteredProductos = computed(() => {
  return productos.value.filter(p => {
    const matchesSearch = p.nombre.toLowerCase().includes(catalogSearch.value.toLowerCase()) ||
                          p.sku.toLowerCase().includes(catalogSearch.value.toLowerCase()) ||
                          (p.marca && p.marca.toLowerCase().includes(catalogSearch.value.toLowerCase()));
    
    const matchesCategory = selectedCategoriaFilter.value === 'Todas' ||
                            p.categorias?.nombre === selectedCategoriaFilter.value;

    const matchesEstado = selectedEstadoFilter.value === 'Todos' ||
                          (p.estado || '').toLowerCase() === selectedEstadoFilter.value.toLowerCase();

    return matchesSearch && matchesCategory && matchesEstado;
  });
});

// Reseteo de página al cambiar filtros
watch([catalogSearch, selectedCategoriaFilter, selectedEstadoFilter], () => {
  currentPage.value = 1;
});

// Paginación computada (KAN-291)
const totalPages = computed(() => {
  return Math.ceil(filteredProductos.value.length / itemsPerPage.value) || 1;
});

const paginatedProductos = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value;
  return filteredProductos.value.slice(start, start + itemsPerPage.value);
});

// Abrir gestor multimedia de un producto (KAN-19 / RF-03)
function openMultimediaManager(prod: Producto) {
  selectedProduct.value = prod;
  activeTab.value = 'multimedia';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Obtener la imagen principal de un producto
function getCoverUrl(prod: Producto): string | null {
  if (!prod.imagenes_producto || prod.imagenes_producto.length === 0) return null;
  const principal = prod.imagenes_producto.find(i => i.es_principal);
  return principal ? principal.url : prod.imagenes_producto[0].url;
}

// Abrir modal para Crear Producto (KAN-307)
function openCreateModal() {
  isEditing.value = false;
  editingProductId.value = null;
  productForm.value = {
    sku: '',
    nombre: '',
    marca: '',
    categoria_id: categorias.value[0]?.id || '',
    precio: 0,
    precio_costo: 0,
    descripcion: '',
    estado: 'publicado'
  };
  formErrors.value = { sku: '', nombre: '', precio: '' };
  productModalError.value = null;
  showProductModal.value = true;
}

// Abrir modal para Editar Producto (KAN-307)
function openEditModal(prod: Producto) {
  isEditing.value = true;
  editingProductId.value = prod.id;
  productForm.value = {
    sku: prod.sku,
    nombre: prod.nombre,
    marca: prod.marca || '',
    categoria_id: prod.categoria_id || '',
    precio: prod.precio || 0,
    precio_costo: (prod as any).precio_costo || Math.round((prod.precio || 0) * 0.7),
    descripcion: prod.descripcion || '',
    estado: prod.estado || 'publicado'
  };
  formErrors.value = { sku: '', nombre: '', precio: '' };
  productModalError.value = null;
  showProductModal.value = true;
}

// Validaciones reactivas en tiempo real
function validateForm(): boolean {
  let isValid = true;
  formErrors.value = { sku: '', nombre: '', precio: '' };

  const skuClean = productForm.value.sku.trim().toUpperCase();
  if (!skuClean) {
    formErrors.value.sku = 'El código SKU es obligatorio.';
    isValid = false;
  } else if (skuClean.length < 3) {
    formErrors.value.sku = 'El SKU debe tener al menos 3 caracteres.';
    isValid = false;
  } else if (!/^[A-Z0-9\-_]+$/.test(skuClean)) {
    formErrors.value.sku = 'Solo se permiten letras, números, guiones (-) y guiones bajos (_).';
    isValid = false;
  }

  if (!productForm.value.nombre.trim()) {
    formErrors.value.nombre = 'El nombre comercial del producto es obligatorio.';
    isValid = false;
  } else if (productForm.value.nombre.trim().length < 3) {
    formErrors.value.nombre = 'El nombre debe tener mínimo 3 caracteres.';
    isValid = false;
  }

  if (productForm.value.precio < 0) {
    formErrors.value.precio = 'El precio de venta no puede ser negativo.';
    isValid = false;
  }

  return isValid;
}

// Guardar Producto (Crear o Editar con persistencia de Precio en Supabase)
async function handleSaveProduct() {
  if (!validateForm()) return;

  isSavingProduct.value = true;
  productModalError.value = null;

  try {
    const payload = {
      ...productForm.value,
      sku: productForm.value.sku.trim().toUpperCase(),
      nombre: productForm.value.nombre.trim(),
      precio: Number(productForm.value.precio) || 0,
      precio_costo: Number(productForm.value.precio_costo) || 0
    };

    if (isEditing.value && editingProductId.value) {
      // Actualizar producto existente
      await apiClient.put(`/productos/${editingProductId.value}`, payload);
      showToast(`Producto ${payload.sku} actualizado con éxito.`);
    } else {
      // Crear nuevo producto
      const res = await apiClient.post('/productos', payload);
      showToast(`Producto ${payload.sku} registrado exitosamente con precio BOB ${payload.precio}.`);
      if (res.data.producto) {
        showProductModal.value = false;
        await fetchCatalog();
        openMultimediaManager(res.data.producto);
        return;
      }
    }

    await fetchCatalog();
    showProductModal.value = false;
  } catch (err: any) {
    console.error('Error guardando producto:', err);
    productModalError.value = err.response?.data?.error || 'Ocurrió un error al procesar la solicitud.';
  } finally {
    isSavingProduct.value = false;
  }
}

// Cambio rápido de estado de ciclo de vida (KAN-291)
async function handleQuickStatusChange(prod: Producto, nuevoEstado: string) {
  try {
    await apiClient.patch(`/productos/${prod.id}/estado`, { estado: nuevoEstado });
    prod.estado = nuevoEstado;
    showToast(`Estado de ${prod.sku} actualizado a "${nuevoEstado}".`);
  } catch (err: any) {
    alert(err.response?.data?.error || 'No se pudo actualizar el estado.');
  }
}

// Eliminar producto (KAN-291)
async function handleDeleteProduct(prod: Producto) {
  const confirmed = confirm(`¿Estás seguro de eliminar el producto "${prod.nombre}" (${prod.sku})? Se eliminarán también sus imágenes asociadas.`);
  if (!confirmed) return;

  try {
    await apiClient.delete(`/productos/${prod.id}`);
    showToast(`Producto ${prod.sku} eliminado del catálogo.`);
    await fetchCatalog();
    if (selectedProduct.value?.id === prod.id) {
      selectedProduct.value = null;
    }
  } catch (err: any) {
    alert(err.response?.data?.error || 'Error al eliminar el producto.');
  }
}
</script>

<template>
  <div class="space-y-8">
    <!-- Toast de Notificación Flotante -->
    <transition
      enter-active-class="transform ease-out duration-300 transition"
      enter-from-class="translate-y-2 opacity-0 sm:translate-y-0 sm:translate-x-2"
      enter-to-class="translate-y-0 opacity-100 sm:translate-x-0"
      leave-active-class="transition ease-in duration-100"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div 
        v-if="toastSuccess" 
        class="fixed bottom-5 right-5 z-50 flex items-center gap-3 bg-emerald-600 text-white px-4 py-3 rounded-2xl shadow-xl border border-emerald-500 text-xs font-semibold"
      >
        <CheckCircle2 class="w-4 h-4 text-emerald-200" />
        <span>{{ toastSuccess }}</span>
      </div>
    </transition>

    <!-- Header Panel Administrativo -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
      <div>
        <h1 class="text-2xl font-extrabold text-slate-900 dark:text-white flex items-center gap-3">
          Gestión de Catálogo y Ciclo de Vida
          <span class="text-xs px-2.5 py-1 rounded-full font-bold bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-900/50">
            RF-01 / RF-03
          </span>
        </h1>
        <p class="text-xs text-slate-500 mt-1">Supervisión integral de catálogo, precios en variantes, ciclo de vida y galería multimedia en Supabase.</p>
      </div>

      <!-- Navegación de Pestañas y Acciones Principales -->
      <div class="flex flex-wrap items-center gap-2">
        <div class="bg-slate-100 dark:bg-slate-800 p-1 rounded-xl flex items-center border border-slate-200 dark:border-slate-700">
          <!-- Pestaña 1: Productos (RF-01 / KAN-291) -->
          <button
            id="tab-btn-productos"
            @click="activeTab = 'productos'"
            :class="[
              'px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5',
              activeTab === 'productos'
                ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            ]"
          >
            <Package class="w-3.5 h-3.5" />
            <span>Productos y Precios (RF-01)</span>
            <span class="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-300 font-bold">
              {{ productos.length }}
            </span>
          </button>

          <!-- Pestaña 2: Multimedia (RF-03 / KAN-19) -->
          <button
            id="tab-btn-multimedia"
            @click="activeTab = 'multimedia'"
            :class="[
              'px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5',
              activeTab === 'multimedia'
                ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            ]"
          >
            <ImageIcon class="w-3.5 h-3.5" />
            <span>Galería y Fotos (RF-03)</span>
          </button>

          <!-- Pestaña 3: Dashboard y KPIs -->
          <button
            id="tab-btn-dashboard"
            @click="activeTab = 'dashboard'"
            :class="[
              'px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-1.5',
              activeTab === 'dashboard'
                ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            ]"
          >
            <TrendingUp class="w-3.5 h-3.5" />
            <span>Métricas</span>
          </button>
        </div>

        <!-- Botón Nuevo Producto (KAN-307) -->
        <button
          id="btn-add-new-product"
          @click="openCreateModal"
          class="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm flex items-center gap-1.5 transition-colors"
        >
          <Plus class="w-4 h-4" />
          <span>+ Nuevo Producto</span>
        </button>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- SECCIÓN 1: TABLA DE GESTIÓN DE PRODUCTOS CON PRECIOS Y PAGINACIÓN     -->
    <!-- ===================================================================== -->
    <div v-if="activeTab === 'productos'" class="space-y-6">
      <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <!-- Barra de Búsqueda y Filtros -->
        <div class="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row justify-between items-center gap-4 bg-slate-50/50 dark:bg-slate-950/40">
          <div class="flex items-center gap-2">
            <h2 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Package class="w-4 h-4 text-blue-600" />
              Catálogo de Productos en Supabase
            </h2>
            <span class="text-xs text-slate-400">Total: {{ filteredProductos.length }} registros filtrados</span>
          </div>

          <div class="flex flex-wrap items-center gap-3 w-full md:w-auto">
            <!-- Filtro de Estado (KAN-291) -->
            <select
              v-model="selectedEstadoFilter"
              class="text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-1.5 text-slate-700 dark:text-slate-300 focus:ring-2 focus:ring-blue-500 font-medium"
            >
              <option value="Todos">Todos los estados</option>
              <option value="publicado">Publicado</option>
              <option value="borrador">Borrador</option>
              <option value="descontinuado">Descontinuado</option>
              <option value="inactivo">Inactivo</option>
            </select>

            <!-- Filtro de Categoría -->
            <select
              v-model="selectedCategoriaFilter"
              class="text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-1.5 text-slate-700 dark:text-slate-300 focus:ring-2 focus:ring-blue-500 font-medium"
            >
              <option value="Todas">Todas las categorías</option>
              <option v-for="cat in categorias" :key="cat.id" :value="cat.nombre">{{ cat.nombre }}</option>
            </select>

            <!-- Input de búsqueda reactivo -->
            <div class="relative flex-1 sm:w-60">
              <Search class="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                v-model="catalogSearch"
                type="text"
                placeholder="Buscar SKU, nombre o marca..."
                class="w-full text-xs pl-8 pr-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <!-- Botón de recarga -->
            <button
              @click="fetchCatalog"
              title="Refrescar catálogo"
              class="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300"
            >
              <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoadingCatalog }" />
            </button>
          </div>
        </div>

        <!-- Indicador de carga -->
        <div v-if="isLoadingCatalog" class="py-16 text-center text-slate-400 space-y-2">
          <Loader2 class="w-7 h-7 animate-spin mx-auto text-blue-600" />
          <p class="text-xs">Sincronizando productos desde Supabase Postgres...</p>
        </div>

        <!-- Sin resultados -->
        <div v-else-if="filteredProductos.length === 0" class="py-14 text-center text-slate-400 space-y-3">
          <Package class="w-10 h-10 text-slate-300 mx-auto" />
          <p class="text-sm font-semibold">No se encontraron productos con los filtros seleccionados</p>
          <p class="text-xs">Intenta ajustar tu búsqueda o registra un producto nuevo.</p>
          <button 
            @click="openCreateModal"
            class="px-4 py-2 bg-blue-600 text-white rounded-xl text-xs font-bold inline-flex items-center gap-2"
          >
            <Plus class="w-4 h-4" /> Registrar Producto
          </button>
        </div>

        <!-- Tabla Paginada de Productos (KAN-291) -->
        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50/80 dark:bg-slate-800/80 text-slate-500 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th class="p-3.5 pl-5">Miniatura</th>
                <th class="p-3.5">SKU (Único)</th>
                <th class="p-3.5">Nombre y Marca</th>
                <th class="p-3.5">Categoría</th>
                <th class="p-3.5">Precio Venta</th>
                <th class="p-3.5">Ciclo de Vida</th>
                <th class="p-3.5">Galería</th>
                <th class="p-3.5 pr-5 text-right">Acciones Rápidas</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr 
                v-for="prod in paginatedProductos" 
                :key="prod.id"
                class="hover:bg-slate-50/80 dark:hover:bg-slate-800/50 transition-colors"
              >
                <!-- Miniatura -->
                <td class="p-3.5 pl-5">
                  <div class="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center shrink-0">
                    <img 
                      v-if="getCoverUrl(prod)" 
                      :src="getCoverUrl(prod)!" 
                      :alt="prod.nombre"
                      class="w-full h-full object-cover"
                    />
                    <ImageIcon v-else class="w-4 h-4 text-slate-300 dark:text-slate-600" />
                  </div>
                </td>

                <!-- SKU -->
                <td class="p-3.5">
                  <span class="font-mono font-bold text-slate-900 dark:text-white bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-md text-[11px] border border-slate-200 dark:border-slate-700">
                    {{ prod.sku }}
                  </span>
                </td>

                <!-- Nombre y Marca -->
                <td class="p-3.5">
                  <div class="font-semibold text-slate-900 dark:text-white text-xs">{{ prod.nombre }}</div>
                  <div class="text-[11px] text-slate-400">{{ prod.marca || 'Sin marca' }}</div>
                </td>

                <!-- Categoría -->
                <td class="p-3.5">
                  <span class="px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                    {{ prod.categorias?.nombre || 'General' }}
                  </span>
                </td>

                <!-- Precio Venta (BOB) -->
                <td class="p-3.5">
                  <div class="font-bold text-slate-900 dark:text-white text-xs">
                    BOB {{ (prod.precio || 0).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
                  </div>
                  <div class="text-[10px] text-slate-400">Variante Estándar</div>
                </td>

                <!-- Selector rápido de Estado de Ciclo de Vida (KAN-291) -->
                <td class="p-3.5">
                  <select
                    :value="prod.estado === 'archivado' ? 'descontinuado' : (prod.estado || 'publicado')"
                    @change="handleQuickStatusChange(prod, ($event.target as HTMLSelectElement).value)"
                    :class="[
                      'text-[11px] font-bold rounded-lg px-2.5 py-1 border transition-colors cursor-pointer',
                      prod.estado === 'publicado' 
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800'
                        : prod.estado === 'borrador'
                          ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800'
                          : 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
                    ]"
                  >
                    <option value="publicado">● Publicado</option>
                    <option value="borrador">● Borrador</option>
                    <option value="descontinuado">● Descontinuado</option>
                    <option value="inactivo">● Inactivo</option>
                  </select>
                </td>

                <!-- Multimedia badge -->
                <td class="p-3.5">
                  <button 
                    @click="openMultimediaManager(prod)"
                    class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 hover:bg-blue-100 transition-colors"
                  >
                    <ImageIcon class="w-3.5 h-3.5" />
                    <span>{{ prod.imagenes_producto?.length || 0 }} fotos</span>
                  </button>
                </td>

                <!-- Acciones Rápidas (Editar, Gestionar Galería, Eliminar) -->
                <td class="p-3.5 pr-5 text-right">
                  <div class="flex items-center justify-end gap-1.5">
                    <!-- Editar -->
                    <button
                      @click="openEditModal(prod)"
                      title="Editar información del producto (KAN-307)"
                      class="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors"
                    >
                      <Edit2 class="w-3.5 h-3.5" />
                    </button>

                    <!-- Administrar Galería -->
                    <button
                      @click="openMultimediaManager(prod)"
                      title="Administrar galería multimedia (KAN-19)"
                      class="p-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-600 hover:text-white transition-colors"
                    >
                      <ImageIcon class="w-3.5 h-3.5" />
                    </button>

                    <!-- Eliminar -->
                    <button
                      @click="handleDeleteProduct(prod)"
                      title="Eliminar producto"
                      class="p-1.5 rounded-lg border border-rose-200 dark:border-rose-900/50 hover:bg-rose-50 text-rose-600 dark:hover:bg-rose-950/30 transition-colors"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Paginación Footer (KAN-291) -->
          <div class="p-4 border-t border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-50/40 dark:bg-slate-950/20 text-xs text-slate-500">
            <div>
              Mostrando página <strong class="text-slate-800 dark:text-slate-200">{{ currentPage }}</strong> de <strong class="text-slate-800 dark:text-slate-200">{{ totalPages }}</strong> 
              ({{ filteredProductos.length }} productos en total)
            </div>

            <div class="flex items-center gap-2">
              <button
                @click="currentPage--"
                :disabled="currentPage === 1"
                class="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 font-semibold flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white dark:hover:bg-slate-800 transition-colors"
              >
                <ChevronLeft class="w-3.5 h-3.5" /> Anterior
              </button>

              <div class="flex items-center gap-1">
                <button
                  v-for="p in totalPages"
                  :key="p"
                  @click="currentPage = p"
                  :class="[
                    'w-7 h-7 rounded-lg text-xs font-bold transition-all',
                    currentPage === p 
                      ? 'bg-blue-600 text-white shadow-sm' 
                      : 'hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                  ]"
                >
                  {{ p }}
                </button>
              </div>

              <button
                @click="currentPage++"
                :disabled="currentPage === totalPages"
                class="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 font-semibold flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white dark:hover:bg-slate-800 transition-colors"
              >
                Siguiente <ChevronRight class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- SECCIÓN 2: GESTOR DE RECURSOS MULTIMEDIA (HISTORIA RF-03 / KAN-19)     -->
    <!-- ===================================================================== -->
    <div v-if="activeTab === 'multimedia'" class="space-y-6">
      <div v-if="selectedProduct" class="space-y-4">
        <ProductMultimediaManager
          :producto="selectedProduct"
          @close="selectedProduct = null"
          @updated="fetchCatalog"
        />
      </div>

      <!-- Selector de producto para galería si ninguno está abierto -->
      <div v-else class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-8 text-center space-y-4 shadow-sm">
        <div class="w-14 h-14 bg-blue-50 dark:bg-blue-950/50 rounded-2xl flex items-center justify-center mx-auto text-blue-600 border border-blue-200 dark:border-blue-900">
          <ImageIcon class="w-7 h-7" />
        </div>
        <div>
          <h3 class="text-base font-bold text-slate-900 dark:text-white">Selecciona un producto para gestionar sus fotos</h3>
          <p class="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Ve a la pestaña de "Productos y Precios" o elige uno a continuación para cargar imágenes en Supabase Storage, optimizarlas con Sharp y definir la portada.
          </p>
        </div>
        <div class="flex flex-wrap justify-center gap-2 max-w-2xl mx-auto pt-2">
          <button
            v-for="p in productos"
            :key="p.id"
            @click="openMultimediaManager(p)"
            class="px-3.5 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-blue-50 dark:hover:bg-blue-950/40 text-slate-800 dark:text-slate-200 rounded-xl text-xs font-semibold border border-slate-200 dark:border-slate-700 transition-all flex items-center gap-2"
          >
            <span class="font-mono text-blue-600 font-bold">{{ p.sku }}</span>
            <span>{{ p.nombre }}</span>
            <span class="text-slate-400 font-bold">BOB {{ p.precio || 0 }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- SECCIÓN 3: DASHBOARD GENERAL Y KPIS                                   -->
    <!-- ===================================================================== -->
    <div v-if="activeTab === 'dashboard'" class="space-y-8">
      <!-- Cards de KPIs Clave (RF-46) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div class="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Ventas Totales Hoy</span>
            <span class="p-2 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 rounded-lg"><DollarSign class="w-4 h-4" /></span>
          </div>
          <div class="text-2xl font-bold text-slate-900 dark:text-white">BOB {{ kpis.ventasHoy.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}</div>
          <span class="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
            <ArrowUpRight class="w-3.5 h-3.5" /> +14.2% vs ayer
          </span>
        </div>

        <div class="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Ventas del Mes</span>
            <span class="p-2 bg-blue-50 dark:bg-blue-950/40 text-blue-600 rounded-lg"><TrendingUp class="w-4 h-4" /></span>
          </div>
          <div class="text-2xl font-bold text-slate-900 dark:text-white">BOB {{ kpis.ventasMes.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}</div>
          <span class="text-[11px] text-blue-600 font-semibold flex items-center gap-1">
            <ArrowUpRight class="w-3.5 h-3.5" /> Meta mensual: 87%
          </span>
        </div>

        <div class="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Órdenes Procesadas Hoy</span>
            <span class="p-2 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 rounded-lg"><ShoppingBag class="w-4 h-4" /></span>
          </div>
          <div class="text-2xl font-bold text-slate-900 dark:text-white">{{ kpis.ordenesHoy }}</div>
          <span class="text-[11px] text-slate-400">Canal Web (22) / POS (12)</span>
        </div>

        <div class="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
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
        <div class="lg:col-span-2 bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div class="flex justify-between items-center">
            <h3 class="text-sm font-bold text-slate-800 dark:text-white flex items-center gap-2">
              <FileText class="w-4 h-4 text-blue-500" /> Órdenes y Ventas Recientes
            </h3>
            <button @click="activeTab = 'productos'" class="text-xs text-blue-600 hover:underline font-semibold">Ver Catálogo</button>
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
        <div class="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div class="flex items-center gap-2 text-rose-600 font-bold text-sm">
            <AlertTriangle class="w-4 h-4" />
            <span>Alertas de Quiebre de Stock (RF-42)</span>
          </div>
          <p class="text-xs text-slate-400">Productos que alcanzaron el punto de reorden para Compras:</p>

          <div class="space-y-3">
            <div
              v-for="alert in lowStockAlerts"
              :key="alert.sku"
              class="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-xl space-y-1"
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
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- MODAL: FORMULARIO REACTIVO DE ADMINISTRACIÓN DE PRODUCTO (KAN-307)     -->
    <!-- ===================================================================== -->
    <div
      v-if="showProductModal"
      class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
    >
      <div class="bg-white dark:bg-slate-900 rounded-3xl max-w-lg w-full p-6 border border-slate-200 dark:border-slate-800 shadow-2xl space-y-5 my-8">
        <!-- Header Modal -->
        <div class="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-3">
          <div class="flex items-center gap-2 text-slate-900 dark:text-white font-bold text-base">
            <Package class="w-5 h-5 text-blue-600" />
            <span>{{ isEditing ? 'Editar Producto y Precio' : 'Crear Nuevo Producto en Catálogo' }}</span>
          </div>
          <button @click="showProductModal = false" class="text-slate-400 hover:text-slate-600">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Banner de Error Backend -->
        <div v-if="productModalError" class="p-3 bg-rose-50 text-rose-700 text-xs rounded-xl border border-rose-200 flex items-center gap-2">
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ productModalError }}</span>
        </div>

        <form @submit.prevent="handleSaveProduct" class="space-y-4 text-xs">
          <!-- SKU y Marca -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                SKU Único * 
                <span class="text-[10px] text-slate-400 font-normal">(Mayúsculas)</span>
              </label>
              <input
                v-model="productForm.sku"
                type="text"
                placeholder="Ej: TEC-KEY-LOGI"
                :class="[
                  'w-full p-2.5 font-mono uppercase bg-slate-50 dark:bg-slate-800 border rounded-xl focus:ring-2 focus:ring-blue-500',
                  formErrors.sku ? 'border-rose-400 ring-1 ring-rose-400' : 'border-slate-200 dark:border-slate-700'
                ]"
              />
              <span v-if="formErrors.sku" class="text-[11px] text-rose-500 font-semibold block mt-1">
                {{ formErrors.sku }}
              </span>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Marca / Fabricante</label>
              <input
                v-model="productForm.marca"
                type="text"
                placeholder="Ej: Logitech, Dell, Sony"
                class="w-full p-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <!-- Nombre Comercial -->
          <div>
            <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Nombre Comercial del Producto *</label>
            <input
              v-model="productForm.nombre"
              type="text"
              placeholder="Ej: Teclado Mecánico Inalámbrico MX Keys Mini"
              :class="[
                'w-full p-2.5 bg-slate-50 dark:bg-slate-800 border rounded-xl focus:ring-2 focus:ring-blue-500',
                formErrors.nombre ? 'border-rose-400 ring-1 ring-rose-400' : 'border-slate-200 dark:border-slate-700'
              ]"
            />
            <span v-if="formErrors.nombre" class="text-[11px] text-rose-500 font-semibold block mt-1">
              {{ formErrors.nombre }}
            </span>
          </div>

          <!-- PRECIOS: Precio Venta y Precio Costo (Persistencia en variantes) -->
          <div class="grid grid-cols-2 gap-3 p-3 bg-blue-50/50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/50 rounded-2xl">
            <div>
              <label class="block font-semibold text-slate-800 dark:text-blue-300 mb-1 flex items-center gap-1">
                <DollarSign class="w-3.5 h-3.5 text-blue-600" />
                <span>Precio Venta (BOB) *</span>
              </label>
              <input
                v-model.number="productForm.precio"
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                class="w-full p-2.5 font-bold text-slate-900 dark:text-white bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500"
              />
              <span v-if="formErrors.precio" class="text-[11px] text-rose-500 font-semibold block mt-1">
                {{ formErrors.precio }}
              </span>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Costo Adquisición (BOB)</label>
              <input
                v-model.number="productForm.precio_costo"
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                class="w-full p-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <!-- Categoría y Estado del Ciclo de Vida -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Categoría</label>
              <select
                v-model="productForm.categoria_id"
                class="w-full p-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Sin categoría asignada</option>
                <option v-for="c in categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option>
              </select>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Estado de Ciclo de Vida</label>
              <select
                v-model="productForm.estado"
                class="w-full p-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500 font-semibold"
              >
                <option value="publicado">● Publicado (Visible en tienda)</option>
                <option value="borrador">● Borrador (En edición interna)</option>
                <option value="descontinuado">● Descontinuado (Archivado)</option>
                <option value="inactivo">● Inactivo (Pausado temporal)</option>
              </select>
            </div>
          </div>

          <!-- Descripción Técnica -->
          <div>
            <label class="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Descripción y Especificaciones</label>
            <textarea
              v-model="productForm.descripcion"
              rows="3"
              placeholder="Detalle de características, especificaciones técnicas, compatibilidad..."
              class="w-full p-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500"
            ></textarea>
          </div>

          <!-- Botones de Acción -->
          <div class="flex justify-end gap-2 pt-3 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              @click="showProductModal = false"
              class="px-4 py-2 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl font-semibold"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="isSavingProduct"
              class="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold flex items-center gap-1.5 shadow-sm transition-colors disabled:opacity-60"
            >
              <Loader2 v-if="isSavingProduct" class="w-3.5 h-3.5 animate-spin" />
              <span>{{ isEditing ? 'Guardar Cambios' : 'Registrar y Continuar' }}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
