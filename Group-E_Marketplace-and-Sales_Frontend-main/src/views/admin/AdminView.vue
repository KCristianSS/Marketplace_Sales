<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import HasRole from '@/components/HasRole.vue';
import ProductMultimediaManager from '@/components/ProductMultimediaManager.vue';
import PriceMatrixManager from '@/components/admin/PriceMatrixManager.vue';
import PromotionsManager from '@/components/admin/PromotionsManager.vue';
import ProductPriceMatrix from '@/components/admin/ProductPriceMatrix.vue';
import ComboManager from '@/components/admin/ComboManager.vue';
import ReviewModerationPanel from '@/components/admin/ReviewModerationPanel.vue';
import DualCurrencyPrice from '@/components/DualCurrencyPrice.vue';
import { apiClient } from '@/api/client';
import type { Producto } from '@/types';
import { 
  TrendingUp, 
  ShoppingBag, 
  DollarSign, 
  Users, 
  Package, 
  FileText, 
  MessageSquareText, 
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
  Settings2,
  Layers,
  Radio,
  Zap,
  Clock,
  Activity,
  ArrowRight,
  Tag
} from 'lucide-vue-next';
import { 
  obtenerEstadoSincronizacion, 
  forzarSincronizacionCatalogo, 
  sincronizarCatalogoDelta,
  type SyncStatusResponse,
  type SyncCatalogoResponse
} from '@/api/catalogo';

interface CategoryNode {
  id: string;
  name: string;
  description: string;
  padre_id?: string | null;
  atributos_dinamicos?: string[];
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

interface CatalogCategory {
  id: string;
  nombre: string;
  descripcion?: string;
  padre_id?: string | null;
  atributos_dinamicos?: string[];
  activo?: boolean;
}

interface PendingImage {
  name: string;
  dataUrl: string;
  size: number;
}

// Control de Pestañas Principales en Admin
const activeAdminTab = ref<'productos' | 'categorias' | 'precios' | 'promociones' | 'combos' | 'kpis' | 'sincronizacion' | 'resenas'>('productos');

// ============================================================================
// RF-08: SINCRONIZACIÓN MULTICANAL (WEB <-> POS)
// ============================================================================
const syncHubStatus = ref<SyncStatusResponse | null>(null);
const isLoadingSyncStatus = ref(false);
const isForcingSync = ref(false);
const deltaTestResult = ref<SyncCatalogoResponse | null>(null);
const isLoadingDeltaTest = ref(false);
const simulatedProductId = ref('');
const simulatedPrice = ref<number>(299.00);
const isBroadcastingPrice = ref(false);

async function loadSyncStatus() {
  isLoadingSyncStatus.value = true;
  try {
    syncHubStatus.value = await obtenerEstadoSincronizacion();
    if (!simulatedProductId.value && productsList.value.length > 0) {
      simulatedProductId.value = productsList.value[0].id;
      simulatedPrice.value = productsList.value[0].precio ? Number(productsList.value[0].precio) : 299.00;
    }
  } catch (err: any) {
    console.error('Error al obtener estado de sincronización:', err);
  } finally {
    isLoadingSyncStatus.value = false;
  }
}

async function triggerForceGlobalSync() {
  isForcingSync.value = true;
  try {
    const res = await forzarSincronizacionCatalogo();
    showFeedback(`¡Sincronización global emitida! ${res.suscriptores_notificados} terminales POS notificadas con ${res.total_productos} productos.`);
    await loadSyncStatus();
  } catch (err: any) {
    showFeedback(err.response?.data?.detail || 'Error al emitir sincronización masiva.', 'error');
  } finally {
    isForcingSync.value = false;
  }
}

async function runDeltaTest(all = false) {
  isLoadingDeltaTest.value = true;
  try {
    const sinceDate = all ? undefined : new Date(Date.now() - 3600 * 1000 * 24).toISOString();
    deltaTestResult.value = await sincronizarCatalogoDelta(sinceDate);
    showFeedback(`Prueba Delta ejecutada: ${deltaTestResult.value.items.length} productos detectados en el lote.`);
  } catch (err: any) {
    showFeedback('Error al consultar endpoint delta de sincronización.', 'error');
  } finally {
    isLoadingDeltaTest.value = false;
  }
}

function onSelectSimulatedProduct(prodId: string) {
  simulatedProductId.value = prodId;
  const p = productsList.value.find(item => item.id === prodId);
  if (p && p.precio) {
    simulatedPrice.value = Number(p.precio);
  }
}

async function applySimulatedPriceAndBroadcast() {
  if (!simulatedProductId.value) {
    showFeedback('Selecciona un producto para actualizar su precio.', 'error');
    return;
  }
  isBroadcastingPrice.value = true;
  try {
    const targetProd = productsList.value.find(p => p.id === simulatedProductId.value);
    await apiClient.patch(`/api/v1/catalogo/productos/${simulatedProductId.value}`, {
      precio: Number(simulatedPrice.value)
    });
    if (targetProd) {
      targetProd.precio = Number(simulatedPrice.value);
    }
    showFeedback(`Precio de "${targetProd?.nombre || simulatedProductId.value}" actualizado a BOB ${Number(simulatedPrice.value).toFixed(2)}. Evento SSE transmitido a POS en tiempo real.`);
    await loadSyncStatus();
  } catch (err: any) {
    showFeedback(err.response?.data?.detail || 'Error al actualizar y propagar precio.', 'error');
  } finally {
    isBroadcastingPrice.value = false;
  }
}

// ============================================================================
// HISTORIA KAN-17 / RF-01: GESTIÓN DE PRODUCTOS Y CICLO DE VIDA
// ============================================================================
const productsList = ref<Producto[]>([]);
const isLoadingProducts = ref(false);
const searchProductQuery = ref('');
const statusFilter = ref<string>('todos');
const currentPage = ref(1);
const itemsPerPage = ref(6);

// Modal para KAN-19 / RF-03: Galería Visual y Multimedia
const selectedMultimediaProduct = ref<Producto | null>(null);
const expandedPriceProductId = ref<string | null>(null);

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
const actionFeedback = ref<{ type: 'success' | 'error'; message: string } | null>(null);
function showFeedback(message: string, type: 'success' | 'error' = 'success') {
  actionFeedback.value = { type, message };
  setTimeout(() => {
    actionFeedback.value = null;
  }, 4500);
}

// Cargar listado de productos desde la API (KAN-306 / KAN-291)
async function loadProductsList() {
  isLoadingProducts.value = true;
  try {
    const res = await apiClient.get('/api/v1/catalogo/productos');
    const data = res.data.productos || res.data || [];
    productsList.value = Array.isArray(data) ? data : [];
  } catch (err: any) {
    console.error('Error cargando catálogo de productos:', err);
    showFeedback('No se pudo cargar la lista de productos del catálogo.', 'error');
  } finally {
    isLoadingProducts.value = false;
  }
}

// Cambio rápido de ciclo de vida (KAN-291: publicado, borrador, inactivo, descontinuado)
async function quickChangeStatus(prod: Producto, nuevoEstado: string) {
  try {
    await apiClient.patch(`/api/v1/catalogo/productos/${prod.id}`, { estado: nuevoEstado });
    prod.estado = nuevoEstado;
    showFeedback(`El estado de "${prod.nombre}" ahora es "${nuevoEstado.toUpperCase()}".`);
  } catch (err: any) {
    showFeedback(err.response?.data?.detail || err.response?.data?.error || 'Error al cambiar estado del producto.', 'error');
  }
}

const editProductAttributeFields = ref<AttributeField[]>([]);

// Opciones de categorías ordenadas con ruta jerárquica padre > hijo
const hierarchicalCategoryOptions = computed(() => {
  const map = new Map<string, CatalogCategory>();
  catalogCategories.value.forEach(c => map.set(c.id, c));

  function getBreadcrumb(cat: CatalogCategory): string {
    const parts = [cat.nombre];
    let curr = cat;
    let depth = 0;
    while (curr.padre_id && map.has(curr.padre_id) && depth < 5) {
      curr = map.get(curr.padre_id)!;
      parts.unshift(curr.nombre);
      depth++;
    }
    return parts.join(' > ');
  }

  return catalogCategories.value.map(c => ({
    id: c.id,
    nombre: c.nombre,
    breadcrumb: getBreadcrumb(c),
    atributos_dinamicos: c.atributos_dinamicos || []
  })).sort((a, b) => a.breadcrumb.localeCompare(b.breadcrumb));
});

function loadAttributesForEdit(categoryId: string, existingAttributes: Record<string, any> = {}) {
  const category = catalogCategories.value.find(c => c.id === categoryId);
  const fields: AttributeField[] = [];
  const processedLabels = new Set<string>();

  if (category?.atributos_dinamicos && category.atributos_dinamicos.length > 0) {
    category.atributos_dinamicos.forEach((attr, idx) => {
      processedLabels.add(attr.toLowerCase());
      fields.push({
        id: `edit-dyn-${idx}-${attr}`,
        label: attr,
        type: 'text',
        value: String(existingAttributes[attr] ?? '')
      });
    });
  } else {
    const templateKey = category?.nombre.toLowerCase().includes('laptop') ? 'laptops'
      : category?.nombre.toLowerCase().includes('monitor') ? 'monitors'
      : category?.nombre.toLowerCase().includes('audio') ? 'audio-video'
      : category?.nombre.toLowerCase().includes('teclado') || category?.nombre.toLowerCase().includes('mouse') ? 'keyboards-mice'
      : category?.nombre.toLowerCase().includes('red') ? 'networking'
      : '';
    const template = attributeTemplates[templateKey] || [];
    template.forEach(f => {
      processedLabels.add(f.label.toLowerCase());
      fields.push({
        ...f,
        value: String(existingAttributes[f.label] ?? '')
      });
    });
  }

  Object.entries(existingAttributes).forEach(([key, val]) => {
    if (!processedLabels.has(key.toLowerCase())) {
      fields.push({
        id: `edit-cust-${key}`,
        label: key,
        type: 'text',
        value: String(val ?? ''),
        custom: true
      });
    }
  });

  editProductAttributeFields.value = fields;
}

function onEditCategoryChange(newCatId: string) {
  if (!editingProduct.value) return;
  editingProduct.value.categoria_id = newCatId;
  const currentValues = editProductAttributeFields.value.reduce<Record<string, any>>((acc, curr) => {
    if (curr.label.trim()) acc[curr.label.trim()] = curr.value;
    return acc;
  }, {});
  loadAttributesForEdit(newCatId, currentValues);
}

function addCustomAttributeToEdit() {
  editProductAttributeFields.value.push({
    id: `custom-edit-${Date.now()}`,
    label: 'Nueva propiedad',
    type: 'text',
    value: '',
    custom: true
  });
}

function removeAttributeFromEdit(fieldId: string) {
  editProductAttributeFields.value = editProductAttributeFields.value.filter(f => f.id !== fieldId);
}

// Abrir modal de edición reactiva con jerarquía y atributos (KAN-307)
function openEditModalProduct(prod: Producto) {
  if (catalogCategories.value.length === 0) {
    loadCatalogCategories();
  }
  const initialCatId = prod.categoria_id || prod.categorias?.id || catalogCategories.value[0]?.id || '';
  editingProduct.value = {
    id: prod.id,
    sku: prod.sku,
    nombre: prod.nombre,
    marca: prod.marca || '',
    descripcion: prod.descripcion || '',
    categoria_id: initialCatId,
    precio: prod.precio || 0,
    precio_costo: (prod as any).precio_costo || Math.round((prod.precio || 0) * 0.7),
    estado: prod.estado || 'publicado'
  };

  const existingAttrs = prod.variantes?.[0]?.atributos || {};
  loadAttributesForEdit(initialCatId, existingAttrs);

  editFormError.value = '';
  isEditModalOpen.value = true;
}

// Guardar cambios de edición incluyendo categoría jerárquica y atributos
async function submitEditProduct() {
  if (!editingProduct.value) return;
  if (!editingProduct.value.sku.trim() || !editingProduct.value.nombre.trim()) {
    editFormError.value = 'El SKU y el Nombre son campos obligatorios.';
    return;
  }
  isSavingEdit.value = true;
  editFormError.value = '';

  const attributes = editProductAttributeFields.value.reduce<Record<string, string>>((result, field) => {
    if (field.label.trim()) result[field.label.trim()] = field.value;
    return result;
  }, {});

  try {
    const res = await apiClient.patch(`/api/v1/catalogo/productos/${editingProduct.value.id}`, {
      nombre: editingProduct.value.nombre.trim(),
      marca: editingProduct.value.marca.trim() || null,
      descripcion: editingProduct.value.descripcion.trim() || null,
      categoria_id: editingProduct.value.categoria_id || null,
      precio: Number(editingProduct.value.precio) || 0,
      estado: editingProduct.value.estado,
      atributos: attributes
    });

    await loadProductsList();
    isEditModalOpen.value = false;
    showFeedback('Producto y jerarquía actualizados exitosamente.');
  } catch (err: any) {
    editFormError.value = err.response?.data?.detail || err.response?.data?.error || 'Error al guardar los cambios del producto.';
  } finally {
    isSavingEdit.value = false;
  }
}

// Eliminar producto con confirmación (KAN-291)
async function confirmDeleteProduct() {
  if (!productToDelete.value) return;
  isDeletingProduct.value = true;
  try {
    await apiClient.delete(`/api/v1/catalogo/productos/${productToDelete.value.id}`);
    productsList.value = productsList.value.filter(p => p.id !== productToDelete.value?.id);
    showFeedback(`Producto "${productToDelete.value.nombre}" eliminado del catálogo.`);
    productToDelete.value = null;
  } catch (err: any) {
    showFeedback(err.response?.data?.detail || err.response?.data?.error || 'Error al eliminar producto.', 'error');
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
      prod.categorias?.id === selectedCategoryFilter.value;

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

const categories = ref<CategoryNode[]>([]);
const expandedCategoryIds = ref(new Set<string>());

// Estados para Crear Nueva Categoría
const isCreateCategoryModalOpen = ref(false);
const isSavingCategory = ref(false);
const categoryFormError = ref('');
const newCategoryName = ref('');
const newCategoryParentId = ref<string>('');
const newCategoryDescription = ref('');
const newCategoryAttributeInput = ref('');
const newCategoryAttributes = ref<string[]>([]);

// Estados para Editar Categoría Existente
const isEditCategoryModalOpen = ref(false);
const isUpdatingCategory = ref(false);
const editCategoryFormError = ref('');
const editingCategory = ref<CategoryNode | null>(null);
const editingName = ref('');
const editingDescription = ref('');
const editingParentId = ref<string>('');
const editingAttributeInput = ref('');
const editingAttributes = ref<string[]>([]);
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

function buildCategoryTree(rawCategories: CatalogCategory[]): CategoryNode[] {
  const map = new Map<string, CategoryNode>();
  const roots: CategoryNode[] = [];

  rawCategories.forEach((cat) => {
    map.set(cat.id, {
      id: cat.id,
      name: cat.nombre,
      description: cat.descripcion || '',
      padre_id: cat.padre_id || null,
      atributos_dinamicos: cat.atributos_dinamicos || [],
      children: []
    });
  });

  rawCategories.forEach((cat) => {
    const node = map.get(cat.id);
    if (!node) return;
    if (cat.padre_id && map.has(cat.padre_id) && cat.padre_id !== cat.id) {
      map.get(cat.padre_id)!.children!.push(node);
    } else {
      roots.push(node);
    }
  });

  return roots;
}

function openCreateCategoryModal() {
  newCategoryName.value = '';
  newCategoryParentId.value = '';
  newCategoryDescription.value = '';
  newCategoryAttributeInput.value = '';
  newCategoryAttributes.value = [];
  categoryFormError.value = '';
  isCreateCategoryModalOpen.value = true;
}

function addCategoryAttribute() {
  const val = newCategoryAttributeInput.value.trim();
  if (val && !newCategoryAttributes.value.includes(val)) {
    newCategoryAttributes.value.push(val);
    newCategoryAttributeInput.value = '';
  }
}

function removeCategoryAttribute(index: number) {
  newCategoryAttributes.value.splice(index, 1);
}

async function saveNewCategory() {
  if (!newCategoryName.value.trim()) {
    categoryFormError.value = 'El nombre de la categoría es obligatorio.';
    return;
  }
  isSavingCategory.value = true;
  categoryFormError.value = '';
  try {
    const payload = {
      nombre: newCategoryName.value.trim(),
      descripcion: newCategoryDescription.value.trim() || null,
      padre_id: newCategoryParentId.value ? newCategoryParentId.value : null,
      atributos_dinamicos: newCategoryAttributes.value
    };
    const res = await apiClient.post('/api/v1/catalogo/categorias', payload);
    await loadCatalogCategories();
    if (newCategoryParentId.value) {
      expandedCategoryIds.value.add(newCategoryParentId.value);
    }
    isCreateCategoryModalOpen.value = false;
    showFeedback(`Categoría "${res.data.nombre || newCategoryName.value}" creada con éxito.`);
  } catch (err: any) {
    categoryFormError.value = err.response?.data?.detail || 'No se pudo crear la categoría.';
  } finally {
    isSavingCategory.value = false;
  }
}

function openEditModal(category: CategoryNode) {
  editingCategory.value = category;
  editingName.value = category.name;
  editingDescription.value = category.description;
  editingParentId.value = category.padre_id || '';
  editingAttributes.value = [...(category.atributos_dinamicos || [])];
  editingAttributeInput.value = '';
  editCategoryFormError.value = '';
  isEditCategoryModalOpen.value = true;
}

function addEditCategoryAttribute() {
  const val = editingAttributeInput.value.trim();
  if (val && !editingAttributes.value.includes(val)) {
    editingAttributes.value.push(val);
    editingAttributeInput.value = '';
  }
}

function removeEditCategoryAttribute(index: number) {
  editingAttributes.value.splice(index, 1);
}

async function saveEditedCategory() {
  if (!editingCategory.value || !editingName.value.trim()) {
    editCategoryFormError.value = 'El nombre no puede estar vacío.';
    return;
  }
  isUpdatingCategory.value = true;
  editCategoryFormError.value = '';
  try {
    const payload = {
      nombre: editingName.value.trim(),
      descripcion: editingDescription.value.trim() || null,
      padre_id: editingParentId.value ? editingParentId.value : null,
      atributos_dinamicos: editingAttributes.value
    };
    await apiClient.put(`/api/v1/catalogo/categorias/${editingCategory.value.id}`, payload);
    await loadCatalogCategories();
    isEditCategoryModalOpen.value = false;
    showFeedback(`Categoría "${editingName.value}" actualizada con éxito.`);
  } catch (err: any) {
    editCategoryFormError.value = err.response?.data?.detail || 'No se pudo actualizar la categoría.';
  } finally {
    isUpdatingCategory.value = false;
  }
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
    const response = await apiClient.get<CatalogCategory[]>('/api/v1/catalogo/categorias');
    const cats = Array.isArray(response.data) ? response.data : [];
    catalogCategories.value = cats.length > 0 ? cats : FALLBACK_CATEGORIES;
    categories.value = buildCategoryTree(catalogCategories.value);
    if (!selectedProductCategory.value && catalogCategories.value.length > 0) {
      selectedProductCategory.value = catalogCategories.value[0].id;
    }
  } catch (err) {
    console.warn('Aviso cargando categorías de Supabase, usando catálogo base:', err);
    catalogCategories.value = FALLBACK_CATEGORIES;
    categories.value = buildCategoryTree(FALLBACK_CATEGORIES);
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

  // Si la categoría tiene atributos dinámicos configurados, utilizarlos prioritariamente
  if (category?.atributos_dinamicos && category.atributos_dinamicos.length > 0) {
    productAttributeFields.value = category.atributos_dinamicos.map((attr, idx) => ({
      id: `dyn-${idx}-${attr}`,
      label: attr,
      type: 'text' as const,
      value: ''
    }));
    return;
  }

  // Plantillas de respaldo por coincidencia de nombre
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

onMounted(() => {
  loadCatalogCategories();
  loadProductsList();
});
const sucursales = ref([
  {
    id: 'suc-central',
    nombre: 'Sucursal Central - La Paz',
    precios: {
      web: 'Lista Web Retail',
      pos: 'Lista POS Retail',
      b2b: 'Lista B2B Corporativa'
    }
  },
  {
    id: 'suc-sur',
    nombre: 'Sucursal Sur - La Paz',
    precios: {
      web: 'Lista Web Retail',
      pos: 'Lista POS Retail',
      b2b: 'Lista B2B Corporativa'
    }
  },
  {
    id: 'suc-calacoto',
    nombre: 'Sucursal Calacoto',
    precios: {
      web: 'Lista Web Retail',
      pos: 'Lista POS Retail',
      b2b: 'Lista B2B Corporativa'
    }
  }
]);

const listasPrecios = [
  'Lista Web Retail',
  'Lista POS Retail',
  'Lista B2B Corporativa',
  'Lista Promocional'
];

const tipoCambioUsd = 6.96;

const preciosDual = ref([
  {
    id: 'precio-001',
    producto: 'Monitor LG UltraGear 27"',
    lista: 'Lista Web Retail',
    precioBob: 8999.00
  },
  {
    id: 'precio-002',
    producto: 'Laptop Dell XPS 15',
    lista: 'Lista Web Retail',
    precioBob: 12500.00
  },
  {
    id: 'precio-003',
    producto: 'Laptop Dell XPS 15',
    lista: 'Lista B2B Corporativa',
    precioBob: 11200.00
  },
  {
    id: 'precio-004',
    producto: 'Monitor LG UltraGear 27"',
    lista: 'Lista POS Retail',
    precioBob: 8799.00
  }
]);

function convertirAUsd(precioBob: number) {
  return precioBob / tipoCambioUsd;
}

function guardarAsignaciones() {
  actionFeedback.value = {
    message: 'Matriz de asignación de listas de precios por sucursal guardada exitosamente.',
    type: 'success'
  };
  setTimeout(() => {
    actionFeedback.value = null;
  }, 4000);
}
</script>

<template>
  <div class="space-y-6">
    <!-- Banner de Notificación / Feedback en Tiempo Real -->
    <div
      v-if="actionFeedback"
      :class="[
        'p-3.5 rounded-xl border flex items-center justify-between text-xs font-semibold animate-in fade-in slide-in-from-top-2 shadow-sm',
        actionFeedback.type === 'success'
          ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300'
          : 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300'
      ]"
    >
      <div class="flex items-center gap-2.5">
        <CheckCircle2 v-if="actionFeedback.type === 'success'" class="w-4 h-4 text-emerald-600 shrink-0" />
        <AlertTriangle v-else class="w-4 h-4 text-rose-600 shrink-0" />
        <span>{{ actionFeedback.message }}</span>
      </div>
      <button @click="actionFeedback = null" class="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5">
        <X class="w-3.5 h-3.5" />
      </button>
    </div>

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
      <div class="flex items-center gap-2">
        <button @click="loadProductsList" :disabled="isLoadingProducts" class="p-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-semibold flex items-center gap-1.5" title="Recargar datos">
          <RefreshCw :class="['w-3.5 h-3.5', isLoadingProducts ? 'animate-spin' : '']" />
          <span class="hidden sm:inline">Actualizar</span>
        </button>
        <HasRole :roles="['administrador', 'gerente_comercial']">
          <button @click="openProductModal" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-sm flex items-center gap-1.5">
            <Plus class="w-4 h-4" />
            <span>Nuevo Producto</span>
          </button>
        </HasRole>
      </div>
    </div>

    <!-- Selector de Pestañas del Panel de Administración -->
    <div class="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2 overflow-x-auto">
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
        <span>Categorías</span>
      </button>

      <button
        @click="activeAdminTab = 'precios'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'precios'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <DollarSign class="w-4 h-4" />
        <span>Listas de Precios & Tarifas (RF-04)</span>
      </button>

      <button
        @click="activeAdminTab = 'combos'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'combos'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <Sparkles class="w-4 h-4 text-amber-400" />
        <span>Combos & Paquetes (US-18)</span>
      </button>

      <button
        @click="activeAdminTab = 'promociones'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'promociones'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <Tag class="w-4 h-4" />
        <span>Promociones y Cupones (RF-17)</span>
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
        @click="activeAdminTab = 'sincronizacion'; loadSyncStatus();"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'sincronizacion'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <Radio class="w-4 h-4 text-cyan-400" />
        <span>Sincronización Multicanal (RF-08)</span>
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
      </button>

      <button
        @click="activeAdminTab = 'resenas'"
        :class="[
          'flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all shrink-0',
          activeAdminTab === 'resenas'
            ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
        ]"
      >
        <MessageSquareText class="w-4 h-4 text-purple-400" />
        <span>Moderación de Reseñas</span>
      </button>
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA 1: GESTIÓN DE PRODUCTOS Y MULTIMEDIA (RF-01 / RF-03)          -->
    <!-- ===================================================================== -->
    <div v-if="activeAdminTab === 'productos'" class="space-y-6">
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
              Catálogo de Productos y Estado de Ciclo de Vida
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
              <template v-for="prod in paginatedProducts" :key="prod.id">
              <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
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

                <!-- Precio -->
                <td class="p-3.5">
                  <span class="font-bold text-slate-900 dark:text-white block">
                    BOB {{ formatPrice(prod.precio || 0) }}
                  </span>
                  <span v-if="(prod as any).precio_costo" class="text-[10px] text-slate-400 block">
                    Costo: BOB {{ formatPrice((prod as any).precio_costo) }}
                  </span>
                  <HasRole :roles="['administrador', 'gerente_comercial']">
                    <button
                      type="button"
                      :aria-expanded="expandedPriceProductId === prod.id"
                      class="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
                      @click="expandedPriceProductId = expandedPriceProductId === prod.id ? null : prod.id"
                    >
                      <DollarSign class="w-3 h-3" />
                      {{ expandedPriceProductId === prod.id ? 'Ocultar precios' : 'Precios diferenciados' }}
                    </button>
                  </HasRole>
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
              <tr v-if="expandedPriceProductId === prod.id">
                <td colspan="6" class="px-3.5 pb-4">
                  <ProductPriceMatrix
                    :product="prod"
                    @saved="showFeedback('Precios diferenciados guardados para ' + prod.nombre + '.')"
                  />
                </td>
              </tr>
              </template>
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
          <div class="flex items-center gap-3">
            <span class="text-[11px] font-semibold text-slate-500 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg">
              {{ categories.length }} categorías principales
            </span>
            <HasRole :roles="['administrador', 'gerente_comercial']">
              <button
                type="button"
                @click="openCreateCategoryModal"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm transition-colors"
              >
                <Plus class="w-3.5 h-3.5" />
                Nueva Categoría
              </button>
            </HasRole>
          </div>
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
              <div v-if="category.atributos_dinamicos && category.atributos_dinamicos.length > 0" class="flex items-center gap-1.5 flex-wrap mt-1">
                <span
                  v-for="attr in category.atributos_dinamicos"
                  :key="attr"
                  class="text-[10px] font-semibold bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded border border-blue-200/60 dark:border-blue-800/60"
                >
                  {{ attr }}
                </span>
              </div>
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
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA: LISTAS DE PRECIOS DIFERENCIADAS (RF-04 / US-04)               -->
    <!-- ===================================================================== -->
    <div v-if="activeAdminTab === 'precios'" class="space-y-6">
      <PriceMatrixManager />
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA: PROMOCIONES Y CUPONES (RF-17)                                -->
    <!-- ===================================================================== -->
    <div v-if="activeAdminTab === 'promociones'" class="space-y-6">
      <PromotionsManager />
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
              <FileText class="w-4 h-4 text-blue-500" /> Órdenes y Ventas Recientes
            </h3>
            <router-link to="/admin/ventas" class="text-xs text-blue-600 hover:underline font-semibold">Ver historial</router-link>
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
            <span>Alertas de Quiebre de Stock</span>
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
    <!-- PESTAÑA: SINCRONIZACIÓN MULTICANAL WEB <-> POS (RF-08)                 -->
    <!-- ===================================================================== -->
    <div v-show="activeAdminTab === 'sincronizacion'" class="space-y-6">
      <!-- Tarjetas de Estado del Hub de Sincronización (RF-08) -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- Tarjeta 1: Canal SSE -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Canal SSE en Tiempo Real</span>
            <span class="p-2 bg-cyan-50 dark:bg-cyan-950/40 text-cyan-600 dark:text-cyan-400 rounded-lg">
              <Radio class="w-4 h-4 animate-pulse" />
            </span>
          </div>
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></span>
            <span class="text-lg font-bold text-slate-900 dark:text-white">
              {{ syncHubStatus?.suscriptores_activos ?? 0 }} POS Conectados
            </span>
          </div>
          <p class="text-[11px] text-slate-500">
            Streaming activo en <code class="text-cyan-600 dark:text-cyan-400 font-mono">/api/v1/catalogo/sync-events</code>
          </p>
        </div>

        <!-- Tarjeta 2: Total Productos Catálogo -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Productos en Catálogo</span>
            <span class="p-2 bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 rounded-lg">
              <Package class="w-4 h-4" />
            </span>
          </div>
          <div class="text-2xl font-black text-slate-900 dark:text-white">
            {{ syncHubStatus?.total_productos ?? productsList.length }} SKUs
          </div>
          <p class="text-[11px] text-emerald-600 font-semibold flex items-center gap-1">
            <CheckCircle2 class="w-3.5 h-3.5" /> Consistencia omnicanal asegurada
          </p>
        </div>

        <!-- Tarjeta 3: Marca Temporal Delta -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Última Mutación Delta</span>
            <span class="p-2 bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 rounded-lg">
              <Clock class="w-4 h-4" />
            </span>
          </div>
          <div class="text-xs font-mono font-bold text-slate-800 dark:text-slate-200 truncate" :title="syncHubStatus?.ultima_sincronizacion || 'Sin registro'">
            {{ syncHubStatus?.ultima_sincronizacion ? new Date(syncHubStatus.ultima_sincronizacion).toLocaleString('es-BO') : 'Sincronizado' }}
          </div>
          <p class="text-[11px] text-slate-400">
            Filtro diferencial por <code class="text-purple-600 dark:text-purple-400 font-mono">updated_at</code>
          </p>
        </div>

        <!-- Tarjeta 4: Estado Operativo -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-2">
          <div class="flex justify-between items-center text-slate-500">
            <span class="text-xs font-semibold">Estado del Hub</span>
            <span class="p-2 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 rounded-lg">
              <Activity class="w-4 h-4" />
            </span>
          </div>
          <div class="text-lg font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">
            {{ syncHubStatus?.estado ?? 'Operativo' }}
          </div>
          <p class="text-[11px] text-slate-500">
            Gateway proxy SSE sin bufferización
          </p>
        </div>
      </div>

      <!-- Panel de Acciones y Simulador -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Control Global & Disparo Masivo -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div class="flex items-center gap-2.5">
              <span class="p-2 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400">
                <Zap class="w-4 h-4" />
              </span>
              <div>
                <h3 class="text-sm font-bold text-slate-900 dark:text-white">Control Global de Sincronización</h3>
                <p class="text-xs text-slate-500">Emite órdenes de recarga o consulta lotes delta</p>
              </div>
            </div>
            <button
              @click="loadSyncStatus"
              :disabled="isLoadingSyncStatus"
              class="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg"
              title="Refrescar estado"
            >
              <RefreshCw :class="['w-4 h-4', isLoadingSyncStatus ? 'animate-spin' : '']" />
            </button>
          </div>

          <div class="space-y-3">
            <p class="text-xs text-slate-600 dark:text-slate-300">
              Al emitir una <strong>Sincronización Global</strong>, el microservicio envía un broadcast SSE inmediato a todas las terminales POS conectadas, forzando la hidratación de precios y catálogo sin reiniciar sesión.
            </p>

            <div class="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                @click="triggerForceGlobalSync"
                :disabled="isForcingSync"
                class="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 text-white text-xs font-bold shadow-md shadow-blue-500/20 transition-all flex items-center gap-2 cursor-pointer"
              >
                <RefreshCw :class="['w-4 h-4', isForcingSync ? 'animate-spin' : '']" />
                <span>{{ isForcingSync ? 'Transmitiendo a POS...' : 'Forzar Sincronización a POS' }}</span>
              </button>

              <button
                type="button"
                @click="runDeltaTest(false)"
                :disabled="isLoadingDeltaTest"
                class="px-4 py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold transition-all flex items-center gap-2 cursor-pointer"
              >
                <Layers class="w-4 h-4" />
                <span>{{ isLoadingDeltaTest ? 'Consultando Delta...' : 'Inspeccionar Delta (/sync-catalogo)' }}</span>
              </button>
            </div>
          </div>

          <!-- Resultado del Test Delta si se ejecutó -->
          <div v-if="deltaTestResult" class="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs space-y-1.5 font-mono">
            <div class="flex justify-between text-slate-600 dark:text-slate-300 font-bold">
              <span>Respuesta Delta: {{ deltaTestResult.items.length }} ítems</span>
              <span>Servidor: {{ new Date(deltaTestResult.servidor_timestamp).toLocaleTimeString() }}</span>
            </div>
            <div class="max-h-28 overflow-y-auto space-y-1 text-[11px] text-slate-500">
              <div v-for="item in deltaTestResult.items.slice(0, 5)" :key="item.id" class="flex justify-between">
                <span>{{ item.sku }} - {{ item.nombre }}</span>
                <span class="font-bold text-slate-700 dark:text-slate-200">BOB {{ item.precio_referencia }} [{{ item.accion }}]</span>
              </div>
              <div v-if="deltaTestResult.items.length > 5" class="text-center text-[10px] text-blue-500">
                + {{ deltaTestResult.items.length - 5 }} ítems adicionales en el lote...
              </div>
            </div>
          </div>
        </div>

        <!-- Simulador Interactivo: Cambio de Precio Reactivo Web -> POS -->
        <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div class="flex items-center gap-2.5 border-b border-slate-100 dark:border-slate-800 pb-3">
            <span class="p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400">
              <DollarSign class="w-4 h-4" />
            </span>
            <div>
              <h3 class="text-sm font-bold text-slate-900 dark:text-white">Simulador de Propagación Web &rarr; POS</h3>
              <p class="text-xs text-slate-500">Modifica un precio administrativo y observa la emisión SSE</p>
            </div>
          </div>

          <form @submit.prevent="applySimulatedPriceAndBroadcast" class="space-y-3.5">
            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                Seleccionar Producto del Catálogo:
              </label>
              <select
                :value="simulatedProductId"
                @change="onSelectSimulatedProduct(($event.target as HTMLSelectElement).value)"
                class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
              >
                <option v-for="p in productsList" :key="p.id" :value="p.id">
                  {{ p.sku }} — {{ p.nombre }} (Actual: BOB {{ p.precio ?? 0 }})
                </option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                Nuevo Precio de Venta (BOB):
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 font-bold">BOB</span>
                <input
                  v-model.number="simulatedPrice"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  class="w-full pl-12 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500 font-bold text-slate-900 dark:text-white"
                />
              </div>
            </div>

            <button
              type="submit"
              :disabled="isBroadcastingPrice"
              class="w-full py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:scale-98 text-white text-xs font-bold shadow-md shadow-emerald-500/20 transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <Zap :class="['w-4 h-4', isBroadcastingPrice ? 'animate-bounce' : '']" />
              <span>{{ isBroadcastingPrice ? 'Propagando a POS...' : 'Propagar Precio a POS en Tiempo Real' }}</span>
            </button>
          </form>
        </div>
      </div>

      <!-- Feed / Log de Eventos de Sincronización en Tiempo Real -->
      <div class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div class="flex items-center gap-2">
            <Radio class="w-4 h-4 text-cyan-500" />
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">Auditoría de Eventos de Sincronización Multicanal</h3>
          </div>
          <span class="text-xs text-slate-400">
            {{ syncHubStatus?.eventos_recientes.length ?? 0 }} eventos registrados en el ring buffer
          </span>
        </div>

        <div v-if="!syncHubStatus || syncHubStatus.eventos_recientes.length === 0" class="py-8 text-center text-xs text-slate-400">
          No hay eventos recientes en el buffer. Modifica un producto o pulsa "Forzar Sincronización a POS" para generar eventos.
        </div>

        <div v-else class="divide-y divide-slate-100 dark:divide-slate-800">
          <div
            v-for="(ev, idx) in syncHubStatus.eventos_recientes"
            :key="idx"
            class="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs"
          >
            <div class="flex items-center gap-2.5">
              <span
                :class="[
                  'px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider',
                  ev.tipo === 'producto_creado'
                    ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                    : ev.tipo === 'producto_actualizado'
                    ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300'
                    : ev.tipo === 'sincronizacion_masiva'
                    ? 'bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300'
                    : 'bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300'
                ]"
              >
                {{ ev.tipo }}
              </span>
              <span class="font-bold text-slate-800 dark:text-slate-100">
                {{ ev.nombre || ev.mensaje || ev.sku || 'Evento Multicanal' }}
              </span>
              <span v-if="ev.sku" class="text-slate-400 font-mono text-[11px]">
                [{{ ev.sku }}]
              </span>
              <span v-if="ev.precio !== undefined" class="text-emerald-600 font-bold">
                BOB {{ ev.precio }}
              </span>
            </div>

            <div class="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
              <Clock class="w-3.5 h-3.5 text-slate-400" />
              <span>{{ new Date(ev.emitido_en).toLocaleTimeString('es-BO') }}</span>
              <span class="text-[10px] text-slate-500 hidden sm:inline">({{ new Date(ev.emitido_en).toLocaleDateString('es-BO') }})</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- PESTAÑA: COMBOS Y PAQUETES COMERCIALES (US-18 / RF-18)                 -->
    <!-- ===================================================================== -->
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
      v-if="isEditCategoryModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      @click.self="isEditCategoryModalOpen = false"
    >
      <div class="w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden my-8">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-800/40">
          <div>
            <h2 class="text-base font-extrabold text-slate-900 dark:text-white">Editar Categoría</h2>
            <p class="text-xs text-slate-500">Actualiza jerarquía y atributos de tipificación</p>
          </div>
          <button
            type="button"
            class="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-700/60 transition-colors"
            @click="isEditCategoryModalOpen = false"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <form class="p-6 space-y-4" @submit.prevent="saveEditedCategory">
          <div v-if="editCategoryFormError" class="p-3 text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-600 rounded-xl font-medium">
            {{ editCategoryFormError }}
          </div>

          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Nombre de la Categoría</label>
            <input
              v-model="editingName"
              type="text"
              required
              class="w-full px-3.5 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
            />
          </div>

          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Categoría Superior / Padre</label>
            <select
              v-model="editingParentId"
              class="w-full px-3.5 py-2.5 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none"
            >
              <option value="">(Ninguna - Categoría Principal Raíz)</option>
              <option
                v-for="cat in catalogCategories.filter(c => c.id !== editingCategory?.id)"
                :key="cat.id"
                :value="cat.id"
              >
                {{ cat.nombre }}
              </option>
            </select>
          </div>

          <div class="space-y-1.5">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300">Descripción</label>
            <textarea
              v-model="editingDescription"
              rows="2"
              class="w-full px-3.5 py-2 text-sm bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none resize-none"
            />
          </div>

          <!-- Atributos Dinámicos -->
          <div class="space-y-2 pt-1 border-t border-slate-100 dark:border-slate-800">
            <label class="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between">
              <span>Atributos Dinámicos Recomendados</span>
              <span class="text-[10px] font-normal text-slate-400">Especificaciones técnicas de variantes</span>
            </label>
            
            <div class="flex gap-2">
              <input
                v-model="editingAttributeInput"
                type="text"
                placeholder="Ej. RAM, Procesador, Watts..."
                class="flex-1 px-3 py-2 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl focus:border-blue-500 outline-none"
                @keydown.enter.prevent="addEditCategoryAttribute"
              />
              <button
                type="button"
                @click="addEditCategoryAttribute"
                class="px-3 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-bold text-slate-700 dark:text-slate-200 rounded-xl transition-colors"
              >
                + Añadir
              </button>
            </div>

            <div v-if="editingAttributes.length > 0" class="flex flex-wrap gap-1.5 pt-1">
              <span
                v-for="(attr, idx) in editingAttributes"
                :key="attr"
                class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/60 rounded-lg"
              >
                {{ attr }}
                <button
                  type="button"
                  @click="removeEditCategoryAttribute(idx)"
                  class="text-blue-500 hover:text-rose-600 ml-0.5"
                >
                  <X class="w-3 h-3" />
                </button>
              </span>
            </div>
            <p v-else class="text-[11px] text-slate-400 italic">No hay atributos específicos agregados.</p>
          </div>

          <div class="flex justify-end gap-2.5 pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              class="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              @click="isEditCategoryModalOpen = false"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="isUpdatingCategory"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm transition-colors disabled:opacity-50"
            >
              <Save class="w-3.5 h-3.5" />
              {{ isUpdatingCategory ? 'Guardando...' : 'Guardar Cambios' }}
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
              Editar Producto
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
              <label class="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Categoría (Ubicación en la Jerarquía)
              </label>
              <select
                :value="editingProduct.categoria_id"
                @change="onEditCategoryChange(($event.target as HTMLSelectElement).value)"
                class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500 font-medium"
              >
                <option value="">Sin categoría asignada</option>
                <option
                  v-for="cat in hierarchicalCategoryOptions"
                  :key="cat.id"
                  :value="cat.id"
                >
                  {{ cat.breadcrumb }}
                </option>
              </select>
              <p class="text-[10px] text-slate-400 mt-0.5">Al cambiar de categoría se cargarán sus atributos técnicos correspondientes.</p>
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
            <textarea v-model="editingProduct.descripcion" rows="2" class="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500 resize-none"></textarea>
          </div>

          <!-- Atributos Dinámicos de la Jerarquía -->
          <div class="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            <div class="p-3 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800">
              <div>
                <h4 class="text-xs font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                  <SlidersHorizontal class="w-3.5 h-3.5 text-blue-600" />
                  Atributos Dinámicos de la Jerarquía
                </h4>
                <p class="text-[10px] text-slate-500 mt-0.5">Especificaciones técnicas y propiedades de la variante.</p>
              </div>
              <button
                type="button"
                @click="addCustomAttributeToEdit"
                class="px-2.5 py-1 text-[11px] font-bold text-blue-600 dark:text-blue-400 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:border-blue-400 transition-colors"
              >
                + Añadir propiedad
              </button>
            </div>

            <div class="p-3.5 space-y-2.5">
              <div v-if="editProductAttributeFields.length === 0" class="text-center py-3 text-xs text-slate-400">
                Esta categoría no tiene atributos dinámicos configurados. Puedes añadir propiedades personalizadas con el botón de arriba.
              </div>
              <div
                v-for="field in editProductAttributeFields"
                :key="field.id"
                class="grid grid-cols-1 sm:grid-cols-[140px_1fr_auto] gap-2 items-center"
              >
                <div>
                  <input
                    v-if="field.custom"
                    v-model="field.label"
                    type="text"
                    placeholder="Nombre del atributo"
                    class="w-full px-2.5 py-1.5 text-xs font-semibold bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
                  />
                  <span v-else class="text-xs font-semibold text-slate-700 dark:text-slate-300 block truncate" :title="field.label">
                    {{ field.label }}
                  </span>
                </div>

                <div class="flex-1">
                  <select
                    v-if="field.options && field.options.length > 0"
                    v-model="field.value"
                    class="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
                  >
                    <option value="">Selecciona una opción</option>
                    <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
                  </select>
                  <input
                    v-else
                    v-model="field.value"
                    :type="field.type === 'number' ? 'number' : 'text'"
                    :placeholder="`Valor para ${field.label}`"
                    class="w-full px-2.5 py-1.5 text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg outline-none focus:border-blue-500"
                  />
                </div>

                <button
                  type="button"
                  @click="removeAttributeFromEdit(field.id)"
                  class="p-1 text-slate-400 hover:text-rose-600 transition-colors"
                  title="Quitar atributo"
                >
                  <X class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
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

            <!-- Matriz de asignación de precios (KAN-298) -->
      <div
        class="bg-white dark:bg-slate-900 p-5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
      >
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div>
            <h3 class="text-sm font-bold text-slate-800 dark:text-white flex items-center gap-2">
              <Settings2 class="w-4 h-4 text-blue-500" />
              Matriz de asignación de precios
            </h3>

            <p class="text-xs text-slate-500 mt-1">
              Asigna la lista de precios correspondiente a cada sucursal y canal.
            </p>
          </div>

          
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead
              class="bg-slate-50 dark:bg-slate-800
                    text-slate-500 font-semibold"
            >
              <tr>
                <th class="p-3">Sucursal</th>
                <th class="p-3">Web</th>
                <th class="p-3">POS</th>
                <th class="p-3">B2B</th>
              </tr>
            </thead>

            <tbody
              class="divide-y divide-slate-100
                    dark:divide-slate-800"
            >
              <tr
                v-for="sucursal in sucursales"
                :key="sucursal.id"
              >
                <td class="p-3">
                  <div class="font-semibold text-slate-800 dark:text-slate-200">
                    {{ sucursal.nombre }}
                  </div>
                </td>

                <td class="p-3">
                  <select
                    v-model="sucursal.precios.web"
                    class="w-full min-w-[170px] px-2.5 py-2
                          border border-slate-200 dark:border-slate-700
                          rounded-lg bg-white dark:bg-slate-800
                          text-slate-700 dark:text-slate-200
                          text-xs focus:outline-none focus:ring-2
                          focus:ring-blue-500"
                  >
                    <option
                      v-for="lista in listasPrecios"
                      :key="`web-${sucursal.id}-${lista}`"
                      :value="lista"
                    >
                      {{ lista }}
                    </option>
                  </select>
                </td>

                <td class="p-3">
                  <select
                    v-model="sucursal.precios.pos"
                    class="w-full min-w-[170px] px-2.5 py-2
                          border border-slate-200 dark:border-slate-700
                          rounded-lg bg-white dark:bg-slate-800
                          text-slate-700 dark:text-slate-200
                          text-xs focus:outline-none focus:ring-2
                          focus:ring-blue-500"
                  >
                    <option
                      v-for="lista in listasPrecios"
                      :key="`pos-${sucursal.id}-${lista}`"
                      :value="lista"
                    >
                      {{ lista }}
                    </option>
                  </select>
                </td>

                <td class="p-3">
                  <select
                    v-model="sucursal.precios.b2b"
                    class="w-full min-w-[170px] px-2.5 py-2
                          border border-slate-200 dark:border-slate-700
                          rounded-lg bg-white dark:bg-slate-800
                          text-slate-700 dark:text-slate-200
                          text-xs focus:outline-none focus:ring-2
                          focus:ring-blue-500"
                  >
                    <option
                      v-for="lista in listasPrecios"
                      :key="`b2b-${sucursal.id}-${lista}`"
                      :value="lista"
                    >
                      {{ lista }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          class="flex items-center justify-between pt-3
                border-t border-slate-100 dark:border-slate-800"
        >
          <p class="text-[11px] text-slate-400">
            Los cambios realizados en esta vista representan la asignación
            actual de cada lista por sucursal y canal.
          </p>

          <button
            type="button"
            @click="guardarAsignaciones"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700
                  text-white text-xs font-semibold rounded-lg shadow-sm active:scale-95 transition-all"
          >
            Guardar asignaciones
          </button>
        </div>
      </div>

            <!-- Visualización de precios dual BOB / USD (KAN-299) -->
      <div
        class="bg-white dark:bg-slate-900 p-5 rounded-xl
              border border-slate-200 dark:border-slate-800
              shadow-sm space-y-4"
      >
        <div class="flex flex-col sm:flex-row justify-between
                    items-start sm:items-center gap-3">

          <div>
            <h3
              class="text-sm font-bold text-slate-800
                    dark:text-white flex items-center gap-2"
            >
              <DollarSign class="w-4 h-4 text-emerald-500" />

              Visualización de precios
            </h3>

            <p class="text-xs text-slate-500 mt-1">
              Consulta los precios en moneda nacional y su equivalente en dólares.
            </p>
          </div>

          <span
            class="px-2.5 py-1 rounded-full text-[10px]
                  font-bold bg-emerald-50 text-emerald-700
                  dark:bg-emerald-950/40 dark:text-emerald-300"
          >
            BOB / USD
          </span>
        </div>

        <!-- Tipo de cambio -->
        <div
          class="flex items-center justify-between
                px-4 py-3 rounded-lg
                bg-slate-50 dark:bg-slate-800
                border border-slate-100 dark:border-slate-700"
        >
          <span class="text-xs text-slate-500">
            Tipo de cambio referencial
          </span>

          <span class="text-sm font-bold text-slate-800 dark:text-white">
            1 USD = {{ tipoCambioUsd.toFixed(2) }} BOB
          </span>
        </div>

        <!-- Lista de precios -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">

          <div
            v-for="precio in preciosDual"
            :key="precio.id"
            class="p-4 rounded-xl
                  border border-slate-200
                  dark:border-slate-700
                  hover:shadow-sm transition"
          >
            <div class="flex justify-between items-start gap-3">

              <div>
                <p
                  class="text-sm font-bold
                        text-slate-800 dark:text-white"
                >
                  {{ precio.producto }}
                </p>

                <p class="text-[11px] text-slate-400 mt-1">
                  {{ precio.lista }}
                </p>
              </div>

              <span
                class="text-[10px] font-semibold
                      px-2 py-1 rounded-full
                      bg-blue-50 text-blue-700
                      dark:bg-blue-950/40
                      dark:text-blue-300"
              >
                Precio
              </span>
            </div>

            <div class="grid grid-cols-2 gap-3 mt-4">

              <!-- BOB -->
              <div
                class="p-3 rounded-lg
                      bg-slate-50 dark:bg-slate-800"
              >
                <p class="text-[10px] uppercase
                          text-slate-400 font-semibold">
                  Bolivianos
                </p>

                <p
                  class="text-lg font-extrabold
                        text-slate-900 dark:text-white mt-1"
                >
                  BOB
                  {{ precio.precioBob.toLocaleString('es-BO', {
                    minimumFractionDigits: 2
                  }) }}
                </p>
              </div>

              <!-- USD -->
              <div
                class="p-3 rounded-lg
                      bg-emerald-50
                      dark:bg-emerald-950/30"
              >
                <p class="text-[10px] uppercase
                          text-emerald-600
                          dark:text-emerald-400
                          font-semibold">
                  Dólares
                </p>

                <p
                  class="text-lg font-extrabold
                        text-emerald-700
                        dark:text-emerald-300 mt-1"
                >
                  USD
                  {{ convertirAUsd(precio.precioBob).toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }) }}
                </p>
              </div>

            </div>
          </div>

        </div>

        <p class="text-[10px] text-slate-400">
          El equivalente USD se calcula a partir del precio BOB utilizando
          el tipo de cambio referencial mostrado arriba.
        </p>
      </div>
    </div>
  </div>
</template>
