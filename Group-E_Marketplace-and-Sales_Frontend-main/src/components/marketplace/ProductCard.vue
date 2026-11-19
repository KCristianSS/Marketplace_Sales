<script setup lang="ts">
import type { MarketplaceProduct } from '@/types';
import { Heart, Layers, Star, ShoppingBag } from 'lucide-vue-next';
import StockBadge from '@/components/StockBadge.vue';

defineProps<{
  product: MarketplaceProduct;
  isInWishlist: boolean;
}>();

defineEmits<{
  (e: 'openGallery', product: MarketplaceProduct): void;
  (e: 'toggleWishlist', product: MarketplaceProduct): void;
  (e: 'addToCart', product: MarketplaceProduct): void;
}>();
</script>

<template>
  <article
    class="reveal-up group flex flex-col bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/90 dark:border-slate-800 overflow-hidden shadow-sm hover:-translate-y-1.5 hover:shadow-xl hover:shadow-teal-900/10 transition-all duration-300"
  >
    <!-- Imagen de Portada y Galería -->
    <div class="relative h-56 bg-slate-100 dark:bg-slate-950 overflow-hidden">
      <img
        :src="product.image"
        :alt="product.nombre"
        class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 cursor-pointer"
        @click="$emit('openGallery', product)"
      />
      
      <button
        type="button"
        :class="[
          'absolute top-2.5 right-2.5 p-2 rounded-full bg-white/90 hover:bg-white shadow-sm backdrop-blur-sm transition-colors z-10',
          isInWishlist ? 'text-rose-500' : 'text-slate-500 hover:text-rose-500'
        ]"
        :title="isInWishlist ? 'Quitar de lista de deseos' : 'Agregar a lista de deseos'"
        @click="$emit('toggleWishlist', product)"
      >
        <Heart :class="['w-4 h-4', isInWishlist ? 'fill-current' : '']" />
      </button>
      
      <span class="absolute top-2.5 left-2.5 bg-teal-700/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full backdrop-blur-sm z-10">
        {{ product.badge }}
      </span>

      <!-- Indicador de Galería si tiene más fotos -->
      <button
        v-if="product.galleryImages && product.galleryImages.length > 0"
        @click="$emit('openGallery', product)"
        class="absolute bottom-2.5 left-2.5 bg-black/60 hover:bg-black/80 text-white text-[10px] font-semibold px-2 py-1 rounded-md flex items-center gap-1 backdrop-blur-sm shadow z-10"
        title="Ver galería completa"
      >
        <Layers class="w-3 h-3 text-cyan-400" />
        <span>{{ product.galleryImages.length }} fotos</span>
      </button>

      <div class="absolute bottom-2.5 right-2.5 bg-black/60 text-white text-xs px-2 py-0.5 rounded-md flex items-center gap-1 backdrop-blur-sm z-10">
        <Star class="w-3 h-3 text-amber-400 fill-amber-400" />
        <span>{{ product.rating }}</span>
      </div>
    </div>

    <!-- Contenido de la Tarjeta -->
    <div class="p-4 flex-1 flex flex-col justify-between space-y-3">
      <div>
        <div class="flex items-center justify-between gap-2">
          <span class="text-[11px] font-bold text-teal-700 dark:text-teal-400 uppercase tracking-wider">
            {{ product.categoria }}
          </span>
          <span v-if="product.marca" class="text-[11px] font-semibold text-slate-400">
            {{ product.marca }}
          </span>
        </div>
        <h3 
          @click="$emit('openGallery', product)"
          class="font-bold text-sm line-clamp-2 text-slate-800 dark:text-slate-100 group-hover:text-teal-700 dark:group-hover:text-teal-400 transition-colors cursor-pointer mt-1"
        >
          {{ product.nombre }}
        </h3>
        <div class="flex items-center justify-between text-[11px] text-slate-400 font-mono mt-1">
          <span>SKU: {{ product.sku }}</span>
          <span :class="product.stock > 0 ? 'text-emerald-600 font-semibold' : product.stock === 0 ? 'text-rose-500 font-semibold' : 'text-slate-400 font-semibold'">
            {{ product.stock > 0 ? `${product.stock} disp.` : product.stock === 0 ? 'Agotado' : 'Consultar stock' }}
          </span>
        </div>
        <!-- RF-07: Badge reactivo de disponibilidad (RIO-INV-01 + caché Redis 30s) -->
        <div class="mt-1.5">
          <StockBadge :sku="product.sku" />
        </div>

        <!-- Atributos Dinámicos de la Jerarquía / Variante -->
        <div v-if="product.atributos && Object.keys(product.atributos).length > 0" class="flex flex-wrap gap-1 mt-2">
          <span
            v-for="([key, val]) in Object.entries(product.atributos).slice(0, 3)"
            :key="key"
            class="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/80"
          >
            <span class="text-slate-400 font-normal mr-1">{{ key }}:</span> {{ val }}
          </span>
          <span
            v-if="Object.keys(product.atributos).length > 3"
            class="text-[10px] text-teal-600 dark:text-teal-400 font-bold self-center cursor-pointer hover:underline"
            @click="$emit('openGallery', product)"
          >
            +{{ Object.keys(product.atributos).length - 3 }} más
          </span>
        </div>
      </div>

      <!-- Precio y Acción de Compra -->
      <div class="pt-2.5 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <div>
          <span class="text-[10px] uppercase tracking-wider text-slate-400 block font-semibold">Precio Contado</span>
          <span class="text-lg font-black text-slate-900 dark:text-white">
            BOB {{ product.precio.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}
          </span>
        </div>
        <button
          @click="$emit('addToCart', product)"
          class="p-2.5 bg-teal-700 hover:bg-teal-800 text-white rounded-xl shadow-md active:scale-95 transition-all disabled:bg-slate-300 disabled:cursor-not-allowed disabled:active:scale-100"
          :title="product.stock === 0 ? 'Producto agotado' : 'Verificar stock y añadir al carrito'"
          :disabled="product.stock === 0"
        >
          <ShoppingBag class="w-4 h-4" />
        </button>
      </div>
    </div>
  </article>
</template>
