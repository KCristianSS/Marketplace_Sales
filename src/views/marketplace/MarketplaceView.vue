<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useCartStore } from '@/stores/cart';
import { apiClient } from '@/api/client';
import type { Producto } from '@/types';
import { 
  Search, 
  ShoppingBag, 
  Filter, 
  CheckCircle2, 
  Star, 
  ShieldCheck, 
  Tag, 
  Eye, 
  X, 
  ChevronLeft, 
  ChevronRight,
  Layers,
  Sparkles
} from 'lucide-vue-next';

const cartStore = useCartStore();

const searchQuery = ref('');
const selectedCategory = ref('Todos');
const categories = ref(['Todos', 'Laptops y PCs', 'Periféricos', 'Monitores', 'Audio y Video']);

// Catálogo base con precios y ratings
interface MarketplaceProduct {
  id: string;
  sku: string;
  nombre: string;
  categoria: string;
  precio: number;
  rating: number;
  stock: number;
  badge: string;
  image: string;
  galleryImages: Array<{ id: string; url: string; es_principal: boolean; orden: number }>;
}

const products = ref<MarketplaceProduct[]>([
  {
    id: 'prod-001',
    sku: 'LAP-DELL-XPS15',
    nombre: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)',
    categoria: 'Laptops y PCs',
    precio: 8999.00,
    rating: 4.9,
    stock: 8,
    badge: 'Más Vendido',
    image: 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: 'prod-002',
    sku: 'MOU-LOG-MX3S',
    nombre: 'Mouse Inalámbrico Logitech MX Master 3S',
    categoria: 'Periféricos',
    precio: 799.00,
    rating: 4.8,
    stock: 24,
    badge: 'Popular',
    image: 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: 'prod-003',
    sku: 'MON-LG-27GP',
    nombre: 'Monitor Gamer LG UltraGear 27" 165Hz IPS',
    categoria: 'Monitores',
    precio: 2450.00,
    rating: 4.7,
    stock: 5,
    badge: 'Envío Gratis',
    image: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  },
  {
    id: 'prod-004',
    sku: 'AUR-SONY-WH1000',
    nombre: 'Auriculares Sony WH-1000XM5 Noise Cancelling',
    categoria: 'Audio y Video',
    precio: 2890.00,
    rating: 4.9,
    stock: 12,
    badge: 'Recomendado',
    image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80',
    galleryImages: []
  }
]);

// Sincronizar con base de datos Supabase
async function syncWithSupabase() {
  try {
    const res = await apiClient.get('/productos');
    const dbProducts: Producto[] = res.data.productos || [];

    // Actualizar imágenes, nombres, categorías y precios con los datos reales de Supabase
    dbProducts.forEach(dbp => {
      const match = products.value.find(p => p.sku === dbp.sku || p.id === dbp.id);
      const gallery = (dbp.imagenes_producto || []).sort((a, b) => a.orden - b.orden);
      const cover = gallery.find(i => i.es_principal) || gallery[0];
      const realPrice = dbp.precio !== undefined && dbp.precio !== null ? Number(dbp.precio) : null;

      if (match) {
        match.id = dbp.id;
        match.nombre = dbp.nombre;
        if (realPrice !== null && realPrice > 0) {
          match.precio = realPrice;
        }
        if (dbp.categorias?.nombre) {
          match.categoria = dbp.categorias.nombre;
        }
        if (cover?.url) {
          match.image = cover.url;
        }
        match.galleryImages = gallery;
      } else {
        // Nuevo producto agregado desde el Admin o Supabase
        products.value.unshift({
          id: dbp.id,
          sku: dbp.sku,
          nombre: dbp.nombre,
          categoria: dbp.categorias?.nombre || 'General',
          precio: realPrice !== null && realPrice > 0 ? realPrice : 1250.00,
          rating: 5.0,
          stock: 10,
          badge: 'Nuevo',
          image: cover?.url || 'https://images.unsplash.com/photo-1526738549149-8e07eca6c147?auto=format&fit=crop&w=600&q=80',
          galleryImages: gallery
        });
      }
    });
  } catch (err) {
    console.warn('Aviso sincronizando productos de Supabase:', err);
  }
}

onMounted(() => {
  syncWithSupabase();
});

// Modal de Galería de Producto
const activeGalleryProduct = ref<MarketplaceProduct | null>(null);
const currentGalleryIndex = ref(0);

function openProductGallery(prod: MarketplaceProduct) {
  activeGalleryProduct.value = prod;
  currentGalleryIndex.value = 0;
}

const currentGalleryImage = computed<string | undefined>(() => {
  if (!activeGalleryProduct.value) return undefined;
  const imgs = activeGalleryProduct.value.galleryImages;
  if (imgs.length === 0) return activeGalleryProduct.value.image;
  return imgs[currentGalleryIndex.value]?.url || activeGalleryProduct.value.image;
});

const filteredProducts = computed(() => {
  return products.value.filter(p => {
    const matchesSearch = p.nombre.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
                          p.sku.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
                          p.categoria.toLowerCase().includes(searchQuery.value.toLowerCase());
    const matchesCategory = selectedCategory.value === 'Todos' || p.categoria === selectedCategory.value;
    return matchesSearch && matchesCategory;
  });
});

function agregarAlCarrito(prod: any) {
  cartStore.addItem({
    variante_id: prod.id,
    sku: prod.sku,
    nombre: prod.nombre,
    cantidad: 1,
    precio_unitario: prod.precio
  });
}
</script>

<template>
  <div class="space-y-8">
    <!-- Hero Banner Promocional -->
    <section class="relative overflow-hidden rounded-2xl bg-gradient-to-r from-blue-700 via-indigo-700 to-slate-900 p-8 md:p-12 text-white shadow-xl">
      <div class="relative z-10 max-w-2xl space-y-4">
        <span class="inline-flex items-center gap-1.5 rounded-full bg-blue-500/30 px-3 py-1 text-xs font-semibold tracking-wide backdrop-blur-md border border-blue-400/30">
          <Tag class="w-3.5 h-3.5 text-cyan-300" /> Catálogo Multimedia en Supabase
        </span>
        <h1 class="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight">
          Tecnología de Punta con Entrega Inmediata.
        </h1>
        <p class="text-slate-200 text-sm sm:text-base">
          Explora el catálogo unificado de MaxiConecta con imágenes de alta resolución optimizadas con Sharp y almacenadas en Supabase Storage.
        </p>
      </div>
      <div class="absolute -right-10 -bottom-10 w-96 h-96 bg-cyan-500/20 rounded-full blur-3xl pointer-events-none"></div>
    </section>

    <!-- Barra de Filtros y Búsqueda Facetada (RF-06) -->
    <section class="flex flex-col md:flex-row gap-4 justify-between items-center bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
      <!-- Input de Búsqueda -->
      <div class="relative w-full md:w-96">
        <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Buscar por nombre, marca o SKU..."
          class="w-full pl-10 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      <!-- Píldoras de Categorías -->
      <div class="flex items-center gap-2 overflow-x-auto w-full md:w-auto pb-2 md:pb-0">
        <button
          v-for="cat in categories"
          :key="cat"
          @click="selectedCategory = cat"
          :class="[
            'px-3.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors',
            selectedCategory === cat
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
          ]"
        >
          {{ cat }}
        </button>
      </div>
    </section>

    <!-- Grid de Productos -->
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      <article
        v-for="prod in filteredProducts"
        :key="prod.id"
        class="group flex flex-col bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-lg transition-all duration-300"
      >
        <!-- Imagen de Portada y Galería -->
        <div class="relative h-52 bg-slate-100 dark:bg-slate-950 overflow-hidden">
          <img
            :src="prod.image"
            :alt="prod.nombre"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
            @click="openProductGallery(prod)"
          />
          <span class="absolute top-2.5 left-2.5 bg-blue-600/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full backdrop-blur-sm">
            {{ prod.badge }}
          </span>

          <!-- Indicador de Galería si tiene más fotos -->
          <button
            v-if="prod.galleryImages && prod.galleryImages.length > 0"
            @click="openProductGallery(prod)"
            class="absolute top-2.5 right-2.5 bg-black/60 hover:bg-black/80 text-white text-[10px] font-semibold px-2 py-1 rounded-md flex items-center gap-1 backdrop-blur-sm shadow"
            title="Ver galería completa"
          >
            <Layers class="w-3 h-3 text-cyan-400" />
            <span>{{ prod.galleryImages.length }} fotos</span>
          </button>

          <div class="absolute bottom-2.5 right-2.5 bg-black/60 text-white text-xs px-2 py-0.5 rounded-md flex items-center gap-1 backdrop-blur-sm">
            <Star class="w-3 h-3 text-amber-400 fill-amber-400" />
            <span>{{ prod.rating }}</span>
          </div>
        </div>

        <!-- Contenido -->
        <div class="p-4 flex-1 flex flex-col justify-between space-y-3">
          <div>
            <span class="text-[11px] font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider">
              {{ prod.categoria }}
            </span>
            <h3 
              @click="openProductGallery(prod)"
              class="font-semibold text-sm line-clamp-2 text-slate-800 dark:text-slate-100 group-hover:text-blue-600 transition-colors cursor-pointer"
            >
              {{ prod.nombre }}
            </h3>
            <p class="text-[11px] text-slate-400 font-mono mt-0.5">SKU: {{ prod.sku }}</p>
          </div>

          <div class="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <div>
              <span class="text-xs text-slate-400 block">Precio Contado</span>
              <span class="text-lg font-bold text-slate-900 dark:text-white">
                BOB {{ prod.precio.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}
              </span>
            </div>
            <button
              @click="agregarAlCarrito(prod)"
              class="p-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl shadow-sm active:scale-95 transition-all"
              title="Añadir al carrito"
            >
              <ShoppingBag class="w-4 h-4" />
            </button>
          </div>
        </div>
      </article>
    </section>

    <!-- MODAL: Visor de Galería Visual del Producto -->
    <div
      v-if="activeGalleryProduct"
      class="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-center justify-center p-4"
      @click.self="activeGalleryProduct = null"
    >
      <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-2xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <!-- Header del Modal -->
        <div class="p-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
          <div>
            <h3 class="text-sm font-bold text-slate-900 dark:text-white">{{ activeGalleryProduct.nombre }}</h3>
            <span class="text-xs text-slate-400 font-mono">SKU: {{ activeGalleryProduct.sku }}</span>
          </div>
          <button @click="activeGalleryProduct = null" class="p-1 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Imagen Principal Seleccionada -->
        <div class="relative bg-slate-950 flex items-center justify-center h-80 overflow-hidden">
          <img
            :src="currentGalleryImage"
            :alt="activeGalleryProduct.nombre"
            class="max-h-full max-w-full object-contain"
          />

          <!-- Botones de Navegación si hay múltiples imágenes -->
          <button
            v-if="activeGalleryProduct.galleryImages.length > 1"
            @click="currentGalleryIndex = (currentGalleryIndex - 1 + activeGalleryProduct.galleryImages.length) % activeGalleryProduct.galleryImages.length"
            class="absolute left-3 p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm"
          >
            <ChevronLeft class="w-5 h-5" />
          </button>
          <button
            v-if="activeGalleryProduct.galleryImages.length > 1"
            @click="currentGalleryIndex = (currentGalleryIndex + 1) % activeGalleryProduct.galleryImages.length"
            class="absolute right-3 p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm"
          >
            <ChevronRight class="w-5 h-5" />
          </button>
        </div>

        <!-- Tira de Miniaturas (Thumbnails) -->
        <div
          v-if="activeGalleryProduct.galleryImages.length > 0"
          class="p-4 bg-slate-50 dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800 flex gap-2 overflow-x-auto"
        >
          <button
            v-for="(img, idx) in activeGalleryProduct.galleryImages"
            :key="img.id"
            @click="currentGalleryIndex = idx"
            :class="[
              'w-16 h-16 rounded-xl border-2 overflow-hidden shrink-0 transition-all',
              currentGalleryIndex === idx
                ? 'border-blue-600 ring-2 ring-blue-500/20 scale-105'
                : 'border-transparent opacity-70 hover:opacity-100'
            ]"
          >
            <img :src="img.url" class="w-full h-full object-cover" alt="Thumbnail" />
          </button>
        </div>

        <!-- Footer con Acción de Compra -->
        <div class="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center">
          <div>
            <span class="text-xs text-slate-400 block">Precio Oficial</span>
            <span class="text-xl font-extrabold text-blue-600 dark:text-blue-400">
              BOB {{ activeGalleryProduct.precio.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}
            </span>
          </div>
          <button
            @click="agregarAlCarrito(activeGalleryProduct); activeGalleryProduct = null"
            class="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-md flex items-center gap-2"
          >
            <ShoppingBag class="w-4 h-4" />
            <span>Añadir al Carrito</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
