<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { 
  Heart, 
  Trash2, 
  ShoppingBag, 
  ArrowRight, 
  Sparkles, 
  Check, 
  Layers, 
  AlertCircle,
  Tag
} from 'lucide-vue-next';
import { useWishlistStore } from '@/stores/wishlist';
import { useAuthStore } from '@/stores/auth';
import type { WishlistItem } from '@/types';

const router = useRouter();
const wishlistStore = useWishlistStore();
const authStore = useAuthStore();

const toastMessage = ref('');
let toastTimer: ReturnType<typeof setTimeout> | null = null;

function showToast(msg: string) {
  toastMessage.value = msg;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastMessage.value = '';
  }, 3500);
}

const tieneDeseos = computed(() => wishlistStore.items.length > 0);

const totalEstimado = computed(() => {
  return wishlistStore.items.reduce((acc, item) => acc + (item.precio || 0), 0);
});

onMounted(() => {
  wishlistStore.cargarDeseos(authStore.user?.id);
});

async function handleMoverAlCarrito(item: WishlistItem) {
  const exito = await wishlistStore.moverAlCarrito(item.variante_id, authStore.user?.id);
  if (exito) {
    showToast(`"${item.nombre || 'Producto'}" se movió al carrito de compras.`);
  }
}

async function handleMoverTodosAlCarrito() {
  const total = await wishlistStore.moverTodosAlCarrito(authStore.user?.id);
  if (total > 0) {
    showToast(`¡Se movieron ${total} producto(s) al carrito de compras!`);
  }
}

function handleEliminar(varianteId: string) {
  wishlistStore.eliminarDeseo(varianteId, authStore.user?.id);
  showToast('Producto eliminado de la lista de deseos.');
}

function handleVaciarLista() {
  if (confirm('¿Estás seguro de que deseas vaciar tu lista de deseos?')) {
    wishlistStore.vaciarLista(authStore.user?.id);
    showToast('Lista de deseos vaciada.');
  }
}

function irAlMarketplace() {
  router.push('/marketplace');
}
</script>

<template>
  <div class="space-y-6 max-w-6xl mx-auto py-2">
    <!-- Toast flotante de retroalimentación -->
    <transition
      enter-active-class="transform transition ease-out duration-300"
      enter-from-class="translate-y-2 opacity-0 sm:translate-y-0 sm:translate-x-2"
      enter-to-class="translate-y-0 opacity-100 sm:translate-x-0"
      leave-active-class="transition ease-in duration-100"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div 
        v-if="toastMessage" 
        class="fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 text-sm font-semibold"
      >
        <span class="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
          <Check class="w-4 h-4 text-emerald-400" />
        </span>
        <span>{{ toastMessage }}</span>
      </div>
    </transition>

    <!-- Encabezado con Hero Banner Suave -->
    <section class="relative overflow-hidden rounded-3xl bg-gradient-to-br from-rose-50 via-pink-50/60 to-purple-50 dark:from-slate-900 dark:via-rose-950/20 dark:to-slate-900 p-6 sm:p-8 border border-rose-100 dark:border-rose-950/50 shadow-sm">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-6 relative z-10">
        <div class="flex items-start gap-4">
          <div class="w-12 h-12 rounded-2xl bg-gradient-to-tr from-rose-500 to-pink-500 text-white flex items-center justify-center shadow-lg shadow-rose-500/20 shrink-0">
            <Heart class="w-6 h-6 fill-white" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                Mi Lista de Deseos
              </h1>
              <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900">
                {{ wishlistStore.itemCount }} {{ wishlistStore.itemCount === 1 ? 'producto' : 'productos' }}
              </span>
            </div>
            <p class="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-xl">
              Tus artículos favoritos guardados para revisitarlos y reservarlos para futuras decisiones de compra.
            </p>
          </div>
        </div>

        <!-- Acciones Masivas (Criterio US-21) -->
        <div v-if="tieneDeseos" class="flex flex-wrap items-center gap-2.5 shrink-0">
          <button
            type="button"
            @click="handleMoverTodosAlCarrito"
            class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 hover:scale-[1.02] active:scale-[0.98] transition-all"
          >
            <ShoppingBag class="w-4 h-4" />
            Mover todos al Carrito
          </button>
          
          <button
            type="button"
            @click="handleVaciarLista"
            class="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-xl bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 font-semibold text-xs border border-slate-200 dark:border-slate-700 transition-colors"
            title="Vaciar lista"
          >
            <Trash2 class="w-3.5 h-3.5 text-slate-400 hover:text-rose-500" />
            Vaciar lista
          </button>
        </div>
      </div>

      <!-- Resumen rápido si hay items -->
      <div v-if="tieneDeseos" class="mt-6 pt-4 border-t border-rose-200/50 dark:border-rose-900/40 flex flex-wrap items-center justify-between text-xs text-slate-600 dark:text-slate-400 gap-2">
        <span class="flex items-center gap-1.5">
          <Sparkles class="w-4 h-4 text-amber-500" />
          Valor total estimado de tus favoritos: 
          <strong class="text-slate-900 dark:text-slate-100 font-bold text-sm">Bs. {{ totalEstimado.toFixed(2) }}</strong>
        </span>
        <span class="text-[11px] text-slate-400">
          Los precios reflejan tarifas actuales del catálogo.
        </span>
      </div>
    </section>

    <!-- Estado: Lista con productos -->
    <div v-if="tieneDeseos" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <article
        v-for="item in wishlistStore.items"
        :key="item.variante_id"
        class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-sm hover:shadow-md transition-all flex flex-col justify-between group"
      >
        <div class="space-y-3">
          <!-- Imagen y Botón Quitar -->
          <div class="relative w-full h-48 rounded-xl bg-slate-100 dark:bg-slate-800 overflow-hidden flex items-center justify-center">
            <img
              v-if="item.imagen_url"
              :src="item.imagen_url"
              :alt="item.nombre"
              class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
            <div v-else class="flex flex-col items-center justify-center text-slate-400 gap-2">
              <Layers class="w-8 h-8 opacity-40" />
              <span class="text-[11px]">Sin vista previa</span>
            </div>

            <button
              type="button"
              class="absolute top-2.5 right-2.5 p-2 rounded-full bg-white/90 dark:bg-slate-900/90 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/50 shadow-sm backdrop-blur-sm transition-transform active:scale-90"
              title="Quitar de mi lista de deseos"
              @click="handleEliminar(item.variante_id)"
            >
              <Trash2 class="w-4 h-4" />
            </button>

            <span class="absolute bottom-2.5 left-2.5 bg-black/60 backdrop-blur-sm text-white text-[10px] font-mono px-2 py-0.5 rounded-md">
              SKU: {{ item.sku || 'VARI-01' }}
            </span>
          </div>

          <!-- Información del Producto -->
          <div>
            <h3 class="font-bold text-slate-900 dark:text-white text-base line-clamp-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
              {{ item.nombre || 'Producto sin nombre' }}
            </h3>

            <div class="flex items-center justify-between mt-2">
              <div>
                <span class="text-[10px] text-slate-400 uppercase tracking-wider block font-semibold">Precio</span>
                <span class="text-lg font-black text-slate-900 dark:text-white">
                  Bs. {{ (item.precio || 0).toFixed(2) }}
                </span>
              </div>

              <div class="text-right">
                <span class="text-[10px] text-slate-400 block">Guardado</span>
                <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">
                  {{ new Date(item.created_at).toLocaleDateString('es-BO', { month: 'short', day: 'numeric' }) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Botón de Acción Principal: Mover al Carrito -->
        <div class="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-2">
          <button
            type="button"
            @click="handleMoverAlCarrito(item)"
            class="flex-1 inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-600 hover:text-white text-blue-600 dark:text-blue-400 font-bold text-xs border border-blue-200 dark:border-blue-900/60 hover:border-transparent transition-all group-hover:shadow-sm"
          >
            <ShoppingBag class="w-4 h-4" />
            Mover al Carrito
          </button>
        </div>
      </article>
    </div>

    <!-- Estado: Lista Vacía -->
    <div
      v-else
      class="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-12 text-center shadow-sm space-y-5"
    >
      <div class="mx-auto w-20 h-20 rounded-3xl bg-rose-50 dark:bg-rose-950/40 text-rose-500 flex items-center justify-center border border-rose-100 dark:border-rose-900/60 shadow-inner">
        <Heart class="w-10 h-10 stroke-[1.5]" />
      </div>

      <div class="max-w-md mx-auto space-y-2">
        <h2 class="text-xl font-bold text-slate-900 dark:text-white">
          Tu lista de deseos está vacía
        </h2>
        <p class="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
          Explora nuestro catálogo y haz clic en el icono del corazón en cualquier producto para guardarlo aquí y comprarlo cuando estés listo.
        </p>
      </div>

      <div class="pt-2">
        <button
          type="button"
          @click="irAlMarketplace"
          class="inline-flex items-center gap-2 px-6 py-3 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-sm shadow-lg shadow-blue-500/25 hover:scale-105 active:scale-95 transition-all"
        >
          <ShoppingBag class="w-4 h-4" />
          Explorar Catálogo
          <ArrowRight class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>