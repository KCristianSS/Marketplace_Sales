
<script setup lang="ts">
import { computed } from 'vue';
import { Heart, Trash2, ShoppingBag } from 'lucide-vue-next';
import { useWishlistStore } from '@/stores/wishlist';

const wishlistStore = useWishlistStore();

const tieneDeseos = computed(() => wishlistStore.items.length > 0);

function eliminar(varianteId: string) {
  console.log('Eliminar deseo:', varianteId);
}
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- Encabezado -->
    <section class="bg-white border-b border-slate-200">
      <div class="max-w-7xl mx-auto px-6 py-8">
        <div class="flex items-center gap-3">
          <Heart class="w-8 h-8 text-rose-500" />
          <div>
            <h1 class="text-3xl font-bold text-slate-900">
              Mi lista de deseos
            </h1>
            <p class="text-slate-500 mt-1">
              Guarda los productos que quieres comprar más adelante.
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Contenido -->
    <main class="max-w-7xl mx-auto px-6 py-8">

      <!-- Lista con productos -->
      <div v-if="tieneDeseos" class="space-y-4">

        <article
          v-for="item in wishlistStore.items"
          :key="item.id"
          class="bg-white rounded-xl border border-slate-200 p-5
                 flex items-center justify-between shadow-sm"
        >
          <div>
            <p class="font-semibold text-slate-900">
              Variante: {{ item.variante_id }}
            </p>

            <p class="text-sm text-slate-500 mt-1">
              Agregado:
              {{ new Date(item.created_at).toLocaleDateString() }}
            </p>
          </div>

          <button
            type="button"
            class="p-2 rounded-lg text-rose-500 hover:bg-rose-50"
            title="Eliminar de favoritos"
            @click="eliminar(item.variante_id)"
          >
            <Trash2 class="w-5 h-5" />
          </button>
        </article>

      </div>

      <!-- Lista vacía -->
      <div
        v-else
        class="bg-white rounded-2xl border border-slate-200
               p-12 text-center"
      >
        <div
          class="mx-auto w-16 h-16 rounded-full bg-rose-50
                 flex items-center justify-center"
        >
          <Heart class="w-8 h-8 text-rose-400" />
        </div>

        <h2 class="mt-5 text-xl font-semibold text-slate-900">
          Tu lista de deseos está vacía
        </h2>

        <p class="mt-2 text-slate-500 max-w-md mx-auto">
          Guarda tus productos favoritos para encontrarlos
          fácilmente cuando estés listo para comprarlos.
        </p>

        <button
          type="button"
          class="mt-6 inline-flex items-center gap-2
                 px-5 py-3 rounded-lg
                 bg-slate-900 text-white
                 hover:bg-slate-800"
        >
          <ShoppingBag class="w-5 h-5" />
          Seguir comprando
        </button>
      </div>

    </main>
  </div>
</template>