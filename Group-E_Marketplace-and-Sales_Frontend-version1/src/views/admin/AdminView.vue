<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import HasRole from '@/components/HasRole.vue';
import { apiClient } from '@/api/client';
import { 
  TrendingUp, 
  ShoppingBag, 
  DollarSign, 
  Users, 
  Package, 
  FileText, 
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Edit3,
  FolderTree,
  ImagePlus,
  Plus,
  Save,
  Store,
  X
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

const categories = ref<CategoryNode[]>([
  {
    id: 'electronics',
    name: 'Electrónica',
    description: 'Tecnología y dispositivos electrónicos.',
    children: [
      {
        id: 'computers',
        name: 'Computación',
        description: 'Equipos y accesorios para computación.',
        children: [
          { id: 'laptops', name: 'Laptops y PCs', description: 'Computadoras portátiles y de escritorio.' },
          { id: 'monitors', name: 'Monitores', description: 'Monitores para trabajo, diseño y gaming.' }
        ]
      },
      { id: 'audio-video', name: 'Audio y Video', description: 'Equipos de audio, video y entretenimiento.' }
    ]
  },
  {
    id: 'peripherals',
    name: 'Periféricos',
    description: 'Accesorios para mejorar tu estación de trabajo.',
    children: [
      { id: 'keyboards-mice', name: 'Teclados y Mouse', description: 'Dispositivos de entrada y controles.' },
      { id: 'networking', name: 'Redes', description: 'Conectividad, routers y accesorios de red.' }
    ]
  },
  { id: 'office', name: 'Oficina', description: 'Productos para espacios de trabajo.' }
]);

const expandedCategoryIds = ref(new Set(['electronics', 'computers', 'peripherals']));
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
const priceProducts = ref([
  { id: 'monitor-lg', name: 'Monitor LG UltraGear 27"', sku: 'MON-LG-27GP' },
  { id: 'laptop-dell', name: 'Laptop Dell XPS 15', sku: 'LAP-DELL-XPS15' },
  { id: 'keyboard-logi', name: 'Teclado Logitech MX Keys', sku: 'TEC-LOG-MXK' }
]);
const selectedPriceProduct = ref('monitor-lg');
const priceMatrix = ref<PriceMatrixRow[]>([
  { branch: 'La Paz Centro', web: 3499, pos: 3420, b2b: 3290 },
  { branch: 'Calacoto', web: 3549, pos: 3490, b2b: 3350 },
  { branch: 'Santa Cruz Equipetrol', web: 3599, pos: 3520, b2b: 3380 },
  { branch: 'Cochabamba Norte', web: 3499, pos: 3390, b2b: 3260 }
]);
const priceMatrixSavedAt = ref('');

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

function openProductModal() {
  isProductModalOpen.value = true;
  productName.value = '';
  productSku.value = '';
  productBrand.value = '';
  productDescription.value = '';
  productPrice.value = null;
  selectedProductCategory.value = '';
  productAttributeFields.value = [];
  pendingImages.value = [];
  productFormMessage.value = '';
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

async function loadCatalogCategories() {
  try {
    const response = await apiClient.get<CatalogCategory[]>('/api/v1/catalogo/categorias');
    catalogCategories.value = response.data;
  } catch {
    productFormMessage.value = 'No fue posible cargar las categorías del catálogo.';
  }
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
  } catch (error: any) {
    productFormMessage.value = error.response?.data?.detail || 'No se pudo guardar el producto en el catálogo.';
  } finally {
    isSavingProduct.value = false;
  }
}

function formatPrice(value: number) {
  return value.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function savePriceMatrix() {
  priceMatrixSavedAt.value = new Date().toLocaleTimeString('es-BO', {
    hour: '2-digit',
    minute: '2-digit'
  });
}

onMounted(loadCatalogCategories);
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
        <HasRole :roles="['administrador', 'gerente_comercial']">
          <button @click="openProductModal" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm">
            + Nuevo Producto
          </button>
        </HasRole>
      </div>
    </div>

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

    <!-- Matriz de precios por sucursal y canal -->
    <HasRole :roles="['administrador', 'gerente_comercial']">
      <section class="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div class="p-5 border-b border-slate-200 dark:border-slate-800 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div class="flex items-start gap-3">
            <span class="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400">
              <DollarSign class="w-5 h-5" />
            </span>
            <div>
              <h2 class="text-sm font-bold text-slate-900 dark:text-white">Matriz de precios</h2>
              <p class="text-xs text-slate-500 mt-1">Define precios diferenciados por sucursal y canal de venta.</p>
            </div>
          </div>
          <label class="flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
            Producto
            <select v-model="selectedPriceProduct" class="min-w-56 px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-xs outline-none focus:border-emerald-500">
              <option v-for="product in priceProducts" :key="product.id" :value="product.id">{{ product.name }}</option>
            </select>
          </label>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 p-5 border-b border-slate-100 dark:border-slate-800">
          <div class="px-4 py-3 rounded-lg bg-slate-50 dark:bg-slate-800/70">
            <span class="block text-[11px] text-slate-500">Precio mínimo</span>
            <strong class="block text-lg text-slate-900 dark:text-white mt-1">BOB {{ formatPrice(priceSummary.minimum) }}</strong>
          </div>
          <div class="px-4 py-3 rounded-lg bg-slate-50 dark:bg-slate-800/70">
            <span class="block text-[11px] text-slate-500">Precio máximo</span>
            <strong class="block text-lg text-slate-900 dark:text-white mt-1">BOB {{ formatPrice(priceSummary.maximum) }}</strong>
          </div>
          <div class="px-4 py-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/30">
            <span class="block text-[11px] text-emerald-700 dark:text-emerald-400">Promedio de matriz</span>
            <strong class="block text-lg text-emerald-800 dark:text-emerald-300 mt-1">BOB {{ formatPrice(priceSummary.average) }}</strong>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full min-w-[680px] text-left text-xs">
            <thead class="bg-slate-50 dark:bg-slate-800 text-slate-500 font-semibold">
              <tr>
                <th class="p-4">Sucursal</th>
                <th class="p-4"><span class="inline-flex items-center gap-1.5"><ShoppingBag class="w-3.5 h-3.5 text-blue-500" /> Web</span></th>
                <th class="p-4"><span class="inline-flex items-center gap-1.5"><Store class="w-3.5 h-3.5 text-emerald-500" /> POS</span></th>
                <th class="p-4"><span class="inline-flex items-center gap-1.5"><Users class="w-3.5 h-3.5 text-indigo-500" /> B2B</span></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
              <tr v-for="row in priceMatrix" :key="row.branch" class="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <th class="p-4 font-semibold text-slate-800 dark:text-slate-200">{{ row.branch }}</th>
                <td class="p-3">
                  <label class="sr-only">Precio Web en {{ row.branch }}</label>
                  <div class="flex items-center gap-1.5">
                    <span class="text-slate-400">BOB</span>
                    <input v-model.number="row.web" type="number" min="0" step="0.01" class="w-28 px-2.5 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-semibold text-slate-800 dark:text-slate-100 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20" />
                  </div>
                </td>
                <td class="p-3">
                  <label class="sr-only">Precio POS en {{ row.branch }}</label>
                  <div class="flex items-center gap-1.5">
                    <span class="text-slate-400">BOB</span>
                    <input v-model.number="row.pos" type="number" min="0" step="0.01" class="w-28 px-2.5 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-semibold text-slate-800 dark:text-slate-100 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20" />
                  </div>
                </td>
                <td class="p-3">
                  <label class="sr-only">Precio B2B en {{ row.branch }}</label>
                  <div class="flex items-center gap-1.5">
                    <span class="text-slate-400">BOB</span>
                    <input v-model.number="row.b2b" type="number" min="0" step="0.01" class="w-28 px-2.5 py-2 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg font-semibold text-slate-800 dark:text-slate-100 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20" />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="p-5 border-t border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p class="text-[11px] text-slate-500">
            {{ priceMatrixSavedAt ? `Matriz guardada a las ${priceMatrixSavedAt}.` : 'Los cambios se aplican al producto seleccionado en esta sesión.' }}
          </p>
          <button type="button" class="inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm" @click="savePriceMatrix">
            <Save class="w-3.5 h-3.5" />
            Guardar matriz
          </button>
        </div>
      </section>
    </HasRole>

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
  </div>
</template>
