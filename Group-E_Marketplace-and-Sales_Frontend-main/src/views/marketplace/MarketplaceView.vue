<script setup lang="ts">
import { notify } from '@/lib/feedback';
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useCartStore } from '@/stores/cart';
import { apiClient } from '@/api/client';
import type { FacetasCatalogo, SugerenciaItem, MarketplaceProduct, Combo } from '@/types';
import { useWishlistStore } from '@/stores/wishlist';
import { useAuthStore } from '@/stores/auth';
import { consultarStock, resolverPreciosLote, obtenerCombos } from '@/api/catalogo';
import { 
  Sparkles, 
  Search, 
  RotateCcw,
  ShoppingBag, 
  Filter, 
  CheckCircle2, 
  Star, 
  Tag, 
  Eye, 
  X, 
  ChevronLeft, 
  ChevronRight, 
  Layers, 
  Heart, 
  RefreshCw, 
  Clock3
} from 'lucide-vue-next';

// Subcomponentes modulares
import MarketplaceSearchBar from '@/components/marketplace/MarketplaceSearchBar.vue';
import MarketplaceFacetSidebar from '@/components/marketplace/MarketplaceFacetSidebar.vue';
import ProductCard from '@/components/marketplace/ProductCard.vue';
import ProductGalleryModal from '@/components/marketplace/ProductGalleryModal.vue';
import ComboCard from '@/components/marketplace/ComboCard.vue';
import ComboDetailModal from '@/components/marketplace/ComboDetailModal.vue';
import ProductRecommendations from '@/components/ProductRecommendations.vue';

const route = useRoute();
const router = useRouter();
const cartStore = useCartStore();
const wishlistStore = useWishlistStore();
const authStore = useAuthStore();
const selectedRecommendationProduct = ref<MarketplaceProduct | null>(null);

function notifyWishlist(message: string, type: 'success' | 'error' = 'success') {
  notify[type](message);
}

// -----------------------------------------------------------------------------
// ESTADO DE BÚSQUEDA Y FILTROS FACETADOS (RF-06 / US-06)
// -----------------------------------------------------------------------------
const searchQuery = ref('');
const debouncedQuery = ref('');
const isSearching = ref(false);
const isSyncingCatalog = ref(false);
const catalogUpdatedAt = ref('recién sincronizado');
const showSuggestions = ref(false);
const suggestions = ref<SugerenciaItem[]>([]);

// Filtros facetados
const selectedCategoryIds = ref<string[]>([]);
const selectedBrands = ref<string[]>([]);
const priceMinInput = ref<number | null>(null);
const priceMaxInput = ref<number | null>(null);
const appliedPriceMin = ref<number | null>(null);
const appliedPriceMax = ref<number | null>(null);
const onlyInStock = ref(false);
const sortBy = ref<'relevancia' | 'precio_asc' | 'precio_desc' | 'nombre'>('relevancia');

// Facetas reactivas devueltas por el backend
const facets = ref<FacetasCatalogo>({
  categorias: [],
  marcas: [],
  precio: { min: 0, max: 0 },
  en_stock: 0,
  total_general: 0
});

// Control responsive del panel lateral de filtros en móviles
const isMobileFiltersOpen = ref(false);

const products = ref<MarketplaceProduct[]>([]);
const totalCoincidencias = ref(0);

// Combos y Paquetes Comerciales (RF-18 / US-18)
const combosList = ref<Combo[]>([]);
const isLoadingCombos = ref(false);
const activeComboDetail = ref<Combo | null>(null);
const combosDisponibles = computed(() => combosList.value.filter(combo => combo.disponible).length);
const maxComboDiscount = computed(() => Math.max(
  0,
  ...combosList.value.map(combo => Number(combo.ahorro_porcentaje || 0))
));

async function cargarCombosMarketplace() {
  isLoadingCombos.value = true;
  try {
    combosList.value = await obtenerCombos({ solo_activos: true });
  } catch (err) {
    console.warn('Aviso: error cargando combos en marketplace:', err);
  } finally {
    isLoadingCombos.value = false;
  }
}

// Productos Recomendados (RF-19 / US-19 Cross-selling)
const recommendedProducts = ref<MarketplaceProduct[]>([]);
const isLoadingRecommendations = ref(false);

// Base de catálogo local de respaldo
const fallbackProducts: MarketplaceProduct[] = [
  {
    id: '20000000-0000-0000-0000-000000000001',
    sku: 'LAP-DELL-XPS15',
    nombre: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)',
    categoria: 'Laptops y PCs',
    categoria_id: '10000000-0000-0000-0000-000000000001',
    marca: 'Dell',
    precio: 8999.00,
    rating: 4.9,
    stock: 8,
    badge: 'Más Vendido',
    image: 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000002',
    sku: 'LAP-APP-MBP16',
    nombre: 'Apple MacBook Pro 16" Chip M3 Pro',
    categoria: 'Laptops y PCs',
    categoria_id: '10000000-0000-0000-0000-000000000001',
    marca: 'Apple',
    precio: 18500.00,
    rating: 5.0,
    stock: 4,
    badge: 'Pro Performance',
    image: 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000003',
    sku: 'MOU-LOG-MX3S',
    nombre: 'Mouse Inalámbrico Logitech MX Master 3S',
    categoria: 'Periféricos',
    categoria_id: '10000000-0000-0000-0000-000000000002',
    marca: 'Logitech',
    precio: 799.00,
    rating: 4.8,
    stock: 24,
    badge: 'Ergonomía Top',
    image: 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000004',
    sku: 'TEC-LOG-MXMECH',
    nombre: 'Teclado Mecánico Inalámbrico Logitech MX Mechanical',
    categoria: 'Periféricos',
    categoria_id: '10000000-0000-0000-0000-000000000002',
    marca: 'Logitech',
    precio: 1150.00,
    rating: 4.8,
    stock: 15,
    badge: 'Productividad',
    image: 'https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000005',
    sku: 'MON-LG-27GP',
    nombre: 'Monitor Gamer LG UltraGear 27" 165Hz IPS',
    categoria: 'Monitores',
    categoria_id: '10000000-0000-0000-0000-000000000003',
    marca: 'LG',
    precio: 2450.00,
    rating: 4.7,
    stock: 5,
    badge: 'Gamer 165Hz',
    image: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000006',
    sku: 'MON-SAM-M8',
    nombre: 'Monitor Inteligente Samsung Smart M8 32" 4K',
    categoria: 'Monitores',
    categoria_id: '10000000-0000-0000-0000-000000000003',
    marca: 'Samsung',
    precio: 4200.00,
    rating: 4.6,
    stock: 7,
    badge: 'Smart 4K',
    image: 'https://images.unsplash.com/photo-1547119957-637f8679db1e?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000007',
    sku: 'AUR-SONY-WH1000',
    nombre: 'Auriculares Sony WH-1000XM5 Noise Cancelling',
    categoria: 'Audio y Video',
    categoria_id: '10000000-0000-0000-0000-000000000004',
    marca: 'Sony',
    precio: 2890.00,
    rating: 4.9,
    stock: 12,
    badge: 'Hi-Res Audio',
    image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: '20000000-0000-0000-0000-000000000008',
    sku: 'CAM-SONY-A7IV',
    nombre: 'Cámara Digital Sony Alpha 7 IV Full-Frame Mirrorless',
    categoria: 'Cámaras y Fotografía',
    categoria_id: '10000000-0000-0000-0000-000000000005',
    marca: 'Sony',
    precio: 16999.00,
    rating: 5.0,
    stock: 3,
    badge: 'Full Frame 4K',
    image: 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  }
];

function mapDbProductToMarketplace(dbp: any): MarketplaceProduct {
  const gallery = (dbp.imagenes_producto || []).sort((a: any, b: any) => a.orden - b.orden);
  const cover = gallery.find((i: any) => i.es_principal) || gallery[0];
  const realPrice = Number(dbp.precio || 0);

  const rawVariants = Array.isArray(dbp.variantes) ? dbp.variantes : [];
  const firstVariant = rawVariants.length > 0 ? rawVariants[0] : null;
  const atributos = firstVariant?.atributos || dbp.atributos || {};

  return {
    id: dbp.id,
    sku: dbp.sku,
    nombre: dbp.nombre,
    descripcion: dbp.descripcion || '',
    categoria: dbp.categorias?.nombre || 'General',
    categoria_id: dbp.categoria_id,
    marca: dbp.marca || 'MaxiConecta',
    precio: realPrice > 0 ? realPrice : 999.00,
    rating: 4.8,
    stock: dbp.stock == null ? -1 : Number(dbp.stock),
    badge: realPrice > 8000 ? 'Pro' : (dbp.stock == null ? 'Consultar stock' : (dbp.stock < 5 ? 'Pocas unidades' : 'Disponible')),
    image: cover?.url || (dbp.imagenes && dbp.imagenes[0]) || 'https://images.unsplash.com/photo-1526738549149-8e07eca6c147?auto=format&fit=crop&w=600&q=80',
    galleryImages: gallery,
    atributos: atributos,
    variantes: rawVariants.map((v: any) => ({
      id: v.id,
      sku: v.sku,
      nombre_variante: v.nombre_variante,
      atributos: v.atributos || {},
      precio: Number(v.precio || realPrice)
    }))
  };
}

// -----------------------------------------------------------------------------
// SINCRONIZACIÓN DE FILTROS CON LA URL (DEEP LINKING & HISTORIAL)
// -----------------------------------------------------------------------------
let isReadingUrl = false;

function leerFiltrosDeUrl() {
  isReadingUrl = true;
  const q = route.query;

  if (q.q && typeof q.q === 'string') {
    searchQuery.value = q.q;
    debouncedQuery.value = q.q;
  } else {
    searchQuery.value = '';
    debouncedQuery.value = '';
  }

  if (q.categoria_ids && typeof q.categoria_ids === 'string') {
    selectedCategoryIds.value = q.categoria_ids.split(',').filter(Boolean);
  } else {
    selectedCategoryIds.value = [];
  }

  if (q.marcas && typeof q.marcas === 'string') {
    selectedBrands.value = q.marcas.split(',').filter(Boolean);
  } else {
    selectedBrands.value = [];
  }

  if (q.precio_min) {
    const pMin = Number(q.precio_min);
    if (!isNaN(pMin) && pMin > 0) {
      priceMinInput.value = pMin;
      appliedPriceMin.value = pMin;
    }
  } else {
    priceMinInput.value = null;
    appliedPriceMin.value = null;
  }

  if (q.precio_max) {
    const pMax = Number(q.precio_max);
    if (!isNaN(pMax) && pMax > 0) {
      priceMaxInput.value = pMax;
      appliedPriceMax.value = pMax;
    }
  } else {
    priceMaxInput.value = null;
    appliedPriceMax.value = null;
  }

  onlyInStock.value = q.en_stock === 'true';

  if (q.ordenar_por && typeof q.ordenar_por === 'string') {
    if (['relevancia', 'precio_asc', 'precio_desc', 'nombre'].includes(q.ordenar_por)) {
      sortBy.value = q.ordenar_por as any;
    }
  } else {
    sortBy.value = 'relevancia';
  }

  isReadingUrl = false;
}

function sincronizarUrlConFiltros() {
  if (isReadingUrl) return;

  const queryParams: Record<string, string> = {};
  if (debouncedQuery.value.trim()) queryParams.q = debouncedQuery.value.trim();
  if (selectedCategoryIds.value.length > 0) queryParams.categoria_ids = selectedCategoryIds.value.join(',');
  if (selectedBrands.value.length > 0) queryParams.marcas = selectedBrands.value.join(',');
  if (appliedPriceMin.value !== null && appliedPriceMin.value > 0) queryParams.precio_min = String(appliedPriceMin.value);
  if (appliedPriceMax.value !== null && appliedPriceMax.value > 0) queryParams.precio_max = String(appliedPriceMax.value);
  if (onlyInStock.value) queryParams.en_stock = 'true';
  if (sortBy.value !== 'relevancia') queryParams.ordenar_por = sortBy.value;

  router.replace({ query: queryParams });
}

// -----------------------------------------------------------------------------
// DEBOUNCE PARA BÚSQUEDA Y SUGERENCIAS
// -----------------------------------------------------------------------------
let debounceTimeout: any = null;
let suggestionsTimeout: any = null;

watch(searchQuery, (newVal) => {
  clearTimeout(debounceTimeout);
  clearTimeout(suggestionsTimeout);

  if (newVal.trim().length >= 1) {
    suggestionsTimeout = setTimeout(() => {
      fetchSuggestions(newVal.trim());
    }, 150);
  } else {
    suggestions.value = [];
    showSuggestions.value = false;
  }

  debounceTimeout = setTimeout(() => {
    debouncedQuery.value = newVal.trim();
    sincronizarUrlConFiltros();
    ejecutarBusqueda();
  }, 300);
});

// Observar navegación con botones Atrás/Adelante del navegador
watch(
  () => route.query,
  () => {
    leerFiltrosDeUrl();
    ejecutarBusqueda();
  }
);

watch(
  () => [authStore.user?.tipo_cliente, authStore.user?.sucursal_id],
  () => ejecutarBusqueda()
);

watch(
  () => authStore.user?.id,
  (clienteId) => { if (clienteId) void wishlistStore.cargarDeseos(clienteId); },
  { immediate: true }
);

onMounted(() => {
  leerFiltrosDeUrl();
  ejecutarBusqueda();
  fetchRecommendations();
  cargarCombosMarketplace();
});

watch(
  products,
  (newProds) => {
    if (newProds.length > 0 && !selectedRecommendationProduct.value) {
      selectedRecommendationProduct.value = newProds[0];
    }
  },
  { immediate: true }
);

// -----------------------------------------------------------------------------
// LLAMADAS AL ENDPOINT DE BÚSQUEDA, SUGERENCIAS Y RECOMENDACIONES (RF-19)
// -----------------------------------------------------------------------------
async function fetchSuggestions(term: string) {
  try {
    const res = await apiClient.get('/api/v1/catalogo/sugerencias', {
      params: { q: term, limite: 5 }
    });
    suggestions.value = Array.isArray(res.data) ? res.data : [];
    showSuggestions.value = suggestions.value.length > 0;
  } catch (err) {
    const norm = term.toLowerCase();
    suggestions.value = fallbackProducts
      .filter(p => p.nombre.toLowerCase().includes(norm) || p.sku.toLowerCase().includes(norm) || p.categoria.toLowerCase().includes(norm))
      .slice(0, 5)
      .map(p => ({
        id: p.id,
        nombre: p.nombre,
        sku: p.sku,
        categoria: p.categoria,
        marca: p.marca || null,
        precio: p.precio,
        imagen_url: p.image,
        stock: p.stock
      }));
    showSuggestions.value = suggestions.value.length > 0;
  }
}

async function fetchRecommendations(targetProdId?: string, catId?: string) {
  isLoadingRecommendations.value = true;
  try {
    const params: Record<string, any> = { limite: 4 };
    if (targetProdId) params.id = targetProdId;
    if (catId) params.categoria_id = catId;
    const res = await apiClient.get('/api/v1/catalogo/recomendaciones', { params });
    if (res.data && Array.isArray(res.data) && res.data.length > 0) {
      recommendedProducts.value = await applyResolvedPrices(res.data.map(mapDbProductToMarketplace));
    } else {
      recommendedProducts.value = await applyResolvedPrices(fallbackProducts.slice(0, 4));
    }
  } catch {
    recommendedProducts.value = await applyResolvedPrices(fallbackProducts.slice(0, 4));
  } finally {
    isLoadingRecommendations.value = false;
  }
}

async function applyResolvedPrices(productsToPrice: MarketplaceProduct[]): Promise<MarketplaceProduct[]> {
  const tipoCliente = authStore.user?.tipo_cliente === 'corporativo_b2b'
    ? 'corporativo_b2b'
    : 'retail';
  const sucursalId = authStore.user?.sucursal_id || undefined;
  if (productsToPrice.length === 0) return productsToPrice;

  try {
    const resolutions = await resolverPreciosLote({
      variante_ids: productsToPrice.map(product => product.id),
      canal: 'web',
      tipo_cliente: tipoCliente,
      sucursal_id: sucursalId
    });
    for (const product of productsToPrice) {
      const resolution = resolutions[product.id];
      if (resolution) {
        product.precio = Number(resolution.precio) * (resolution.moneda === 'USD' ? 6.96 : 1);
      }
    }
  } catch {
    // Mantener el precio base del catálogo si el resolutor no está disponible.
  }
  return productsToPrice;
}

function selectSuggestion(item: SugerenciaItem) {
  searchQuery.value = item.nombre;
  debouncedQuery.value = item.nombre;
  showSuggestions.value = false;
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function clearSearch() {
  searchQuery.value = '';
  debouncedQuery.value = '';
  showSuggestions.value = false;
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

async function ejecutarBusqueda() {
  isSearching.value = true;
  try {
    const params: Record<string, any> = {
      ordenar_por: sortBy.value,
      pagina: 1,
      limite: 40
    };

    if (debouncedQuery.value) {
      params.q = debouncedQuery.value;
    }
    if (selectedCategoryIds.value.length > 0) {
      params.categoria_ids = selectedCategoryIds.value.join(',');
    }
    if (selectedBrands.value.length > 0) {
      params.marcas = selectedBrands.value.join(',');
    }
    if (appliedPriceMin.value !== null && appliedPriceMin.value > 0) {
      params.precio_min = appliedPriceMin.value;
    }
    if (appliedPriceMax.value !== null && appliedPriceMax.value > 0) {
      params.precio_max = appliedPriceMax.value;
    }
    if (onlyInStock.value) {
      params.en_stock = true;
    }

    const res = await apiClient.get('/api/v1/catalogo/buscar', { params });
    const data = res.data;

    if (data && Array.isArray(data.items)) {
      totalCoincidencias.value = data.total_coincidencias ?? data.items.length;
      facets.value = data.facetas || {
        categorias: [],
        marcas: [],
        precio: { min: 0, max: 0 },
        en_stock: 0,
        total_general: data.items.length
      };

      products.value = await applyResolvedPrices(data.items.map(mapDbProductToMarketplace));
      catalogUpdatedAt.value = new Date().toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' });
    }
  } catch (err) {
    console.warn('Aviso: backend no disponible, ejecutando motor facetado en memoria local:', err);
    await aplicarFiltrosLocales();
  } finally {
    isSearching.value = false;
  }
}

async function aplicarFiltrosLocales() {
  const normQ = debouncedQuery.value.toLowerCase();
  let filtered = [...fallbackProducts];

  if (normQ) {
    filtered = filtered.filter(p => 
      p.nombre.toLowerCase().includes(normQ) ||
      p.sku.toLowerCase().includes(normQ) ||
      p.categoria.toLowerCase().includes(normQ) ||
      (p.marca && p.marca.toLowerCase().includes(normQ))
    );
  }

  const catMap: Record<string, { id: string; etiqueta: string; total: number }> = {};
  const brandMap: Record<string, number> = {};
  let minP = Infinity;
  let maxP = 0;
  let inStockCount = 0;

  filtered.forEach(p => {
    if (p.precio < minP) minP = p.precio;
    if (p.precio > maxP) maxP = p.precio;
    if (p.stock > 0) inStockCount++;

    if (p.categoria_id) {
      if (!catMap[p.categoria_id]) {
        catMap[p.categoria_id] = { id: p.categoria_id, etiqueta: p.categoria, total: 0 };
      }
      catMap[p.categoria_id].total++;
    }

    if (p.marca) {
      brandMap[p.marca] = (brandMap[p.marca] || 0) + 1;
    }
  });

  facets.value = {
    categorias: Object.values(catMap).map(c => ({
      ...c,
      seleccionado: selectedCategoryIds.value.includes(c.id)
    })),
    marcas: Object.entries(brandMap).map(([brand, count]) => ({
      id: brand,
      etiqueta: brand,
      total: count,
      seleccionado: selectedBrands.value.includes(brand)
    })),
    precio: { min: minP === Infinity ? 0 : minP, max: maxP },
    en_stock: inStockCount,
    total_general: fallbackProducts.length
  };

  if (selectedCategoryIds.value.length > 0) {
    filtered = filtered.filter(p => p.categoria_id && selectedCategoryIds.value.includes(p.categoria_id));
  }
  if (selectedBrands.value.length > 0) {
    filtered = filtered.filter(p => p.marca && selectedBrands.value.includes(p.marca));
  }
  if (appliedPriceMin.value !== null) {
    filtered = filtered.filter(p => p.precio >= appliedPriceMin.value!);
  }
  if (appliedPriceMax.value !== null) {
    filtered = filtered.filter(p => p.precio <= appliedPriceMax.value!);
  }
  if (onlyInStock.value) {
    filtered = filtered.filter(p => p.stock > 0);
  }

  if (sortBy.value === 'precio_asc') {
    filtered.sort((a, b) => a.precio - b.precio);
  } else if (sortBy.value === 'precio_desc') {
    filtered.sort((a, b) => b.precio - a.precio);
  } else if (sortBy.value === 'nombre') {
    filtered.sort((a, b) => a.nombre.localeCompare(b.nombre));
  }

  products.value = await applyResolvedPrices(filtered);
  totalCoincidencias.value = filtered.length;
}

// -----------------------------------------------------------------------------
// CONTROLADORES DE FILTROS FACETADOS
// -----------------------------------------------------------------------------
function toggleCategoria(catId: string) {
  const index = selectedCategoryIds.value.indexOf(catId);
  if (index > -1) {
    selectedCategoryIds.value.splice(index, 1);
  } else {
    selectedCategoryIds.value.push(catId);
  }
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function toggleMarca(brandName: string) {
  const index = selectedBrands.value.indexOf(brandName);
  if (index > -1) {
    selectedBrands.value.splice(index, 1);
  } else {
    selectedBrands.value.push(brandName);
  }
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function aplicarRangoPrecio(min: number | null, max: number | null) {
  priceMinInput.value = min;
  priceMaxInput.value = max;
  appliedPriceMin.value = min;
  appliedPriceMax.value = max;
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function toggleStock() {
  onlyInStock.value = !onlyInStock.value;
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function limpiarTodosLosFiltros() {
  searchQuery.value = '';
  debouncedQuery.value = '';
  selectedCategoryIds.value = [];
  selectedBrands.value = [];
  priceMinInput.value = null;
  priceMaxInput.value = null;
  appliedPriceMin.value = null;
  appliedPriceMax.value = null;
  onlyInStock.value = false;
  sortBy.value = 'relevancia';
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

function onSortChange() {
  sincronizarUrlConFiltros();
  ejecutarBusqueda();
}

const activeFiltersCount = computed(() => {
  let count = 0;
  if (debouncedQuery.value) count++;
  count += selectedCategoryIds.value.length;
  count += selectedBrands.value.length;
  if (appliedPriceMin.value !== null || appliedPriceMax.value !== null) count++;
  if (onlyInStock.value) count++;
  return count;
});

function refreshCatalog() {
  isSyncingCatalog.value = true;
  ejecutarBusqueda().finally(() => {
    isSyncingCatalog.value = false;
  });
}

// -----------------------------------------------------------------------------
// MODAL DE GALERÍA Y ACCIONES DE CARRITO / DESEOS
// -----------------------------------------------------------------------------
const activeGalleryProduct = ref<MarketplaceProduct | null>(null);

function openProductGallery(prod: MarketplaceProduct) {
  activeGalleryProduct.value = prod;
}

async function agregarAlCarrito(prod: MarketplaceProduct) {
  try {
    const stock = await consultarStock(prod.sku);
    products.value.filter(p => p.sku === prod.sku).forEach(p => { p.stock = stock.stock_disponible; });
    cartStore.addItem({
      variante_id: prod.id,
      sku: prod.sku,
      nombre: prod.nombre,
      cantidad: 1,
      precio_unitario: prod.precio,
      stock_disponible: stock.stock_disponible
    });
  } catch {
    cartStore.error = `No se pudo verificar el stock de ${prod.nombre}. Inténtalo nuevamente.`;
    cartStore.openDrawer();
  }
}

async function alternarDeseo(prod: MarketplaceProduct) {
  const clienteId = authStore.user?.id;
  if (!clienteId) {
    authStore.openAuthModal('login');
    return;
  }
  const estabaEnDeseos = wishlistStore.estaEnDeseos(prod.id);
  const correcto = estabaEnDeseos
    ? await wishlistStore.eliminarDeseo(clienteId, prod.id)
    : await wishlistStore.agregarDeseo(clienteId, prod.id);
  const guardado = correcto ? !estabaEnDeseos : estabaEnDeseos;

  if (wishlistStore.error) {
    notifyWishlist(wishlistStore.error, 'error');
  } else if (guardado !== estabaEnDeseos) {
    const destino = authStore.user?.id ? 'tu lista de deseos' : 'la lista de deseos de este dispositivo';
    notifyWishlist(guardado ? `Producto guardado en ${destino}.` : 'Producto quitado de tu lista de deseos.');
  }
}
</script>

<template>
  <div class="space-y-8">


    <!-- Barra de Búsqueda Predictiva con Autocompletado (Subcomponente) -->
    <MarketplaceSearchBar
      v-model:search-query="searchQuery"
      v-model:sort-by="sortBy"
      v-model:show-suggestions="showSuggestions"
      :suggestions="suggestions"
      :is-searching="isSearching"
      :is-syncing-catalog="isSyncingCatalog"
      :active-filters-count="activeFiltersCount"
      :facets="facets"
      :selected-category-ids="selectedCategoryIds"
      :selected-brands="selectedBrands"
      :applied-price-min="appliedPriceMin"
      :applied-price-max="appliedPriceMax"
      :only-in-stock="onlyInStock"
      :debounced-query="debouncedQuery"
      @select-suggestion="selectSuggestion"
      @clear-search="clearSearch"
      @toggle-mobile-filters="isMobileFiltersOpen = !isMobileFiltersOpen"
      @refresh-catalog="refreshCatalog"
      @toggle-category="toggleCategoria"
      @toggle-brand="toggleMarca"
      @clear-price-range="aplicarRangoPrecio(null, null)"
      @toggle-stock="toggleStock"
      @clear-all-filters="limpiarTodosLosFiltros"
      @sort-change="onSortChange"
    />

    <!-- =================================================================== -->
    <!-- SECCIÓN DESTACADA: COMBOS Y PAQUETES COMERCIALES (US-18 / RF-18)    -->
    <!-- =================================================================== -->
    <section v-if="isLoadingCombos || combosList.length > 0" class="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="relative flex flex-col gap-6 overflow-hidden bg-slate-950 px-6 py-7 text-white sm:flex-row sm:items-end sm:justify-between sm:px-8">
        <div class="relative z-10 flex max-w-2xl items-start gap-4">
          <div class="rounded-2xl bg-indigo-500 p-3 text-white shadow-lg shadow-indigo-950/40">
            <Layers class="h-6 w-6" />
          </div>
          <div class="space-y-2">
            <h2 class="text-xl font-black leading-tight text-white sm:text-2xl">
              Combos y Paquetes Comerciales en Oferta
            </h2>
            <p class="max-w-xl text-sm leading-relaxed text-slate-300">
              Equipa todo de una vez con precios especiales y stock confirmado para cada producto del paquete.
            </p>
          </div>
        </div>

        <div class="relative z-10 grid w-full grid-cols-2 gap-3 sm:w-auto">
          <div class="min-w-28 border-l border-white/20 pl-4">
            <span class="block text-xs text-slate-400">Disponibles hoy</span>
            <strong class="mt-1 block text-2xl font-black text-white">{{ combosDisponibles }}</strong>
          </div>
          <div class="min-w-32 border-l border-white/20 pl-4">
            <span class="block text-xs text-slate-400">Ahorro de hasta</span>
            <strong class="mt-1 block text-2xl font-black text-emerald-400">{{ maxComboDiscount }}%</strong>
          </div>
        </div>
      </div>

      <div class="bg-slate-50 p-4 sm:p-6 dark:bg-slate-950/40">
        <div v-if="isLoadingCombos" class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          <div v-for="index in 3" :key="index" class="h-[34rem] animate-pulse rounded-[1.75rem] bg-slate-200 dark:bg-slate-800" />
        </div>
        <div v-else class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        <ComboCard
          v-for="combo in combosList"
          :key="combo.id"
          :combo="combo"
          @ver-detalle="activeComboDetail = $event"
        />
        </div>
      </div>
    </section>

    <!-- Layout Principal: Barra Lateral de Filtros Facetados + Cuadrícula de Productos -->
    <div class="grid grid-cols-1 lg:grid-cols-[270px_1fr] gap-8 items-start">

      <!-- Barra Lateral de Filtros Facetados (Subcomponente) -->
      <MarketplaceFacetSidebar
        :facets="facets"
        :selected-category-ids="selectedCategoryIds"
        :selected-brands="selectedBrands"
        :price-min="appliedPriceMin"
        :price-max="appliedPriceMax"
        :only-in-stock="onlyInStock"
        :active-filters-count="activeFiltersCount"
        :is-mobile-open="isMobileFiltersOpen"
        @toggle-category="toggleCategoria"
        @toggle-brand="toggleMarca"
        @apply-price-range="aplicarRangoPrecio"
        @toggle-stock="toggleStock"
        @reset-filters="limpiarTodosLosFiltros"
        @close-mobile="isMobileFiltersOpen = false"
      />

      <!-- Cuadrícula de Productos o Estado Vacío -->
      <main class="space-y-6">

        <!-- Indicador de Resultados y Estado -->
        <div class="flex items-center justify-between text-xs text-slate-500 px-1">
          <p class="flex items-center gap-1.5 font-medium">
            <span class="w-2 h-2 rounded-full bg-teal-500"></span>
            Mostrando <strong class="text-slate-900 dark:text-white">{{ products.length }}</strong> de {{ totalCoincidencias }} productos encontrados
          </p>
          <span class="text-[11px] text-slate-400 hidden sm:inline">
            Sincronizado: {{ catalogUpdatedAt }}
          </span>
        </div>

        <!-- Grid de Tarjetas de Productos (Subcomponente ProductCard) -->
        <section v-if="products.length > 0" class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6">
          <ProductCard
            v-for="prod in products"
            :key="prod.id"
            :product="prod"
            :is-in-wishlist="wishlistStore.estaEnDeseos(prod.id)"
            @open-gallery="openProductGallery"
            @toggle-wishlist="alternarDeseo"
            @add-to-cart="agregarAlCarrito"
          />
        </section>

        <!-- Estado Vacío Cuando no hay Coincidencias con Recomendaciones (RF-19) -->
        <div v-else class="space-y-8">
          <section class="py-12 px-6 text-center bg-white/90 dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div class="w-16 h-16 mx-auto rounded-2xl bg-amber-50 dark:bg-amber-950 flex items-center justify-center text-amber-600 dark:text-amber-400">
              <Search class="w-8 h-8" />
            </div>
            <div class="max-w-md mx-auto space-y-1.5">
              <h2 class="text-lg font-black text-slate-800 dark:text-white">
                No encontramos coincidencias para "{{ debouncedQuery || 'los filtros aplicados' }}"
              </h2>
              <p class="text-xs text-slate-500 leading-relaxed">
                Ningún producto coincide con esta combinación de filtros. Puedes restablecerlos o descubrir nuestras recomendaciones sugeridas abajo.
              </p>
            </div>
            <div class="pt-2 flex justify-center gap-3">
              <button
                @click="limpiarTodosLosFiltros"
                class="px-4 py-2 rounded-xl bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold shadow-md inline-flex items-center gap-2"
              >
                <RotateCcw class="w-3.5 h-3.5" />
                <span>Restablecer todos los filtros</span>
              </button>
            </div>
          </section>

          <!-- Bloque de Recomendaciones (RF-19 / US-19 Cross-selling) -->
          <section v-if="recommendedProducts.length > 0" class="space-y-4 pt-2">
            <div class="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div class="flex items-center gap-2">
                <div class="p-1 rounded-lg bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400">
                  <Sparkles class="w-4 h-4" />
                </div>
                <div>
                  <h3 class="text-sm font-extrabold text-slate-900 dark:text-white uppercase tracking-wider">
                    Productos Recomendados para ti
                  </h3>
                  <p class="text-[11px] text-slate-400">Artículos populares y afines disponibles para entrega inmediata</p>
                </div>
              </div>
              <span class="text-xs font-bold text-teal-700 dark:text-teal-400">
                {{ recommendedProducts.length }} sugerencias
              </span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
              <ProductCard
                v-for="rec in recommendedProducts"
                :key="'rec-' + rec.id"
                :product="rec"
                :is-in-wishlist="wishlistStore.estaEnDeseos(rec.id)"
                @open-gallery="openProductGallery"
                @toggle-wishlist="alternarDeseo"
                @add-to-cart="agregarAlCarrito"
              />
            </div>
          </section>
        </div>
      </main>
    </div>

    <!-- ===================================================================== -->
    <!-- KAN-35 / RF-19: SECCIÓN DESTACADA DE RECOMENDACIONES Y BUNDLES -->
    <!-- ===================================================================== -->
    <section v-if="products.length > 0" class="mt-8 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-5">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-800">
        <div>
          <h2 class="text-xl font-black text-slate-900 dark:text-white">Motor de Recomendaciones y Paquetes Frecuentes</h2>
          <p class="text-xs text-slate-500 mt-0.5">Explora las recomendaciones automáticas de complementos afines, alternativas de gama superior y bundles con 8% OFF.</p>
        </div>

        <!-- Selector de producto para ver recomendaciones -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full">
          <span class="text-xs font-semibold text-slate-400 whitespace-nowrap mr-1">Ver para:</span>
          <button
            v-for="p in products.slice(0, 5)"
            :key="'rec-tab-' + p.id"
            @click="selectedRecommendationProduct = p"
            :class="[
              'px-3 py-1.5 text-xs font-bold rounded-xl transition-all whitespace-nowrap flex items-center gap-1.5',
              selectedRecommendationProduct?.id === p.id
                ? 'bg-teal-700 text-white shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            ]"
          >
            <span>{{ p.nombre.split(' ')[0] }} {{ p.nombre.split(' ')[1] || '' }}</span>
          </button>
        </div>
      </div>

      <ProductRecommendations
        v-if="selectedRecommendationProduct"
        :productId="selectedRecommendationProduct.id"
        :productSku="selectedRecommendationProduct.sku"
        :productTitle="selectedRecommendationProduct.nombre"
      />
    </section>

    <!-- Visor Modal de Galería (Subcomponente) -->
    <ProductGalleryModal
      :product="activeGalleryProduct"
      @close="activeGalleryProduct = null"
      @add-to-cart="agregarAlCarrito"
    />

    <!-- Modal Detalle del Combo como Artículo Único (US-18 / RF-18) -->
    <ComboDetailModal
      :combo="activeComboDetail"
      @close="activeComboDetail = null"
    />
  </div>
</template>
