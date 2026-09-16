<script setup lang="ts">
import { ref, computed } from 'vue';
import { useCartStore } from '@/stores/cart';
import { Search, ShoppingBag, Filter, CheckCircle2, Star, ShieldCheck, Tag } from 'lucide-vue-next';

const cartStore = useCartStore();

const searchQuery = ref('');
const selectedCategory = ref('Todos');
const categories = ['Todos', 'Laptops y PCs', 'Periféricos', 'Audio y Video', 'Monitores'];

const products = ref([
  {
    id: 'prod-001',
    sku: 'LAP-DELL-XPS15',
    nombre: 'Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)',
    categoria: 'Laptops y PCs',
    precio: 8999.00,
    rating: 4.9,
    stock: 8,
    badge: 'Más Vendido',
    image: 'https://images.unsplash.com/photo-1593642632823-8f785ba67e45?auto=format&fit=crop&w=600&q=80'
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
    image: 'https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?auto=format&fit=crop&w=600&q=80'
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
    image: 'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=600&q=80'
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
    image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80'
  }
]);

const filteredProducts = computed(() => {
  return products.value.filter(p => {
    const matchesSearch = p.nombre.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
                          p.sku.toLowerCase().includes(searchQuery.value.toLowerCase());
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
          <Tag class="w-3.5 h-3.5 text-cyan-300" /> Gran Oferta Omnicanal Grupo E
        </span>
        <h1 class="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight">
          Tecnología de Punta con Entrega Inmediata.
        </h1>
        <p class="text-slate-200 text-sm sm:text-base">
          Explora el catálogo unificado de MaxiConecta. Reserva stock en tiempo real con respaldo seguro de inventarios en sucursales y tienda online.
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
        class="group flex flex-col bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-lg transition-all duration-300"
      >
        <!-- Imagen y Badge -->
        <div class="relative h-48 bg-slate-100 dark:bg-slate-800 overflow-hidden">
          <img
            :src="prod.image"
            :alt="prod.nombre"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          <span class="absolute top-2.5 left-2.5 bg-blue-600/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full backdrop-blur-sm">
            {{ prod.badge }}
          </span>
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
            <h3 class="font-semibold text-sm line-clamp-2 text-slate-800 dark:text-slate-100 group-hover:text-blue-600 transition-colors">
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
              class="p-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm active:scale-95"
              title="Añadir al carrito"
            >
              <ShoppingBag class="w-4 h-4" />
            </button>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>
