<script setup lang="ts">
import { notify } from '@/lib/feedback';
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import SalesHistoryView from '@/views/admin/SalesHistoryView.vue';
import HasRole from '@/components/HasRole.vue';
import ProductMultimediaManager from '@/components/ProductMultimediaManager.vue';
import PriceMatrixManager from '@/components/admin/PriceMatrixManager.vue';
import PromotionsManager from '@/components/admin/PromotionsManager.vue';
import ProductPriceMatrix from '@/components/admin/ProductPriceMatrix.vue';
import ComboManager from '@/components/admin/ComboManager.vue';
import ReviewModerationPanel from '@/components/admin/ReviewModerationPanel.vue';
import NotificationsLogPanel from '@/components/admin/NotificationsLogPanel.vue';
import B2BQuotesPanel from '@/components/admin/B2BQuotesPanel.vue';
import ShippingManager from '@/components/admin/ShippingManager.vue';
import AuditLogPanel from '@/components/admin/AuditLogPanel.vue';
import TarjetasRegaloPanel from '@/components/TarjetasRegaloPanel.vue';
import DualCurrencyPrice from '@/components/DualCurrencyPrice.vue';
import InternalUsersManager from '@/components/admin/InternalUsersManager.vue';
import CrmSyncManager from '@/components/admin/CrmSyncManager.vue';
import { apiClient } from '@/api/client';
import type { Producto, ListaPrecio } from '@/types';
import { 
  TrendingUp, 
  ShoppingBag, 
  DollarSign, 
  Users, 
  Package, 
  FileText, 
  MessageSquareText, 
  Mail,
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Edit3,
  FolderTree,
  ImagePlus,
  Image as ImageIcon,
  Plus,
  Save,
  Store,
  X,
  Search,
  Filter,
  Trash2,
  RefreshCw,
  CheckCircle2,
  SlidersHorizontal,
  Sparkles,
  Eye,
  ShieldCheck,
  RotateCcw,
  Settings2,
  Layers,
  Radio,
  Zap,
  Clock,
  Activity,
  ArrowRight,
  Tag,
  Truck
} from 'lucide-vue-next';

interface CategoryNode {
  id: string;
  name: string;
  description: string;
  children?: CategoryNode[];
}

interface AttributeField {
  id: string;
  label: string;
  type: 'text' | 'number' | 'select';
  value: string;
  options?: string[];
  custom?: boolean;
}

interface PriceMatrixRow {
  branch: string;
  web: number;
  pos: number;
  b2b: number;
}

interface CatalogCategory {
  id: string;
  nombre: string;
  descripcion?: string;
}

interface PendingImage {
  name: string;
  dataUrl: string;
  size: number;
}

// Control de Pestañas Principales en Admin
const adminTabs = ['pedidos', 'productos', 'categorias', 'precios', 'promociones', 'combos', 'kpis', 'sincronizacion', 'resenas', 'notificaciones', 'cotizaciones', 'usuarios', 'crm_sync', 'envios', 'vales', 'auditoria'] as const;
type AdminTab = typeof adminTabs[number];
const route = useRoute();
const router = useRouter();
const activeAdminTab = computed<AdminTab>({
  get: () => typeof route.query.tab === 'string' && adminTabs.includes(route.query.tab as AdminTab)
    ? route.query.tab as AdminTab : 'productos',
  set: tab => { void router.replace({ path: '/admin', query: { ...route.query, tab } }); },
});


// ============================================================================
// HISTORIA KAN-17 / RF-01: GESTIÓN DE PRODUCTOS Y CICLO DE VIDA
// ============================================================================
const defaultAdminProducts: Producto[] = [
  {
    id: 'lap-dell-xps15',
    sku: 'LAP-DELL-XPS15',
    nombre: 'Laptop Dell XPS 15 (OLED 4K, Intel Core i7 13va Gen, 32GB RAM, 1TB SSD)',
    marca: 'Dell',
    descripcion: 'Workstation portátil premium con pantalla OLED táctil de 15.6 pulgadas.',
    categoria_id: '53848eb0-b9eb-4d99-b675-ac2176f67e20',
    estado: 'publicado',
    precio: 6767.00,
    precio_costo: 4736.00,
    categorias: { id: '53848eb0-b9eb-4d99-b675-ac2176f67e20', nombre: 'Laptops y PCs' },
    imagenes_producto: [
      { id: 'img-1', producto_id: 'lap-dell-xps15', url: 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 },
      { id: 'img-2', producto_id: 'lap-dell-xps15', url: 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?auto=format&fit=crop&w=800&q=80', es_principal: false, orden: 2 }
    ]
  },
  {
    id: 'mou-log-mx3s',
    sku: 'MOU-LOG-MX3S',
    nombre: 'Mouse Inalámbrico Logitech MX Master 3S con Sensor Darkfield 8K DPI',
    marca: 'Logitech',
    descripcion: 'Mouse ergonómico insignia para creadores y desarrolladores.',
    categoria_id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d',
    estado: 'publicado',
    precio: 899.00,
    precio_costo: 620.00,
    categorias: { id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d', nombre: 'Periféricos' },
    imagenes_producto: [
      { id: 'img-3', producto_id: 'mou-log-mx3s', url: 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'mon-sam-odyssey',
    sku: 'MON-SAM-ODYSSEY',
    nombre: 'Monitor Gamer Samsung Odyssey G7 27 pulg QHD 240Hz 1ms Curvo 1000R',
    marca: 'Samsung',
    descripcion: 'Panel VA QLED con resolución WQHD (2560x1440), certificación HDR600.',
    categoria_id: 'd1543851-f4d8-4c72-b952-dcf4a777666a',
    estado: 'publicado',
    precio: 3450.00,
    precio_costo: 2415.00,
    categorias: { id: 'd1543851-f4d8-4c72-b952-dcf4a777666a', nombre: 'Monitores' },
    imagenes_producto: [
      { id: 'img-4', producto_id: 'mon-sam-odyssey', url: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'aud-sony-wh1000xm5',
    sku: 'AUD-SONY-WH1000XM5',
    nombre: 'Auriculares Inalámbricos Sony WH-1000XM5 Noise Cancelling LDAC',
    marca: 'Sony',
    descripcion: 'Cancelación de ruido líder del sector con procesador dual HD QN1.',
    categoria_id: 'd0998a1f-3b78-4099-928a-b05c70ae472b',
    estado: 'publicado',
    precio: 2650.00,
    precio_costo: 1855.00,
    categorias: { id: 'd0998a1f-3b78-4099-928a-b05c70ae472b', nombre: 'Audio y Video' },
    imagenes_producto: [
      { id: 'img-5', producto_id: 'aud-sony-wh1000xm5', url: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'tec-key-k2pro',
    sku: 'TEC-KEY-K2PRO',
    nombre: 'Teclado Mecánico Inalámbrico Keychron K2 Pro QMK/VIA Custom RGB',
    marca: 'Keychron',
    descripcion: 'Distribución 75% compacta con switches mecánicos Keychron K Pro.',
    categoria_id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d',
    estado: 'publicado',
    precio: 720.00,
    precio_costo: 504.00,
    categorias: { id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d', nombre: 'Periféricos' },
    imagenes_producto: [
      { id: 'img-7', producto_id: 'tec-key-k2pro', url: 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'cam-log-brio4k',
    sku: 'CAM-LOG-BRIO4K',
    nombre: 'Cámara Web Profesional Logitech Brio 4K Ultra HD HDR con Windows Hello',
    marca: 'Logitech',
    descripcion: 'Streaming y videoconferencias cristalinas en 4K Ultra HD a 30 fps.',
    categoria_id: 'd0998a1f-3b78-4099-928a-b05c70ae472b',
    estado: 'publicado',
    precio: 1150.00,
    precio_costo: 805.00,
    categorias: { id: 'd0998a1f-3b78-4099-928a-b05c70ae472b', nombre: 'Audio y Video' },
    imagenes_producto: [
      { id: 'img-8', producto_id: 'cam-log-brio4k', url: 'https://images.unsplash.com/photo-1588702547919-26089e690ecc?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'lap-mac-m3pro',
    sku: 'LAP-MAC-M3PRO',
    nombre: 'Apple MacBook Pro 14 pulgadas Chip M3 Pro (18GB Memoria Unificada, 512GB SSD)',
    marca: 'Apple',
    descripcion: 'Rendimiento profesional extremo con CPU de 11 núcleos, GPU de 14 núcleos.',
    categoria_id: '53848eb0-b9eb-4d99-b675-ac2176f67e20',
    estado: 'publicado',
    precio: 14200.00,
    precio_costo: 9940.00,
    categorias: { id: '53848eb0-b9eb-4d99-b675-ac2176f67e20', nombre: 'Laptops y PCs' },
    imagenes_producto: [
      { id: 'img-9', producto_id: 'lap-mac-m3pro', url: 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  },
  {
    id: 'mon-lg-ultragear',
    sku: 'MON-LG-ULTRAGEAR',
    nombre: 'Monitor Gamer Curvo LG UltraGear 34 pulg WQHD 160Hz 1ms Nano IPS',
    marca: 'LG',
    descripcion: 'Pantalla curva panorámica 21:9 UltraWide con tecnología Nano IPS 1ms.',
    categoria_id: 'd1543851-f4d8-4c72-b952-dcf4a777666a',
    estado: 'publicado',
    precio: 4100.00,
    precio_costo: 2870.00,
    categorias: { id: 'd1543851-f4d8-4c72-b952-dcf4a777666a', nombre: 'Monitores' },
    imagenes_producto: [
      { id: 'img-10', producto_id: 'mon-lg-ultragear', url: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=800&q=80', es_principal: true, orden: 1 }
    ]
  }
];

const productsList = ref<Producto[]>([...defaultAdminProducts]);
const isLoadingProducts = ref(false);
const searchProductQuery = ref('');
const statusFilter = ref<string>('todos');
const currentPage = ref(1);
const itemsPerPage = ref(6);

// Modal para KAN-19 / RF-03: Galería Visual y Multimedia
const selectedMultimediaProduct = ref<Producto | null>(null);

// Modal de Edición de Producto (KAN-307)
const isEditModalOpen = ref(false);
const editingProduct = ref<{
  id: string;
  sku: string;
  nombre: string;
  marca: string;
  descripcion: string;
  categoria_id: string;
  precio: number;
  precio_costo: number;
  estado: string;
} | null>(null);
const editFormError = ref('');
const isSavingEdit = ref(false);

// Modal de Confirmación de Eliminación
const productToDelete = ref<Producto | null>(null);
const isDeletingProduct = ref(false);

// Feedback Toast/Banner
function showFeedback(message: string, type: 'success' | 'error' = 'success') {
  notify[type](message);
}

// Cargar listado de productos desde la API (KAN-306 / KAN-291)
async function loadProductsList() {
  isLoadingProducts.value = true;
  try {
    const res = await apiClient.get('/productos');
    const data = res.data.productos || res.data || [];
    if (Array.isArray(data) && data.length > 0) {
      productsList.value = data;
    } else {
      // Intentar endpoint delta /v1/catalogo/productos
      const altRes = await apiClient.get('/v1/catalogo/productos');
      const altData = Array.isArray(altRes.data) ? altRes.data : altRes.data?.productos || [];
      if (Array.isArray(altData) && altData.length > 0) {
        productsList.value = altData;
      }
    }
  } catch (err: any) {
    console.warn('Fallo cargando /productos, intentando /v1/catalogo/productos:', err);
    try {
      const altRes = await apiClient.get('/v1/catalogo/productos');
      const altData = Array.isArray(altRes.data) ? altRes.data : altRes.data?.productos || [];
      if (Array.isArray(altData) && altData.length > 0) {
        productsList.value = altData;
      }
    } catch {
      showFeedback('Aviso: Mostrando catálogo base sincronizado.', 'error');
    }
  } finally {
    isLoadingProducts.value = false;
    // Sincronizar selector de matriz de precios con productos reales de la BD
    if (productsList.value.length > 0) {
      priceProducts.value = productsList.value.map(p => ({
        id: p.id,
        name: p.nombre,
        sku: p.sku
      }));
      if (!priceProducts.value.some(p => p.id === selectedPriceProduct.value)) {
        selectedPriceProduct.value = priceProducts.value[0]?.id || '';
      }
    }
  }
}

// Cambio rápido de ciclo de vida (KAN-291: publicado, borrador, inactivo, descontinuado)
async function quickChangeStatus(prod: Producto, nuevoEstado: string) {
  try {
    await apiClient.patch(`/productos/${prod.id}/estado`, { estado: nuevoEstado });
    prod.estado = nuevoEstado;
    showFeedback(`El estado de "${prod.nombre}" ahora es "${nuevoEstado.toUpperCase()}".`);
  } catch (err: any) {
    showFeedback(err.response?.data?.error || 'Error al cambiar estado del producto.', 'error');
  }
}

// Abrir modal de edición reactiva (KAN-307)
function openEditModalProduct(prod: Producto) {
  if (catalogCategories.value.length === 0) {
    loadCatalogCategories();
  }
  editingProduct.value = {
    id: prod.id,
    sku: prod.sku,
    nombre: prod.nombre,
    marca: prod.marca || '',
    descripcion: prod.descripcion || '',
    categoria_id: prod.categoria_id || catalogCategories.value[0]?.id || '',
    precio: prod.precio || 0,
    precio_costo: (prod as any).precio_costo || Math.round((prod.precio || 0) * 0.7),
    estado: prod.estado || 'publicado'
  };
  editFormError.value = '';
  isEditModalOpen.value = true;
}

// Guardar cambios de edición (KAN-306 / KAN-307)
async function submitEditProduct() {
  if (!editingProduct.value) return;
  if (!editingProduct.value.sku.trim() || !editingProduct.value.nombre.trim()) {
    editFormError.value = 'El SKU y el Nombre son campos obligatorios.';
    return;
  }
  isSavingEdit.value = true;
  editFormError.value = '';
  try {
    const res = await apiClient.put(`/productos/${editingProduct.value.id}`, {
      sku: editingProduct.value.sku.trim().toUpperCase(),
      nombre: editingProduct.value.nombre.trim(),
      marca: editingProduct.value.marca.trim() || null,
      descripcion: editingProduct.value.descripcion.trim() || null,
      categoria_id: editingProduct.value.categoria_id || null,
      precio: Number(editingProduct.value.precio) || 0,
      precio_costo: Number(editingProduct.value.precio_costo) || 0,
      estado: editingProduct.value.estado
    });

    const updated = res.data.producto || res.data;
    const index = productsList.value.findIndex(p => p.id === editingProduct.value?.id);
    if (index !== -1) {
      productsList.value[index] = {
        ...productsList.value[index],
        ...updated,
        precio: Number(editingProduct.value.precio),
        precio_costo: Number(editingProduct.value.precio_costo)
      };
    }
    isEditModalOpen.value = false;
    showFeedback('Producto actualizado exitosamente con SKU y validaciones validadas.');
  } catch (err: any) {
    editFormError.value = err.response?.data?.error || 'Error al guardar los cambios del producto.';
  } finally {
    isSavingEdit.value = false;
  }
}

// Eliminar producto con confirmación (KAN-291)
async function confirmDeleteProduct() {
  if (!productToDelete.value) return;
  isDeletingProduct.value = true;
  try {
    await apiClient.delete(`/productos/${productToDelete.value.id}`);
    productsList.value = productsList.value.filter(p => p.id !== productToDelete.value?.id);
    showFeedback(`Producto "${productToDelete.value.nombre}" eliminado del catálogo.`);
    productToDelete.value = null;
  } catch (err: any) {
    showFeedback(err.response?.data?.error || 'Error al eliminar producto.', 'error');
  } finally {
    isDeletingProduct.value = false;
  }
}

// Cuando se suben o reordenan fotos en ProductMultimediaManager (KAN-19)
function handleMultimediaUpdated() {
  loadProductsList();
}

// Filtros y Paginación (KAN-291)
const selectedCategoryFilter = ref('todas');

const filteredProductsList = computed(() => {
  return productsList.value.filter(prod => {
    const query = searchProductQuery.value.trim().toLowerCase();
    const matchesSearch = !query ||
      prod.nombre.toLowerCase().includes(query) ||
      prod.sku.toLowerCase().includes(query) ||
      (prod.marca && prod.marca.toLowerCase().includes(query)) ||
      (prod.categorias?.nombre && prod.categorias.nombre.toLowerCase().includes(query));

    const matchesStatus = statusFilter.value === 'todos' || prod.estado?.toLowerCase() === statusFilter.value.toLowerCase();

    const matchesCategory = selectedCategoryFilter.value === 'todas' ||
      prod.categoria_id === selectedCategoryFilter.value ||
      prod.categorias?.id === selectedCategoryFilter.value ||
      (Boolean(prod.categorias?.nombre) && catalogCategories.value.find(c => c.id === selectedCategoryFilter.value)?.nombre?.toLowerCase() === prod.categorias?.nombre?.toLowerCase());

    return matchesSearch && matchesStatus && matchesCategory;
  });
});

const totalPages = computed(() => Math.ceil(filteredProductsList.value.length / itemsPerPage.value) || 1);

const paginatedProducts = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value;
  return filteredProductsList.value.slice(start, start + itemsPerPage.value);
});

const productsStats = computed(() => {
  const total = productsList.value.length;
  const publicados = productsList.value.filter(p => p.estado === 'publicado').length;
  const borradores = productsList.value.filter(p => p.estado === 'borrador').length;
  const conImagenes = productsList.value.filter(p => (p.imagenes_producto && p.imagenes_producto.length > 0)).length;
  return { total, publicados, borradores, conImagenes };
});

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

const lowStockAlerts = computed(() => {
  if (productsList.value.length === 0) {
    return [
      { sku: 'MON-LG-27GP', nombre: 'Monitor LG UltraGear 27"', stockActual: 2, puntoReorden: 5 },
      { sku: 'LAP-DELL-XPS15', nombre: 'Laptop Dell XPS 15', stockActual: 0, puntoReorden: 8 }
    ];
  }
  return productsList.value
    .filter(p => p.estado === 'descontinuado' || p.estado === 'borrador')
    .slice(0, 3)
    .map(p => ({
      sku: p.sku,
      nombre: p.nombre,
      stockActual: p.estado === 'descontinuado' ? 0 : 3,
      puntoReorden: 5
    }));
});

const categories = ref<CategoryNode[]>([
  {
    id: '0201bb04-acb2-46fe-8aa9-198a4701ab54',
    name: 'Laptops y PCs',
    description: 'Equipos portátiles y de escritorio.'
  },
  {
    id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d',
    name: 'Periféricos',
    description: 'Teclados, mouse y accesorios para estaciones de trabajo.'
  },
  {
    id: 'd1543851-f4d8-4c72-b952-dcf4a777666a',
    name: 'Monitores',
    description: 'Pantallas para gaming, diseño y productividad.'
  },
  {
    id: 'd0998a1f-3b78-4099-928a-b05c70ae472b',
    name: 'Audio y Video',
    description: 'Auriculares, micrófonos y cámaras de alta fidelidad.'
  }
]);

const expandedCategoryIds = ref(new Set(['0201bb04-acb2-46fe-8aa9-198a4701ab54', 'bfeabe38-3626-49e1-9b4e-ace0315cd91d']));
const isCreateCategoryModalOpen = ref(false);
const isSavingCategory = ref(false);
const categoryFormError = ref('');
const newCategoryName = ref('');
const newCategoryParentId = ref('');
const newCategoryDescription = ref('');
const newCategoryAttributeInput = ref('');
const newCategoryAttributes = ref<string[]>([]);

function addCategoryAttribute() {
  const value = newCategoryAttributeInput.value.trim();
  if (value && !newCategoryAttributes.value.includes(value)) {
    newCategoryAttributes.value.push(value);
    newCategoryAttributeInput.value = '';
  }
}

function removeCategoryAttribute(index: number) {
  newCategoryAttributes.value.splice(index, 1);
}

async function saveNewCategory() {
  if (!newCategoryName.value.trim()) {
    categoryFormError.value = 'El nombre de la categoria es obligatorio.';
    return;
  }
  isSavingCategory.value = true;
  categoryFormError.value = '';
  try {
    await apiClient.post('/api/v1/catalogo/categorias', {
      nombre: newCategoryName.value.trim(),
      descripcion: newCategoryDescription.value.trim() || null,
      padre_id: newCategoryParentId.value || null,
      atributos_dinamicos: newCategoryAttributes.value,
    });
    await loadCatalogCategories();
    if (newCategoryParentId.value) expandedCategoryIds.value.add(newCategoryParentId.value);
    isCreateCategoryModalOpen.value = false;
  } catch (error: any) {
    categoryFormError.value = error.response?.data?.detail || 'No se pudo crear la categoria.';
  } finally {
    isSavingCategory.value = false;
  }
}

const editingCategory = ref<CategoryNode | null>(null);
const editingName = ref('');
const editingDescription = ref('');
const isProductModalOpen = ref(false);
const selectedProductCategory = ref('');
const productName = ref('');
const productSku = ref('');
const productBrand = ref('');
const productDescription = ref('');
const productPrice = ref<number | null>(null);
const productAttributeFields = ref<AttributeField[]>([]);
const catalogCategories = ref<CatalogCategory[]>([]);
const pendingImages = ref<PendingImage[]>([]);
const imageInput = ref<HTMLInputElement | null>(null);
const isSavingProduct = ref(false);
const productFormMessage = ref('');
const isSavingPriceMatrix = ref(false);
const activePriceLists = ref<ListaPrecio[]>([]);

const priceProducts = ref([
  { id: '7026ea00-797c-43a8-b6e9-58277af347e7', name: 'Monitor Gamer LG UltraGear 27" 165Hz IPS', sku: 'MON-LG-27GP' },
  { id: 'c121e644-d23a-427d-821e-9c4a8bab7812', name: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)', sku: 'LAP-DELL-XPS15' },
  { id: 'a03f1380-bf24-4394-acde-6c726a677df3', name: 'Mouse Inalámbrico Logitech MX Master 3S', sku: 'MOU-LOG-MX3S' }
]);
const selectedPriceProduct = ref('7026ea00-797c-43a8-b6e9-58277af347e7');
const priceMatrix = ref<PriceMatrixRow[]>([
  { branch: 'La Paz Centro (El Prado)', web: 3499, pos: 3420, b2b: 2974 },
  { branch: 'El Alto (Ceja)', web: 3499, pos: 3390, b2b: 2974 },
  { branch: 'Santa Cruz (Equipetrol)', web: 3499, pos: 3674, b2b: 3079 },
  { branch: 'Cochabamba (Cala Cala)', web: 3499, pos: 3420, b2b: 2974 }
]);
const priceMatrixSavedAt = ref('');

// Sincronizar productos disponibles para la matriz de precios desde el catálogo
watch(productsList, (newProds) => {
  if (newProds.length > 0) {
    priceProducts.value = newProds.map(p => ({
      id: p.id,
      name: p.nombre,
      sku: p.sku
    }));
    if (!selectedPriceProduct.value || !newProds.some(p => p.id === selectedPriceProduct.value)) {
      selectedPriceProduct.value = newProds[0].id;
    }
  }
}, { immediate: true });

// Al cambiar el producto seleccionado, cargar sus tarifas diferenciadas
watch(selectedPriceProduct, (newId) => {
  const prod = productsList.value.find(p => p.id === newId);
  const basePrice = prod && prod.precio ? Number(prod.precio) : 3499;
  priceMatrix.value = [
    { branch: 'La Paz Centro (El Prado)', web: basePrice, pos: basePrice, b2b: Math.round(basePrice * 0.85) },
    { branch: 'El Alto (Ceja)', web: basePrice, pos: Math.round(basePrice * 0.98), b2b: Math.round(basePrice * 0.85) },
    { branch: 'Santa Cruz (Equipetrol)', web: basePrice, pos: Math.round(basePrice * 1.05), b2b: Math.round(basePrice * 0.88) },
    { branch: 'Cochabamba (Cala Cala)', web: basePrice, pos: Math.round(basePrice * 0.99), b2b: Math.round(basePrice * 0.85) }
  ];
});

async function loadPriceLists() {
  try {
    const res = await apiClient.get<ListaPrecio[]>('/v1/catalogo/listas-precios');
    if (Array.isArray(res.data) && res.data.length > 0) {
      activePriceLists.value = res.data;
    }
  } catch (err) {
    console.warn('Error cargando listas de precios:', err);
  }
}

const priceValues = computed(() => priceMatrix.value.flatMap((row) => [row.web, row.pos, row.b2b]));
const priceSummary = computed(() => {
  const values = priceValues.value;
  return {
    minimum: Math.min(...values),
    maximum: Math.max(...values),
    average: values.reduce((sum, value) => sum + value, 0) / values.length
  };
});

const attributeTemplates: Record<string, Omit<AttributeField, 'value'>[]> = {
  laptops: [
    { id: 'processor', label: 'Procesador', type: 'text' },
    { id: 'ram', label: 'Memoria RAM', type: 'select', options: ['8 GB', '16 GB', '32 GB', '64 GB'] },
    { id: 'storage', label: 'Almacenamiento', type: 'select', options: ['256 GB SSD', '512 GB SSD', '1 TB SSD', '2 TB SSD'] }
  ],
  monitors: [
    { id: 'screen-size', label: 'Tamaño de pantalla', type: 'number' },
    { id: 'resolution', label: 'Resolución', type: 'select', options: ['Full HD', 'QHD', '4K UHD', '5K'] },
    { id: 'refresh-rate', label: 'Tasa de refresco', type: 'number' }
  ],
  'audio-video': [
    { id: 'connectivity', label: 'Conectividad', type: 'text' },
    { id: 'warranty', label: 'Garantía', type: 'select', options: ['6 meses', '1 año', '2 años'] }
  ],
  'keyboards-mice': [
    { id: 'connection', label: 'Tipo de conexión', type: 'select', options: ['USB', 'Bluetooth', 'Inalámbrico 2.4 GHz'] },
    { id: 'layout', label: 'Distribución', type: 'text' }
  ],
  networking: [
    { id: 'ports', label: 'Cantidad de puertos', type: 'number' },
    { id: 'speed', label: 'Velocidad', type: 'text' }
  ]
};

const visibleCategories = computed(() => {
  const visible: Array<CategoryNode & { depth: number; hasChildren: boolean }> = [];

  function append(nodes: CategoryNode[], depth: number) {
    nodes.forEach((category) => {
      visible.push({ ...category, depth, hasChildren: Boolean(category.children?.length) });
      if (category.children?.length && expandedCategoryIds.value.has(category.id)) {
        append(category.children, depth + 1);
      }
    });
  }

  append(categories.value, 0);
  return visible;
});

const categoryOptions = computed(() => {
  const options: CategoryNode[] = [];
  function append(nodes: CategoryNode[]) {
    nodes.forEach((category) => {
      options.push(category);
      if (category.children) append(category.children);
    });
  }
  append(categories.value);
  return options;
});

function toggleCategory(categoryId: string) {
  const nextExpandedIds = new Set(expandedCategoryIds.value);
  if (nextExpandedIds.has(categoryId)) {
    nextExpandedIds.delete(categoryId);
  } else {
    nextExpandedIds.add(categoryId);
  }
  expandedCategoryIds.value = nextExpandedIds;
}

function openEditModal(category: CategoryNode) {
  editingCategory.value = category;
  editingName.value = category.name;
  editingDescription.value = category.description;
}

function findCategory(categoryId: string, nodes: CategoryNode[]): CategoryNode | undefined {
  for (const category of nodes) {
    if (category.id === categoryId) return category;
    if (category.children) {
      const match = findCategory(categoryId, category.children);
      if (match) return match;
    }
  }
}

function saveCategory() {
  if (!editingCategory.value || !editingName.value.trim()) return;
  const category = findCategory(editingCategory.value.id, categories.value);
  if (category) {
    category.name = editingName.value.trim();
    category.description = editingDescription.value.trim();
  }
  editingCategory.value = null;
}

// Categorías de respaldo para garantizar disponibilidad inmediata
const FALLBACK_CATEGORIES: CatalogCategory[] = [
  { id: '0201bb04-acb2-46fe-8aa9-198a4701ab54', nombre: 'Laptops y PCs', descripcion: 'Equipos portátiles y de escritorio' },
  { id: 'bfeabe38-3626-49e1-9b4e-ace0315cd91d', nombre: 'Periféricos', descripcion: 'Teclados, mouse y accesorios' },
  { id: 'd1543851-f4d8-4c72-b952-dcf4a777666a', nombre: 'Monitores', descripcion: 'Pantallas para gaming y productividad' },
  { id: 'd0998a1f-3b78-4099-928a-b05c70ae472b', nombre: 'Audio y Video', descripcion: 'Auriculares, micrófonos y cámaras' }
];

async function loadCatalogCategories() {
  try {
    const response = await apiClient.get<CatalogCategory[]>('/v1/catalogo/categorias');
    const cats = Array.isArray(response.data) ? response.data : [];
    catalogCategories.value = cats.length > 0 ? cats : FALLBACK_CATEGORIES;
    if (!selectedProductCategory.value && catalogCategories.value.length > 0) {
      selectedProductCategory.value = catalogCategories.value[0].id;
    }
  } catch (err) {
    console.warn('Aviso cargando categorías de Supabase, usando catálogo base:', err);
    catalogCategories.value = FALLBACK_CATEGORIES;
    if (!selectedProductCategory.value && catalogCategories.value.length > 0) {
      selectedProductCategory.value = catalogCategories.value[0].id;
    }
  }
}

function openProductModal() {
  if (catalogCategories.value.length === 0) {
    loadCatalogCategories();
  }
  isProductModalOpen.value = true;
  productName.value = '';
  productSku.value = '';
  productBrand.value = '';
  productDescription.value = '';
  productPrice.value = null;
  selectedProductCategory.value = catalogCategories.value[0]?.id || '0201bb04-acb2-46fe-8aa9-198a4701ab54';
  productAttributeFields.value = [];
  pendingImages.value = [];
  productFormMessage.value = '';
  if (selectedProductCategory.value) {
    updateProductCategory(selectedProductCategory.value);
  }
}

function updateProductCategory(categoryId: string) {
  selectedProductCategory.value = categoryId;
  const category = catalogCategories.value.find((item) => item.id === categoryId);
  const templateKey = category?.nombre.toLowerCase().includes('laptop') ? 'laptops'
    : category?.nombre.toLowerCase().includes('monitor') ? 'monitors'
    : category?.nombre.toLowerCase().includes('audio') ? 'audio-video'
    : category?.nombre.toLowerCase().includes('teclado') || category?.nombre.toLowerCase().includes('mouse') ? 'keyboards-mice'
    : category?.nombre.toLowerCase().includes('red') ? 'networking'
    : '';
  productAttributeFields.value = (attributeTemplates[templateKey] || []).map((field) => ({
    ...field,
    value: ''
  }));
}

function formatImageSize(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function addProductImages(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || []);
  const remainingSlots = 5 - pendingImages.value.length;
  const validFiles = files.slice(0, remainingSlots).filter((file) => file.size <= 5 * 1024 * 1024 && ['image/jpeg', 'image/png', 'image/webp'].includes(file.type));
  if (validFiles.length !== files.length) {
    productFormMessage.value = 'Solo se aceptan hasta 5 imágenes JPEG, PNG o WebP de máximo 5 MB.';
  }
  const images = await Promise.all(validFiles.map((file) => new Promise<PendingImage>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, dataUrl: String(reader.result), size: file.size });
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  })));
  pendingImages.value.push(...images);
  if (imageInput.value) imageInput.value.value = '';
}

function removeProductImage(index: number) {
  pendingImages.value.splice(index, 1);
}

function addCustomAttribute() {
  productAttributeFields.value.push({
    id: `custom-${Date.now()}`,
    label: 'Nuevo atributo',
    type: 'text',
    value: '',
    custom: true
  });
}

function removeAttribute(fieldId: string) {
  productAttributeFields.value = productAttributeFields.value.filter((field) => field.id !== fieldId);
}

async function saveProduct() {
  if (!productName.value.trim() || !productSku.value.trim() || !selectedProductCategory.value || productPrice.value === null) {
    productFormMessage.value = 'Completa nombre, SKU, categoría y precio antes de guardar.';
    return;
  }
  isSavingProduct.value = true;
  productFormMessage.value = '';
  const attributes = productAttributeFields.value.reduce<Record<string, string>>((result, field) => {
    if (field.label.trim()) result[field.label.trim()] = field.value;
    return result;
  }, {});
  try {
    const response = await apiClient.post('/api/v1/catalogo/productos', {
      sku: productSku.value.trim(),
      nombre: productName.value.trim(),
      marca: productBrand.value.trim() || null,
      descripcion: productDescription.value.trim() || null,
      categoria_id: selectedProductCategory.value,
      precio: productPrice.value,
      variantes: [{
        sku: `${productSku.value.trim()}-BASE`,
        nombre_variante: 'Configuración principal',
        atributos: attributes,
        precio: productPrice.value,
        precio_costo: 0
      }],
      imagenes: pendingImages.value.map((image) => ({ data_url: image.dataUrl, nombre: image.name }))
    });
    priceProducts.value.unshift({ id: response.data.id, name: response.data.nombre, sku: response.data.sku });
    selectedPriceProduct.value = response.data.id;
    isProductModalOpen.value = false;
    await loadProductsList();
    showFeedback(`Producto "${response.data.nombre || productName.value}" creado con éxito.`);
  } catch (error: any) {
    productFormMessage.value = error.response?.data?.detail || 'No se pudo guardar el producto en el catálogo.';
  } finally {
    isSavingProduct.value = false;
  }
}

function formatPrice(value: number) {
  return value.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function savePriceMatrix() {
  isSavingPriceMatrix.value = true;
  try {
    const prod = productsList.value.find(p => p.id === selectedPriceProduct.value);
    const varId = prod?.variante_id || prod?.variantes?.[0]?.id || selectedPriceProduct.value;

    // Guardar precios diferenciados en backend (KAN-298)
    await Promise.all([
      apiClient.post('/v1/catalogo/listas-precios/matriz', {
        lista_id: 'lista-web-retail',
        variante_id: varId,
        precio: priceMatrix.value[0].web
      }),
      apiClient.post('/v1/catalogo/listas-precios/matriz', {
        lista_id: 'lista-pos-santacruz',
        variante_id: varId,
        precio: priceMatrix.value[2].pos
      }),
      apiClient.post('/v1/catalogo/listas-precios/matriz', {
        lista_id: 'lista-b2b-corporativo',
        variante_id: varId,
        precio: priceMatrix.value[0].b2b
      })
    ]);

    priceMatrixSavedAt.value = new Date().toLocaleTimeString('es-BO', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
    showFeedback(`Tarifas diferenciadas guardadas exitosamente para ${prod?.sku || 'el producto'}.`);
  } catch (err: any) {
    showFeedback('Error guardando tarifas en la matriz de precios.', 'error');
  } finally {
    isSavingPriceMatrix.value = false;
  }
}

onMounted(() => {
  loadCatalogCategories();
  loadProductsList();
  loadPriceLists();
});
</script>

<template>
  <div class="space-y-6">



    <!-- Header Panel Administrativo -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 dark:border-slate-800 pb-5">
      <div>
        <div class="flex items-center gap-2.5">
          <h1 class="text-2xl font-extrabold text-slate-900 dark:text-white">Panel de Control y Analítica</h1>
          <span class="px-2 py-0.5 rounded-md bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 text-[10px] font-bold uppercase tracking-wider">
            Admin ERP
          </span>
        </div>
        <p class="text-xs text-slate-500 mt-1">Supervisión omnicanal de catálogo de productos, galería multimedia, sucursales y ventas en tiempo real.</p>
      </div>
    </div>

    <!-- Selector de Pestañas del Panel de Administración -->
    <div class="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2 overflow-x-auto">
      <HasRole :roles="['administrador']">
        <button type="button" @click="activeAdminTab = 'auditoria'" :class="['flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all', activeAdminTab === 'auditoria' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800']"><ShieldCheck class="h-4 w-4" /> Auditoría</button>
      </HasRole>
      <button
        @click="activeAdminTab = 'pedidos'"
        :class="['flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0', activeAdminTab === 'pedidos' ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800']"
      >
        <Truck class="w-4 h-4" />
        <span>Pedidos y seguimiento</span>
      </button>
      <button
        @click="activeAdminTab = 'productos'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'productos'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <Package class="w-4 h-4" />
        <span>Gestión de Catálogo & Multimedia</span>
        <span :class="['px-2 py-0.5 rounded-full text-[10px] font-extrabold', activeAdminTab === 'productos' ? 'bg-white/20 text-white' : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200']">
          {{ productsList.length }}
        </span>
      </button>

      <button
        @click="activeAdminTab = 'categorias'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'categorias'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <FolderTree class="w-4 h-4" />
        <span>Categorías & Matriz de Precios</span>
      </button>

      <button
        @click="activeAdminTab = 'kpis'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'kpis'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <TrendingUp class="w-4 h-4" />
        <span>KPIs & Operaciones ERP</span>
      </button>

      <button
        @click="activeAdminTab = 'usuarios'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'usuarios'
            ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <ShieldCheck class="w-4 h-4" />
        <span>Usuarios Internos & Roles (RF-49)</span>
      </button>

      <button
        @click="activeAdminTab = 'crm_sync'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'crm_sync'
            ? 'bg-amber-600 text-white shadow-md shadow-amber-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <RefreshCw class="w-4 h-4" />
        <span>Sincronización CRM (Pub/Sub) [RF-14]</span>
      </button>

      <button
        @click="activeAdminTab = 'notificaciones'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'notificaciones'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <Mail class="w-4 h-4 text-amber-400" />
        <span>Bitácora de Notificaciones</span>
      </button>

      <button
        @click="activeAdminTab = 'cotizaciones'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'cotizaciones'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <FileText class="w-4 h-4 text-indigo-400" />
        <span>Cotizaciones B2B</span>
      </button>
      <button
        @click="activeAdminTab = 'envios'"
        :class="['flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0', activeAdminTab === 'envios' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800']"
      >
        <Truck class="w-4 h-4" />
        <span>Envíos</span>
      </button>
      <button @click="activeAdminTab = 'vales'" :class="['flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0', activeAdminTab === 'vales' ? 'bg-blue-600 text-white shadow-md' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800']">Tarjetas de regalo</button>
    </div>


    <!-- ===================================================================== -->
    <!-- PESTAÑA 1: GESTIÓN DE PRODUCTOS Y MULTIMEDIA (RF-01 / RF-03)          -->
    <!-- ===================================================================== -->
    <SalesHistoryView v-if="activeAdminTab === 'pedidos'" />
    <HasRole v-if="activeAdminTab === 'auditoria'" :roles="['administrador']"><AuditLogPanel /></HasRole>
    <div v-if="activeAdminTab === 'productos'" class="space-y-6">
      <div class="flex flex-wrap items-center justify-end gap-2">
        <button @click="loadProductsList" :disabled="isLoadingProducts" class="p-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold flex items-center gap-1.5" title="Recargar datos">
          <RefreshCw :class="['w-3.5 h-3.5', isLoadingProducts ? 'animate-spin' : '']" />
          <span>Actualizar</span>
        </button>
        <HasRole :roles="['administrador', 'gerente_comercial']">
          <button @click="openProductModal" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-sm flex items-center gap-1.5">
            <Plus class="w-4 h-4" />
            <span>Nuevo Producto</span>
          </button>
        </HasRole>
      </div>
      <!-- Tarjetas de Resumen Rápido de Catálogo -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div class="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <span class="block text-[11px] font-semibold text-slate-500">Total en Catálogo</span>
          <strong class="block text-2xl font-black text-slate-900 dark:text-white mt-1">{{ productsStats.total }}</strong>
          <span class="text-[10px] text-slate-400">SKUs registrados</span>
        </div>
        <div class="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <span class="block text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">Publicados (Web/POS)</span>
          <strong class="block text-2xl font-black text-emerald-700 dark:text-emerald-300 mt-1">{{ productsStats.publicados }}</strong>
          <span class="text-[10px] text-slate-400">Visibles para venta</span>
        </div>
        <div class="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <span class="block text-[11px] font-semibold text-amber-600 dark:text-amber-400">En Borrador / Revisión</span>
          <strong class="block text-2xl font-black text-amber-700 dark:text-amber-300 mt-1">{{ productsStats.borradores }}</strong>
          <span class="text-[10px] text-slate-400">Edición en progreso</span>
        </div>
        <div class="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <span class="block text-[11px] font-semibold text-blue-600 dark:text-blue-400">Con Galería Multimedia</span>
          <strong class="block text-2xl font-black text-blue-700 dark:text-blue-300 mt-1">{{ productsStats.conImagenes }}</strong>
          <span class="text-[10px] text-slate-400">Fotos en Supabase Storage</span>
        </div>
      </div>

      <!-- Barra de Filtros, Búsqueda y Paginación (KAN-291) -->
      <div class="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <!-- Buscador -->
        <div class="relative flex-1 max-w-md">
          <Search class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            v-model="searchProductQuery"
            type="text"
            placeholder="Buscar producto por SKU, nombre o marca..."
            class="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>

        <div class="flex items-center gap-3 flex-wrap">
          <!-- Filtro por Categoría (KAN-291) -->
          <div class="flex items-center gap-1.5">
            <span class="text-xs text-slate-400 font-semibold flex items-center gap-1">
              <Layers class="w-3.5 h-3.5" /> Categoría:
            </span>
            <select
              v-model="selectedCategoryFilter"
              @change="currentPage = 1"
              class="px-2.5 py-1 text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
            >
              <option value="todas">Todas las categorías</option>
              <option v-for="cat in catalogCategories" :key="cat.id" :value="cat.id">{{ cat.nombre }}</option>
            </select>
          </div>

          <!-- Filtros por Estado del Ciclo de Vida (KAN-291) -->
          <div class="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
            <span class="text-xs text-slate-400 font-semibold mr-1 flex items-center gap-1">
              <Filter class="w-3.5 h-3.5" /> Estado:
            </span>
            <button
              v-for="st in ['todos', 'publicado', 'borrador', 'inactivo', 'descontinuado']"
              :key="st"
              @click="statusFilter = st; currentPage = 1"
              :class="[
                'px-2.5 py-1 rounded-lg text-xs font-semibold capitalize transition-colors',
                statusFilter === st
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200'
              ]"
            >
              {{ st }}
            </button>
          </div>
        </div>
      </div>

      <!-- Tabla de Ciclo de Vida de Productos (KAN-291) -->
      <section class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div class="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Package class="w-4 h-4 text-blue-600" />
              Catálogo de Productos y Estado de Ciclo de Vida (RF-01)
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">Control de SKU único, precios base, galería multimedia y estados de publicación.</p>
          </div>
          <span class="text-[11px] font-semibold text-slate-500 bg-slate-100 dark:bg-slate-800 px-2.5 py-1 rounded-lg self-start sm:self-auto">
            Mostrando {{ paginatedProducts.length }} de {{ filteredProductsList.length }} productos
          </span>
        </div>

        <div v-if="isLoadingProducts" class="p-12 text-center text-xs text-slate-500 flex flex-col items-center justify-center gap-3">
          <RefreshCw class="w-6 h-6 animate-spin text-blue-600" />
          <span>Cargando catálogo de productos y recursos multimedia...</span>
        </div>

        <div v-else-if="filteredProductsList.length === 0" class="p-12 text-center space-y-3">
          <Package class="w-10 h-10 text-slate-300 dark:text-slate-700 mx-auto" />
          <p class="text-sm font-bold text-slate-700 dark:text-slate-300">No se encontraron productos</p>
          <p class="text-xs text-slate-400">Intenta con otro término de búsqueda o crea un nuevo producto en el catálogo.</p>
          <button @click="openProductModal" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-bold shadow-sm">
            + Crear Primer Producto
          </button>
        </div>

        <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[800px] text-left text-xs">
            <thead class="bg-slate-50 dark:bg-slate-800/80 text-slate-500 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th class="p-3.5">Portada & Multimedia</th>
                <th class="p-3.5">Producto / SKU</th>
                <th class="p-3.5">Categoría</th>
                <th class="p-3.5">Precio Web</th>
                <th class="p-3.5">Ciclo de Vida (Estado)</th>
                <th class="p-3.5 text-right">Acciones Rápidas</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="prod in paginatedProducts" :key="prod.id" class="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                <!-- Portada y Multimedia (KAN-19 / KAN-78) -->
                <td class="p-3.5">
                  <div class="flex items-center gap-3">
                    <div
                      class="relative w-12 h-12 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-100 dark:bg-slate-800 shrink-0 cursor-pointer group shadow-sm"
                      @click="selectedMultimediaProduct = prod"
                      title="Abrir gestor multimedia"
                    >
                      <img
                        v-if="prod.imagenes_producto && prod.imagenes_producto.length > 0"
                        :src="(prod.imagenes_producto.find(i => i.es_principal) || prod.imagenes_producto[0]).url"
                        :alt="prod.nombre"
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform"
                      />
                      <div v-else class="w-full h-full flex items-center justify-center text-slate-400">
                        <ImageIcon class="w-5 h-5" />
                      </div>
                      <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                        <Eye class="w-4 h-4" />
                      </div>
                    </div>
                    <div>
                      <button
                        @click="selectedMultimediaProduct = prod"
                        class="text-[11px] font-bold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      >
                        <ImageIcon class="w-3.5 h-3.5" />
                        <span>{{ (prod.imagenes_producto && prod.imagenes_producto.length) || 0 }} foto(s)</span>
                      </button>
                      <span v-if="prod.imagenes_producto && prod.imagenes_producto.some(i => i.es_principal)" class="text-[9px] text-emerald-600 font-bold block">
                        ★ Con Portada
                      </span>
                    </div>
                  </div>
                </td>

                <!-- Nombre y SKU con unicidad KAN-287 -->
                <td class="p-3.5">
                  <p class="font-bold text-slate-900 dark:text-white line-clamp-1">{{ prod.nombre }}</p>
                  <div class="flex items-center gap-2 mt-0.5">
                    <span class="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      {{ prod.sku }}
                    </span>
                    <span v-if="prod.marca" class="text-[10px] text-slate-400">{{ prod.marca }}</span>
                  </div>
                </td>

                <!-- Categoría -->
                <td class="p-3.5">
                  <span class="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                    {{ prod.categorias?.nombre || 'General' }}
                  </span>
                </td>

                <!-- Precio con Moneda Dual (KAN-299) -->
                <td class="p-3.5">
                  <DualCurrencyPrice :price="prod.precio || 0" size="xs" layout="stacked" />
                  <span v-if="(prod as any).precio_costo" class="text-[9px] text-slate-400 block mt-0.5">
                    Costo: BOB {{ formatPrice((prod as any).precio_costo) }}
                  </span>
                </td>

                <!-- Ciclo de Vida: Selector rápido (KAN-291) -->
                <td class="p-3.5">
                  <div class="flex items-center gap-1.5">
                    <select
                      :value="prod.estado || 'publicado'"
                      @change="quickChangeStatus(prod, ($event.target as HTMLSelectElement).value)"
                      :class="[
                        'px-2.5 py-1 rounded-lg text-xs font-bold outline-none border transition-colors cursor-pointer',
                        prod.estado === 'publicado'
                          ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                          : prod.estado === 'borrador'
                          ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                          : prod.estado === 'inactivo'
                          ? 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-700'
                          : 'bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800'
                      ]"
                    >
                      <option value="publicado">Publicado</option>
                      <option value="borrador">Borrador</option>
                      <option value="inactivo">Inactivo</option>
                      <option value="descontinuado">Descontinuado</option>
                    </select>
                  </div>
                </td>

                <!-- Acciones Rápidas (KAN-291, KAN-19) -->
                <td class="p-3.5 text-right">
                  <div class="inline-flex items-center gap-1.5">
                    <!-- Botón Gestor Multimedia (KAN-19) -->
                    <button
                      type="button"
                      @click="selectedMultimediaProduct = prod"
                      class="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 hover:bg-blue-100 transition-colors flex items-center gap-1"
                      title="Administrar galería multimedia (Subir, ordenar y portada)"
                    >
                      <ImageIcon class="w-3.5 h-3.5" />
                      <span class="hidden md:inline">Multimedia</span>
                    </button>

                    <!-- Botón Editar Producto (KAN-307) -->
                    <button
                      type="button"
                      @click="openEditModalProduct(prod)"
                      class="p-1.5 rounded-lg text-slate-500 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="Editar datos del producto"
                    >
                      <Edit3 class="w-4 h-4" />
                    </button>

                    <!-- Botón Eliminar Producto (KAN-291) -->
                    <button
                      type="button"
                      @click="productToDelete = prod"
                      class="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                      title="Eliminar producto"
                    >
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Paginador Interactivo (KAN-291) -->
        <div v-if="totalPages > 1" class="p-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between gap-4">
          <p class="text-xs text-slate-500">
            Página <strong class="text-slate-800 dark:text-slate-200">{{ currentPage }}</strong> de <strong class="text-slate-800 dark:text-slate-200">{{ totalPages }}</strong>
          </p>
          <div class="flex items-center gap-1.5">
            <button
              :disabled="currentPage === 1"
              @click="currentPage--"
              class="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1"
            >
              <ChevronLeft class="w-3.5 h-3.5" /> Anterior
            </button>
            <div class="flex items-center gap-1">
              <button
                v-for="p in totalPages"
                :key="p"
                @click="currentPage = p"
                :class="[
                  'w-7 h-7 rounded-lg text-xs font-bold flex items-center justify-center transition-colors',
                  currentPage === p
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                ]"
              >
                {{ p }}
              </button>
            </div>
            <button
              :disabled="currentPage === totalPages"
              @click="currentPage++"
              class="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs font-semibold disabled:opacity-40 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1"
            >
              Siguiente <ChevronRight class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </section>
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA 2: CATEGORÍAS & MATRIZ DE PRECIOS                             -->
    <!-- ===================================================================== -->
    <div v-show="activeAdminTab === 'categorias'" class="space-y-6">
      <!-- Gestión de Categorías -->
      <section class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div class="flex items-start gap-3">
            <span class="p-2.5 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400">
              <FolderTree class="w-5 h-5" />
            </span>
            <div>
              <h2 class="text-sm font-bold text-slate-900 dark:text-white">Árbol de categorías</h2>
              <p class="text-xs text-slate-500 mt-1">Organiza la jerarquía del catálogo y actualiza sus datos.</p>
            </div>
          </div>
          <span class="text-[11px] font-semibold text-slate-500 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg">
            {{ categories.length }} categorías principales
          </span>
        </div>

        <div class="divide-y divide-slate-100 dark:divide-slate-800">
          <div
            v-for="category in visibleCategories"
            :key="category.id"
            class="min-h-16 px-5 py-3 flex items-center gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
            :style="{ paddingLeft: `${1.25 + category.depth * 2}rem` }"
          >
            <button
              v-if="category.hasChildren"
              type="button"
              class="w-6 h-6 flex items-center justify-center rounded-md text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-200"
              :aria-label="expandedCategoryIds.has(category.id) ? `Contraer ${category.name}` : `Expandir ${category.name}`"
              @click="toggleCategory(category.id)"
            >
              <ChevronDown v-if="expandedCategoryIds.has(category.id)" class="w-4 h-4" />
              <ChevronRight v-else class="w-4 h-4" />
            </button>
            <span v-else class="w-6" aria-hidden="true" />

            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <span :class="category.depth === 0 ? 'text-sm font-bold' : 'text-sm font-medium'" class="text-slate-800 dark:text-slate-100">
                  {{ category.name }}
                </span>
                <span v-if="category.hasChildren" class="text-[10px] text-slate-400">{{ category.children?.length }} subcategorías</span>
              </div>
              <p class="text-xs text-slate-500 truncate mt-0.5">{{ category.description }}</p>
            </div>

            <HasRole :roles="['administrador', 'gerente_comercial']">
              <button
                type="button"
                class="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40"
                :aria-label="`Editar ${category.name}`"
                @click="openEditModal(category)"
              >
                <Edit3 class="w-3.5 h-3.5" />
                Editar
              </button>
            </HasRole>
          </div>
        </div>
      </section>

      <!-- Matriz de precios por sucursal y canal (RF-04 / KAN-298) -->
      <HasRole :roles="['administrador', 'gerente_comercial']">
        <section class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden space-y-4">
          <!-- Header de Matriz de Precios -->
          <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div class="flex items-start gap-3">
              <span class="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400">
                <DollarSign class="w-5 h-5" />
              </span>
              <div>
                <h2 class="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  Matriz de Precios y Tarifas Diferenciadas (RF-04)
                  <span class="text-[10px] bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 font-bold px-2 py-0.5 rounded-full">Moneda Dual BOB / USD</span>
                </h2>
                <p class="text-xs text-slate-500 mt-0.5">Define precios por sucursal, canal (Web vs POS) y tipo de cliente (Retail vs B2B Corporativo).</p>
              </div>
            </div>
            <label class="flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Producto:
              <select v-model="selectedPriceProduct" class="min-w-64 px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs font-bold outline-none focus:border-emerald-500">
                <option v-for="product in priceProducts" :key="product.id" :value="product.id">[{{ product.sku }}] {{ product.name }}</option>
              </select>
            </label>
          </div>

          <!-- Listas de Precios Activas (KAN-296) -->
          <div class="px-5 pt-1">
            <h3 class="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-1.5">
              <FileText class="w-3.5 h-3.5 text-blue-500" /> Listas de Precios y Políticas Comerciales Activas:
            </h3>
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <div 
                v-for="lp in (activePriceLists.length > 0 ? activePriceLists : [
                  { id: 'web', nombre: 'Tarifa Web Retail', canal: 'web', tipo_cliente: 'retail', factor_ajuste: 1.0, moneda: 'BOB' },
                  { id: 'pos', nombre: 'Tarifa POS La Paz', canal: 'pos', tipo_cliente: 'retail', factor_ajuste: 1.0, moneda: 'BOB' },
                  { id: 'scz', nombre: 'Tarifa POS Santa Cruz', canal: 'pos', tipo_cliente: 'retail', factor_ajuste: 1.05, moneda: 'BOB' },
                  { id: 'b2b', nombre: 'Tarifa B2B Mayorista', canal: 'b2b', tipo_cliente: 'corporativo_b2b', factor_ajuste: 0.85, moneda: 'BOB' }
                ])"
                :key="lp.id"
                class="p-2.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 text-[11px]"
              >
                <div class="flex justify-between items-center">
                  <span class="font-bold text-slate-800 dark:text-slate-200 truncate">{{ lp.nombre }}</span>
                  <span class="text-[9px] font-mono uppercase bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 px-1 rounded">{{ lp.canal }}</span>
                </div>
                <div class="mt-1 flex justify-between text-slate-500 text-[10px]">
                  <span>Factor: {{ lp.factor_ajuste || 1.0 }}x</span>
                  <span class="font-bold text-emerald-600">
                    {{ (lp.factor_ajuste || 1.0) < 1.0 ? `${Math.round((1 - (lp.factor_ajuste || 1.0)) * 100)}% desc.` : ((lp.factor_ajuste || 1.0) > 1.0 ? `+${Math.round(((lp.factor_ajuste || 1.0) - 1) * 100)}% recargo` : 'Base') }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Resumen de Precios -->
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 px-5 pt-2">
            <div class="px-4 py-3 rounded-lg bg-slate-50 dark:bg-slate-800/70 border border-slate-200/60 dark:border-slate-700/60">
              <span class="block text-[11px] text-slate-500 font-semibold">Precio Mínimo (Mayorista B2B)</span>
              <div class="mt-1">
                <DualCurrencyPrice :price="priceSummary.minimum" size="md" colorClass="text-slate-900 dark:text-white" />
              </div>
            </div>
            <div class="px-4 py-3 rounded-lg bg-slate-50 dark:bg-slate-800/70 border border-slate-200/60 dark:border-slate-700/60">
              <span class="block text-[11px] text-slate-500 font-semibold">Precio Máximo (Sucursales con Flete)</span>
              <div class="mt-1">
                <DualCurrencyPrice :price="priceSummary.maximum" size="md" colorClass="text-slate-900 dark:text-white" />
              </div>
            </div>
            <div class="px-4 py-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-800/60">
              <span class="block text-[11px] text-emerald-700 dark:text-emerald-400 font-semibold">Promedio de Tarifas</span>
              <div class="mt-1">
                <DualCurrencyPrice :price="priceSummary.average" size="md" colorClass="text-emerald-800 dark:text-emerald-300" />
              </div>
            </div>
          </div>

          <!-- Tabla de la Matriz de Precios (KAN-298) con Moneda Dual (KAN-299) -->
          <div class="overflow-x-auto px-5">
            <table class="w-full min-w-[700px] text-left text-xs border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
              <thead class="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold">
                <tr>
                  <th class="p-3.5">Sucursal / Región</th>
                  <th class="p-3.5"><span class="inline-flex items-center gap-1.5"><ShoppingBag class="w-3.5 h-3.5 text-blue-500" /> Canal Web (Retail)</span></th>
                  <th class="p-3.5"><span class="inline-flex items-center gap-1.5"><Store class="w-3.5 h-3.5 text-emerald-500" /> Canal POS (Caja Mostrador)</span></th>
                  <th class="p-3.5"><span class="inline-flex items-center gap-1.5"><Users class="w-3.5 h-3.5 text-indigo-500" /> Canal B2B (Corporativo)</span></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                <tr v-for="row in priceMatrix" :key="row.branch" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td class="p-3.5 font-bold text-slate-900 dark:text-white">{{ row.branch }}</td>
                  <td class="p-3">
                    <div class="space-y-1">
                      <div class="flex items-center gap-1">
                        <span class="text-slate-400 text-[11px] font-bold">BOB</span>
                        <input v-model.number="row.web" type="number" min="0" step="1" class="w-28 px-2 py-1.5 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-bold text-slate-900 dark:text-white text-xs outline-none focus:border-blue-500" />
                      </div>
                      <span class="text-[10px] text-slate-400 font-mono block">
                        ≈ ${{ (Number(row.web || 0) / 6.96).toFixed(2) }} USD
                      </span>
                    </div>
                  </td>
                  <td class="p-3">
                    <div class="space-y-1">
                      <div class="flex items-center gap-1">
                        <span class="text-slate-400 text-[11px] font-bold">BOB</span>
                        <input v-model.number="row.pos" type="number" min="0" step="1" class="w-28 px-2 py-1.5 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-bold text-slate-900 dark:text-white text-xs outline-none focus:border-emerald-500" />
                      </div>
                      <span class="text-[10px] text-slate-400 font-mono block">
                        ≈ ${{ (Number(row.pos || 0) / 6.96).toFixed(2) }} USD
                      </span>
                    </div>
                  </td>
                  <td class="p-3">
                    <div class="space-y-1">
                      <div class="flex items-center gap-1">
                        <span class="text-slate-400 text-[11px] font-bold">BOB</span>
                        <input v-model.number="row.b2b" type="number" min="0" step="1" class="w-28 px-2 py-1.5 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-bold text-slate-900 dark:text-white text-xs outline-none focus:border-indigo-500" />
                      </div>
                      <span class="text-[10px] text-slate-400 font-mono block">
                        ≈ ${{ (Number(row.b2b || 0) / 6.96).toFixed(2) }} USD
                      </span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="p-5 border-t border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <p class="text-[11px] text-slate-500">
              {{ priceMatrixSavedAt ? `Matriz de tarifas guardada en backend a las ${priceMatrixSavedAt}.` : 'Modifica las tarifas y presiona Guardar para persistir en las listas de precios de la empresa.' }}
            </p>
            <button 
              type="button" 
              :disabled="isSavingPriceMatrix"
              class="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold rounded-lg shadow-sm" 
              @click="savePriceMatrix"
            >
              <RefreshCw v-if="isSavingPriceMatrix" class="w-3.5 h-3.5 animate-spin" />
              <Save v-else class="w-3.5 h-3.5" />
              <span>{{ isSavingPriceMatrix ? 'Guardando en Backend...' : 'Guardar Tarifas Diferenciadas' }}</span>
            </button>
          </div>
        </section>
      </HasRole>
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA 3: KPIS & OPERACIONES ERP                                     -->
    <!-- ===================================================================== -->
    <div v-show="activeAdminTab === 'kpis'" class="space-y-6">
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
            <router-link to="/admin/ventas" class="text-xs text-blue-600 hover:underline font-semibold">Ver historial</router-link>
            <router-link to="/admin/reembolsos" class="ml-3 text-xs text-rose-600 hover:underline font-semibold" data-testid="link-reembolsos">Reembolsos</router-link>
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

    <!-- ===================================================================== -->
    <!-- PESTAÑA 4: GESTIÓN DE USUARIOS INTERNOS Y ROLES (RF-49 / KAN-421)     -->
    <!-- Subtareas: KAN-423, KAN-424, KAN-425                                 -->
    <!-- ===================================================================== -->
    <div v-show="activeAdminTab === 'usuarios'" class="space-y-6">
      <InternalUsersManager />
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA 5: SINCRONIZACIÓN ASÍNCRONA CON CRM VÍA PUB/SUB (RF-14 / KAN-40) -->
    <!-- Subtareas: KAN-169, KAN-171, KAN-173                                 -->
    <!-- ===================================================================== -->
    <div v-show="activeAdminTab === 'crm_sync'" class="space-y-6">
      <CrmSyncManager />
  </div>
    <div v-if="activeAdminTab === 'combos'" class="space-y-6">
      <ComboManager />
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA: MODERACIÓN DE RESEÑAS DE CLIENTES                             -->
    <!-- ===================================================================== -->
    <div v-if="activeAdminTab === 'resenas'" class="space-y-6">
      <HasRole :roles="['administrador', 'gerente_comercial']">
        <ReviewModerationPanel />
      </HasRole>
    </div>

    <div v-if="activeAdminTab === 'notificaciones'" class="space-y-6">
      <HasRole :roles="['administrador', 'gerente_comercial']">
        <NotificationsLogPanel />
      </HasRole>
    </div>

    <div v-if="activeAdminTab === 'cotizaciones'" class="space-y-6">
      <HasRole :roles="['administrador', 'gerente_comercial']">
        <B2BQuotesPanel />
      </HasRole>
  </div>
    <div v-if="activeAdminTab === 'vales'" class="space-y-6">
      <HasRole :roles="['administrador', 'gerente_comercial']"><TarjetasRegaloPanel administracion /></HasRole>
    </div>
    <div v-if="activeAdminTab === 'envios'" class="space-y-6">
      <HasRole :roles="['administrador', 'gerente_comercial']"><ShippingManager /></HasRole>
    </div>

    <!-- Modal de Creación de Categoría -->
    <div
      v-if="isCreateCategoryModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      @click.self="isCreateCategoryModalOpen = false"
    >
      <div class="w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden my-8">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-800/40">
          <div class="flex items-center gap-3">
            <span class="p-2 rounded-xl bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400">
              <FolderTree class="w-5 h-5" />
            </span>
            <div>
              <h2 class="text-base font-extrabold text-slate-900 dark:text-white">Nueva Categoría</h2>
              <p class="text-xs text-slate-500">Estructura jerárquica y atributos dinámicos</p>
            </div>
          </div>
          <button
            type="button"
            class="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-700/60 transition-colors"
            @click="isCreateCategoryModalOpen = false"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <form class="p-6 space-y-4" @submit.prevent="saveNewCategory">
          <div v-if="categoryFormError" class="p-3 text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-600 rounded-xl font-medium">
            {{ categoryFormError }}
          </div>

          <!-- Nombre -->
          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">
              Nombre de la Categoría <span class="text-rose-500">*</span>
            </label>
            <input
              v-model="newCategoryName"
              type="text"
              placeholder="Ej. Componentes, Tarjetas Gráficas, Audio..."
              required
              class="w-full px-3.5 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
            />
          </div>

          <!-- Categoría Padre (Jerarquía Recursiva) -->
          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">
              Categoría Superior / Padre
            </label>
            <select
              v-model="newCategoryParentId"
              class="w-full px-3.5 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
            >
              <option value="">(Ninguna - Categoría Principal Raíz)</option>
              <option
                v-for="cat in catalogCategories"
                :key="cat.id"
                :value="cat.id"
              >
                {{ cat.nombre }}
              </option>
            </select>
            <p class="text-[11px] text-slate-400">Si seleccionas una categoría superior, esta pasará a ser una subcategoría anidada.</p>
          </div>

          <!-- Descripción -->
          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Descripción</label>
            <textarea
              v-model="newCategoryDescription"
              rows="2"
              placeholder="Breve reseña del tipo de productos comprendidos..."
              class="w-full px-3.5 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none resize-none"
            />
          </div>

          <!-- Atributos Dinámicos -->
          <div class="space-y-2 pt-1 border-t border-slate-100 dark:border-slate-800">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between">
              <span>Atributos Dinámicos Recomendados</span>
              <span class="text-[10px] font-normal text-slate-400">Campos técnicos que solicitará al crear productos</span>
            </label>

            <div class="flex gap-2">
              <input
                v-model="newCategoryAttributeInput"
                type="text"
                placeholder="Ej. RAM, Socket, Watts, Pulgadas, Color..."
                class="flex-1 px-3 py-2 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 outline-none"
                @keydown.enter.prevent="addCategoryAttribute"
              />
              <button
                type="button"
                @click="addCategoryAttribute"
                class="px-3 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-bold text-slate-700 dark:text-slate-200 rounded-xl transition-colors"
              >
                + Añadir
              </button>
            </div>

            <!-- Chips de Atributos -->
            <div v-if="newCategoryAttributes.length > 0" class="flex flex-wrap gap-1.5 pt-1">
              <span
                v-for="(attr, idx) in newCategoryAttributes"
                :key="attr"
                class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60 rounded-lg"
              >
                {{ attr }}
                <button
                  type="button"
                  @click="removeCategoryAttribute(idx)"
                  class="text-blue-500 hover:text-rose-600 ml-0.5"
                >
                  <X class="w-3 h-3" />
                </button>
              </span>
            </div>
            <p v-else class="text-[11px] text-slate-400 italic">No hay atributos específicos agregados (opcional).</p>
          </div>

          <div class="flex justify-end gap-2.5 pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              class="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              @click="isCreateCategoryModalOpen = false"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="isSavingCategory"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm transition-colors disabled:opacity-50"
            >
              <Save class="w-3.5 h-3.5" />
              {{ isSavingCategory ? 'Creando...' : 'Crear Categoría' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal de Edición de Categoría -->

    <div
      v-if="editingCategory"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="category-modal-title"
      @click.self="editingCategory = null"
    >
      <div class="w-full max-w-lg bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <h2 id="category-modal-title" class="text-base font-bold text-slate-900 dark:text-white">Editar categoría</h2>
            <p class="text-xs text-slate-500 mt-1">Actualiza la información visible en el catálogo.</p>
          </div>
          <button
            type="button"
            class="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Cerrar modal"
            @click="editingCategory = null"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <form class="p-5 space-y-4" @submit.prevent="saveCategory">
          <label class="block space-y-1.5">
            <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Nombre</span>
            <input
              v-model="editingName"
              type="text"
              required
              autofocus
              class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
            />
          </label>

          <label class="block space-y-1.5">
            <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Descripción</span>
            <textarea
              v-model="editingDescription"
              rows="3"
              class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none resize-none"
            />
          </label>

          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              class="px-3.5 py-2 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
              @click="editingCategory = null"
            >
              Cancelar
            </button>
            <button
              type="submit"
              class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm"
            >
              <Save class="w-3.5 h-3.5" />
              Guardar cambios
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Modal de Nuevo Producto con Atributos Dinámicos -->
    <div
      v-if="isProductModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="product-modal-title"
      @click.self="isProductModalOpen = false"
    >
      <div class="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-700">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div>
            <h2 id="product-modal-title" class="text-base font-bold text-slate-900 dark:text-white">Nuevo producto</h2>
            <p class="text-xs text-slate-500 mt-1">Selecciona una categoría para cargar sus atributos sugeridos.</p>
          </div>
          <button type="button" class="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Cerrar modal" @click="isProductModalOpen = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <form class="p-5 space-y-5" @submit.prevent="saveProduct">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label class="block space-y-1.5">
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Nombre del producto</span>
              <input v-model="productName" type="text" required placeholder="Ej. Laptop Lenovo ThinkPad" class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none" />
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">SKU</span>
              <input v-model="productSku" type="text" required placeholder="Ej. LAP-LEN-T14" class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none uppercase" />
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Marca</span>
              <input v-model="productBrand" type="text" placeholder="Ej. Lenovo" class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none" />
            </label>
            <label class="block space-y-1.5">
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Precio web (BOB)</span>
              <input v-model.number="productPrice" type="number" min="0" step="0.01" required placeholder="0.00" class="w-full px-3 py-2.5 text-sm font-semibold bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none" />
            </label>
          </div>

          <label class="block space-y-1.5">
            <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Descripción</span>
            <textarea v-model="productDescription" rows="2" placeholder="Describe las características principales del producto" class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none resize-none" />
          </label>

          <label class="block space-y-1.5">
            <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">Categoría</span>
            <select
              :value="selectedProductCategory"
              required
              class="w-full px-3 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
              @change="updateProductCategory(($event.target as HTMLSelectElement).value)"
            >
              <option value="">Selecciona una categoría</option>
              <option v-for="category in catalogCategories" :key="category.id" :value="category.id">{{ category.nombre }}</option>
            </select>
          </label>

          <section class="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            <div class="p-4 bg-slate-50 dark:bg-slate-800/60 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 class="text-sm font-bold text-slate-800 dark:text-slate-100">Imágenes del producto</h3>
                <p class="text-[11px] text-slate-500 mt-1">Hasta 5 archivos JPEG, PNG o WebP. Máximo 5 MB por imagen.</p>
              </div>
              <button type="button" class="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-white border border-slate-300 hover:border-blue-400 text-xs font-semibold text-slate-700" @click="imageInput?.click()">
                <ImagePlus class="w-4 h-4 text-blue-600" />
                Añadir imágenes
              </button>
              <input ref="imageInput" class="hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple @change="addProductImages" />
            </div>
            <div v-if="pendingImages.length" class="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div v-for="(image, index) in pendingImages" :key="image.dataUrl" class="relative overflow-hidden rounded-lg border border-slate-200 bg-slate-100 aspect-square group">
                <img :src="image.dataUrl" :alt="image.name" class="w-full h-full object-cover" />
                <div class="absolute inset-x-0 bottom-0 p-2 bg-slate-950/75 text-white">
                  <p class="truncate text-[10px] font-semibold">{{ image.name }}</p>
                  <p class="text-[10px] text-slate-300">{{ formatImageSize(image.size) }}</p>
                </div>
                <button type="button" class="absolute top-2 right-2 p-1.5 rounded-md bg-white text-rose-600 shadow-sm opacity-0 group-hover:opacity-100" :aria-label="`Eliminar ${image.name}`" @click="removeProductImage(index)">
                  <X class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div v-else class="p-6 text-center text-xs text-slate-400">Agrega una imagen para mostrar este producto en Marketplace.</div>
          </section>

          <div class="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            <div class="p-4 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-bold text-slate-800 dark:text-slate-100">Atributos del producto</h3>
                <p class="text-[11px] text-slate-500 mt-1">Los campos cambian automáticamente según la categoría.</p>
              </div>
              <button type="button" class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-950/40" @click="addCustomAttribute">
                <Plus class="w-3.5 h-3.5" />
                Añadir campo
              </button>
            </div>

            <div v-if="productAttributeFields.length" class="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div v-for="field in productAttributeFields" :key="field.id" class="relative space-y-1.5">
                <div class="flex items-center justify-between gap-2">
                  <input v-if="field.custom" v-model="field.label" type="text" class="min-w-0 flex-1 px-2 py-1 text-xs font-semibold bg-transparent border-b border-slate-300 dark:border-slate-700 focus:border-blue-500 outline-none" aria-label="Nombre del atributo personalizado" />
                  <span v-else class="text-xs font-semibold text-slate-700 dark:text-slate-300">{{ field.label }}</span>
                  <button v-if="field.custom" type="button" class="p-1 text-slate-400 hover:text-rose-600" :aria-label="`Eliminar ${field.label}`" @click="removeAttribute(field.id)">
                    <X class="w-3.5 h-3.5" />
                  </button>
                </div>
                <select v-if="field.type === 'select'" v-model="field.value" class="w-full px-3 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500">
                  <option value="">Selecciona una opción</option>
                  <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
                </select>
                <input v-else v-model="field.value" :type="field.type" :placeholder="field.type === 'number' ? 'Ingresa un valor' : 'Ingresa un valor'" class="w-full px-3 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
              </div>
            </div>
            <div v-else class="p-8 text-center text-xs text-slate-400">
              Selecciona una categoría para mostrar sus atributos.
            </div>
          </div>

          <div class="flex justify-end gap-2 pt-1">
            <button type="button" class="px-3.5 py-2 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800" @click="isProductModalOpen = false">Cancelar</button>
            <button type="submit" :disabled="isSavingProduct" class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-semibold shadow-sm">
              <Save class="w-3.5 h-3.5" />
              {{ isSavingProduct ? 'Guardando...' : 'Guardar producto' }}
            </button>
          </div>
          <p v-if="productFormMessage" class="text-xs font-medium text-rose-600">{{ productFormMessage }}</p>
        </form>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- MODAL DE GESTIÓN MULTIMEDIA (KAN-19 / RF-03)                         -->
    <!-- Subtareas: KAN-75, KAN-76, KAN-77, KAN-78                           -->
    <!-- =================================================================== -->
    <div
      v-if="selectedMultimediaProduct"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      @click.self="selectedMultimediaProduct = null"
    >
      <div class="w-full max-w-4xl max-h-[92vh] overflow-y-auto bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-2 sm:p-4">
        <ProductMultimediaManager
          :producto="selectedMultimediaProduct"
          @close="selectedMultimediaProduct = null"
          @updated="handleMultimediaUpdated"
        />
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- MODAL FORMULARIO REACTIVO DE EDICIÓN DE PRODUCTO (KAN-307 / RF-01)  -->
    <!-- =================================================================== -->
    <div
      v-if="isEditModalOpen && editingProduct"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      @click.self="isEditModalOpen = false"
    >
      <div class="w-full max-w-xl bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-5">
        <div class="flex justify-between items-center border-b border-slate-100 dark:border-slate-800 pb-3">
          <div>
            <h3 class="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Edit3 class="w-4 h-4 text-blue-600" />
              Editar Producto (RF-01 / KAN-307)
            </h3>
            <p class="text-xs text-slate-500 mt-0.5">Actualiza las características, precio y estado del ciclo de vida.</p>
          </div>
          <button @click="isEditModalOpen = false" class="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X class="w-4 h-4" />
          </button>
        </div>

        <form @submit.prevent="submitEditProduct" class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">SKU *</label>
              <input v-model="editingProduct.sku" type="text" required class="w-full px-3 py-2 text-xs font-mono uppercase bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Nombre *</label>
              <input v-model="editingProduct.nombre" type="text" required class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Marca</label>
              <input v-model="editingProduct.marca" type="text" class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Precio Web (BOB) *</label>
              <input v-model.number="editingProduct.precio" type="number" min="0" step="0.01" required class="w-full px-3 py-2 text-xs font-bold bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Precio Costo (BOB)</label>
              <input v-model.number="editingProduct.precio_costo" type="number" min="0" step="0.01" class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500" />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Categoría</label>
              <select v-model="editingProduct.categoria_id" class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500">
                <option value="">Sin categoría asignada</option>
                <option v-for="cat in catalogCategories" :key="cat.id" :value="cat.id">{{ cat.nombre }}</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Estado de Ciclo de Vida</label>
              <select v-model="editingProduct.estado" class="w-full px-3 py-2 text-xs font-semibold bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500">
                <option value="publicado">Publicado (Visible en tienda)</option>
                <option value="borrador">Borrador (Oculto)</option>
                <option value="inactivo">Inactivo (Pausado)</option>
                <option value="descontinuado">Descontinuado (Sin reposición)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Descripción</label>
            <textarea v-model="editingProduct.descripcion" rows="3" class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500 resize-none"></textarea>
          </div>

          <div v-if="editFormError" class="p-2.5 rounded-lg bg-rose-50 text-rose-600 border border-rose-200 text-xs font-medium">
            {{ editFormError }}
          </div>

          <div class="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
            <button type="button" @click="isEditModalOpen = false" class="px-4 py-2 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800">Cancelar</button>
            <button type="submit" :disabled="isSavingEdit" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm disabled:opacity-60">
              <Save class="w-3.5 h-3.5" />
              {{ isSavingEdit ? 'Guardando...' : 'Guardar Cambios' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- =================================================================== -->
    <!-- MODAL DE CONFIRMACIÓN DE ELIMINACIÓN DE PRODUCTO (KAN-291)          -->
    <!-- =================================================================== -->
    <div
      v-if="productToDelete"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4">
        <div class="w-12 h-12 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
          <Trash2 class="w-6 h-6" />
        </div>
        <div class="text-center space-y-1">
          <h3 class="text-base font-bold text-slate-900 dark:text-white">¿Eliminar este producto?</h3>
          <p class="text-xs text-slate-500">
            Se eliminará el producto <strong class="text-slate-800 dark:text-slate-200">"{{ productToDelete.nombre }}"</strong> (SKU: {{ productToDelete.sku }}) junto con todos sus recursos multimedia asociados en Supabase Storage.
          </p>
        </div>
        <div class="flex justify-center gap-3 pt-2">
          <button @click="productToDelete = null" class="px-4 py-2 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800">
            Cancelar
          </button>
          <button @click="confirmDeleteProduct" :disabled="isDeletingProduct" class="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold shadow-sm disabled:opacity-60">
            {{ isDeletingProduct ? 'Eliminando...' : 'Sí, eliminar producto' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
