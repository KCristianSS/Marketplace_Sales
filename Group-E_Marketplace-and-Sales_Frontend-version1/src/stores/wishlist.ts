
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { WishlistItem } from '@/types';
import { apiClient } from '@/api/client';

export const useWishlistStore = defineStore('wishlist', () => {
  const items = ref<WishlistItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const itemCount = computed(() => items.value.length);

  async function cargarDeseos(clienteId: string) {
    loading.value = true;
    error.value = null;

    try {
      const response = await apiClient.get<WishlistItem[]>(
        `/api/v1/carrito/${clienteId}/deseos`
      );

      items.value = response.data;
    } catch (err) {
      console.error('Error al cargar la lista de deseos:', err);
      error.value = 'No se pudo cargar la lista de deseos.';
    } finally {
      loading.value = false;
    }
  }

  async function agregarDeseo(clienteId: string, varianteId: string) {
    error.value = null;

    try {
      const response = await apiClient.post<WishlistItem>(
        `/api/v1/carrito/${clienteId}/deseos`,
        {
          variante_id: varianteId
        }
      );

      items.value.push(response.data);

      return true;
    } catch (err) {
      console.error('Error al agregar a la lista de deseos:', err);
      error.value = 'No se pudo agregar el producto a la lista de deseos.';

      return false;
    }
  }

  async function eliminarDeseo(
    clienteId: string,
    varianteId: string
  ) {
    error.value = null;

    try {
      await apiClient.delete(
        `/api/v1/carrito/${clienteId}/deseos/${varianteId}`
      );

      items.value = items.value.filter(
        item => item.variante_id !== varianteId
      );

      return true;
    } catch (err) {
      console.error('Error al eliminar de la lista de deseos:', err);
      error.value = 'No se pudo eliminar el producto de la lista de deseos.';

      return false;
    }
  }

  function estaEnDeseos(varianteId: string) {
    return items.value.some(
      item => item.variante_id === varianteId
    );
  }

  return {
    items,
    loading,
    error,
    itemCount,
    cargarDeseos,
    agregarDeseo,
    eliminarDeseo,
    estaEnDeseos
  };
});