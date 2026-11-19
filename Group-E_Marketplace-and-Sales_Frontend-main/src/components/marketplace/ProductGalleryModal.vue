<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { MarketplaceProduct } from '@/types';
import { X, ChevronLeft, ChevronRight, ShoppingBag, SlidersHorizontal, Layers, Tag } from 'lucide-vue-next';
import ProductReviewsPanel from '@/components/ProductReviewsPanel.vue';
import ProductRecommendations from '@/components/ProductRecommendations.vue';

const props = defineProps<{
  product: MarketplaceProduct | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'addToCart', product: MarketplaceProduct): void;
}>();

const currentIndex = ref(0);
const selectedVariantId = ref<string>('');

// Reiniciar índice y variante cuando cambia el producto activo
watch(
  () => props.product,
  (newProd) => {
    currentIndex.value = 0;
    if (newProd?.variantes && newProd.variantes.length > 0) {
      selectedVariantId.value = newProd.variantes[0].id;
    } else {
      selectedVariantId.value = '';
    }
  },
  { immediate: true }
);

const currentImage = computed<string | undefined>(() => {
  if (!props.product) return undefined;
  const imgs = props.product.galleryImages;
  if (!imgs || imgs.length === 0) return props.product.image;
  return imgs[currentIndex.value]?.url || props.product.image;
});

const activeAttributes = computed<Record<string, any>>(() => {
  if (!props.product) return {};
  if (selectedVariantId.value && props.product.variantes) {
    const v = props.product.variantes.find((item) => item.id === selectedVariantId.value);
    if (v && v.atributos && Object.keys(v.atributos).length > 0) {
      return v.atributos;
    }
  }
  return props.product.atributos || {};
});

const activePrice = computed<number>(() => {
  if (!props.product) return 0;
  if (selectedVariantId.value && props.product.variantes) {
    const v = props.product.variantes.find((item) => item.id === selectedVariantId.value);
    if (v && v.precio) return v.precio;
  }
  return props.product.precio;
});

const activeSku = computed<string>(() => {
  if (!props.product) return '';
  if (selectedVariantId.value && props.product.variantes) {
    const v = props.product.variantes.find((item) => item.id === selectedVariantId.value);
    if (v && v.sku) return v.sku;
  }
  return props.product.sku;
});

function prevImage() {
  if (!props.product || !props.product.galleryImages.length) return;
  const len = props.product.galleryImages.length;
  currentIndex.value = (currentIndex.value - 1 + len) % len;
}

function nextImage() {
  if (!props.product || !props.product.galleryImages.length) return;
  const len = props.product.galleryImages.length;
  currentIndex.value = (currentIndex.value + 1) % len;
}

function handleAddToCart() {
  if (props.product) {
    const variant = props.product.variantes?.find((item) => item.id === selectedVariantId.value);
    // El stock se controla por producto: todas sus variantes comparten el SKU del producto.
    const itemToCart: MarketplaceProduct = {
      ...props.product,
      nombre: variant && props.product.variantes!.length > 1
        ? `${props.product.nombre} (${variant.nombre_variante})`
        : props.product.nombre,
      precio: activePrice.value,
      id: selectedVariantId.value || props.product.id
    };
    emit('addToCart', itemToCart);
    emit('close');
  }
}
</script>

<template>
  <div
    v-if="product"
    class="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto"
    @click.self="$emit('close')"
  >
    <div class="bg-white dark:bg-slate-900 rounded-2xl max-w-2xl w-full border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[92vh] my-6">
      <!-- Header del Modal -->
      <div class="p-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
        <div>
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-teal-50 dark:bg-teal-950/60 text-teal-700 dark:text-teal-300 border border-teal-200/60 dark:border-teal-800/60">
              {{ product.categoria }}
            </span>
            <span v-if="product.marca" class="text-xs font-semibold text-slate-400">
              {{ product.marca }}
            </span>
          </div>
          <h3 class="text-sm font-bold text-slate-900 dark:text-white mt-1">{{ product.nombre }}</h3>
          <span class="text-xs text-slate-400 font-mono">SKU: {{ activeSku }}</span>
        </div>
        <button @click="$emit('close')" class="p-1.5 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-500 transition-colors">
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Contenedor Scrollable -->
      <div class="overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
        <!-- Imagen Principal Seleccionada -->
        <div class="relative bg-slate-950 flex items-center justify-center h-72 sm:h-80 overflow-hidden">
          <img
            :src="currentImage"
            :alt="product.nombre"
            class="max-h-full max-w-full object-contain"
          />

          <!-- Botones de Navegación si hay múltiples imágenes -->
          <button
            v-if="product.galleryImages && product.galleryImages.length > 1"
            @click="prevImage"
            class="absolute left-3 p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm transition-colors"
            title="Foto anterior"
          >
            <ChevronLeft class="w-5 h-5" />
          </button>
          <button
            v-if="product.galleryImages && product.galleryImages.length > 1"
            @click="nextImage"
            class="absolute right-3 p-2 rounded-full bg-black/50 hover:bg-black/80 text-white backdrop-blur-sm transition-colors"
            title="Siguiente foto"
          >
            <ChevronRight class="w-5 h-5" />
          </button>
        </div>

        <!-- Tira de Miniaturas (Thumbnails) -->
        <div
          v-if="product.galleryImages && product.galleryImages.length > 0"
          class="p-3 bg-slate-50 dark:bg-slate-950 flex gap-2 overflow-x-auto"
        >
          <button
            v-for="(img, idx) in product.galleryImages"
            :key="img.id"
            @click="currentIndex = idx"
            :class="[
              'w-14 h-14 rounded-xl border-2 overflow-hidden shrink-0 transition-all',
              currentIndex === idx
                ? 'border-teal-600 ring-2 ring-teal-500/20 scale-105'
                : 'border-transparent opacity-70 hover:opacity-100'
            ]"
          >
            <img :src="img.url" class="w-full h-full object-cover" alt="Thumbnail" />
          </button>
        </div>

        <!-- Selector de Variantes (si tiene más de 1 opción) -->
        <div
          v-if="product.variantes && product.variantes.length > 1"
          class="p-4 bg-white dark:bg-slate-900 space-y-2"
        >
          <label class="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
            <Tag class="w-3.5 h-3.5 text-teal-600" />
            Opciones y Variantes Disponibles:
          </label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="v in product.variantes"
              :key="v.id"
              type="button"
              @click="selectedVariantId = v.id"
              :class="[
                'px-3 py-1.5 rounded-xl text-xs font-bold border transition-all text-left',
                selectedVariantId === v.id
                  ? 'bg-teal-50 dark:bg-teal-950/60 border-teal-600 text-teal-800 dark:text-teal-200 ring-2 ring-teal-500/20'
                  : 'bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-slate-400'
              ]"
            >
              <div>{{ v.nombre_variante }}</div>
              <div class="text-[10px] text-slate-400 font-mono">BOB {{ v.precio.toFixed(2) }}</div>
            </button>
          </div>
        </div>

        <!-- Bloque de Atributos y Especificaciones Técnicas de la Jerarquía -->
        <div
          v-if="activeAttributes && Object.keys(activeAttributes).length > 0"
          class="p-4 bg-slate-50/60 dark:bg-slate-950/40 space-y-2.5"
        >
          <div class="flex items-center gap-2">
            <SlidersHorizontal class="w-4 h-4 text-teal-600 dark:text-teal-400" />
            <h4 class="text-xs font-extrabold uppercase tracking-wider text-slate-800 dark:text-slate-200">
              Especificaciones y Atributos Técnicos
            </h4>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            <div
              v-for="(val, key) in activeAttributes"
              :key="key"
              class="p-2.5 bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-xl shadow-xs"
            >
              <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider block truncate" :title="String(key)">
                {{ key }}
              </span>
              <span class="text-xs font-extrabold text-slate-800 dark:text-slate-100 block mt-0.5">
                {{ val }}
              </span>
            </div>
          </div>
        </div>

        <!-- Descripción del Producto -->
        <div v-if="product.descripcion" class="p-4 bg-white dark:bg-slate-900 space-y-1">
          <h4 class="text-xs font-bold text-slate-700 dark:text-slate-300">Descripción del Artículo</h4>
          <p class="text-xs text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-line">
            {{ product.descripcion }}
          </p>
        </div>

        <!-- Panel de Reseñas de Clientes (RF-33) -->
        <div class="p-4 bg-slate-50/50 dark:bg-slate-950/50 border-t border-slate-200 dark:border-slate-800">
          <ProductReviewsPanel :producto-id="product.id" />
        </div>

        <!-- Recomendaciones Inteligentes y Bundle Frecuente (KAN-35 / RF-19) -->
        <div class="p-5 sm:p-6 border-t border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/40">
          <ProductRecommendations
            :product-id="product.id"
            :product-sku="product.sku"
            :product-title="product.nombre"
          />
        </div>
      </div>

      <!-- Footer con Acción de Compra -->
      <div class="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50/50 dark:bg-slate-950/50">
        <div>
          <span class="text-xs text-slate-400 block font-medium">Precio Contado</span>
          <span class="text-xl font-black text-teal-700 dark:text-teal-400">
            BOB {{ activePrice.toLocaleString('es-BO', { minimumFractionDigits: 2 }) }}
          </span>
        </div>
        <button
          @click="handleAddToCart"
          class="px-5 py-2.5 bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold rounded-xl shadow-md flex items-center gap-2 transition-colors active:scale-95 disabled:opacity-50"
          :disabled="product.stock === 0"
        >
          <ShoppingBag class="w-4 h-4" />
          <span>{{ product.stock === 0 ? 'Agotado' : 'Añadir al Carrito' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
