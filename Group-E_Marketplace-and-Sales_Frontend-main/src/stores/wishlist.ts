import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { WishlistItem } from '@/types';
import { apiClient } from '@/api/client';
import { useCartStore } from '@/stores/cart';
import { consultarStock } from '@/api/catalogo';

const STORAGE_KEY_WISHLIST = 'maxiconecta_wishlist_items';
const STORAGE_KEY_GUEST_WISHLIST = `${STORAGE_KEY_WISHLIST}:guest`;

function isValidUuid(id?: string): boolean {
  if (!id) return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

function loadSavedWishlist(clienteId?: string): WishlistItem[] {
  try {
    const key = clienteId ? `${STORAGE_KEY_WISHLIST}:${clienteId}` : STORAGE_KEY_GUEST_WISHLIST;
    const raw = localStorage.getItem(key) ?? (!clienteId ? localStorage.getItem(STORAGE_KEY_WISHLIST) : null);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export const useWishlistStore = defineStore('wishlist', () => {
  const activeClienteId = ref<string | undefined>();
  const items = ref<WishlistItem[]>(loadSavedWishlist());
  const loading = ref(false);
  const error = ref<string | null>(null);

  const itemCount = computed(() => items.value.length);

  function persistirLocal() {
    try {
      const key = activeClienteId.value
        ? `${STORAGE_KEY_WISHLIST}:${activeClienteId.value}`
        : STORAGE_KEY_GUEST_WISHLIST;
      localStorage.setItem(key, JSON.stringify(items.value));
    } catch (err) {
      console.warn('Error guardando lista de deseos localmente:', err);
    }
  }

  /**
   * RF-21: Carga la lista persistida del cliente autenticado. Cada cliente
   * tiene una caché local separada y la lista remota es la fuente de verdad.
   */
  async function cargarDeseos(clienteId?: string) {
    activeClienteId.value = clienteId && isValidUuid(clienteId) ? clienteId : undefined;
    items.value = loadSavedWishlist(activeClienteId.value);

    if (!clienteId || !isValidUuid(clienteId)) {
      return;
    }

    loading.value = true;
    error.value = null;

    try {
      const response = await apiClient.get<WishlistItem[]>(
        `/api/v1/carrito/${clienteId}/deseos`
      );

      if (activeClienteId.value === clienteId && Array.isArray(response.data)) {
        const localMap = new Map(items.value.map(i => [i.variante_id, i]));
        items.value = response.data.map(remote => {
          const local = localMap.get(remote.variante_id);
          return {
            ...remote,
            nombre: remote.nombre || local?.nombre || 'Producto Favorito',
            sku: remote.sku || local?.sku || 'SKU-ITEM',
            precio: remote.precio !== undefined ? Number(remote.precio) : (local?.precio ?? 0),
            imagen_url: remote.imagen_url || local?.imagen_url || '',
          };
        });
        persistirLocal();
      }
    } catch (err) {
      if (activeClienteId.value === clienteId) {
        error.value = 'No se pudo cargar tu lista de deseos. Inténtalo nuevamente.';
        console.warn(error.value, err);
      }
    } finally {
      loading.value = false;
    }
  }

  /**
   * RF-21: Agrega un producto a la lista de deseos de forma reactiva e inmediata.
   */
  async function agregarDeseo(
    producto: {
      id: string;
      sku?: string;
      nombre?: string;
      precio?: number;
      image?: string;
      variante_id?: string;
    },
    clienteId?: string
  ): Promise<boolean> {
    error.value = null;
    const varianteId = producto.variante_id || producto.id;

    if (estaEnDeseos(varianteId)) {
      return true;
    }

    const nuevoItem: WishlistItem = {
      id: crypto.randomUUID(),
      cliente_id: clienteId,
      variante_id: varianteId,
      sku: producto.sku || 'SKU-FAV',
      nombre: producto.nombre || 'Producto Favorito',
      precio: producto.precio ?? 0,
      imagen_url: producto.image || '',
      created_at: new Date().toISOString()
    };

    if (clienteId && isValidUuid(clienteId)) {
      try {
        const response = await apiClient.post<WishlistItem>(
          `/api/v1/carrito/${clienteId}/deseos`,
          { variante_id: varianteId }
        );
        const savedItem = { ...nuevoItem, ...response.data };
        items.value.unshift(savedItem);
        persistirLocal();
        return true;
      } catch (err) {
        error.value = 'No se pudo guardar el producto en tu lista de deseos.';
        console.warn(error.value, err);
        return false;
      }
    }

    items.value.unshift(nuevoItem);
    persistirLocal();
    return true;
  }

  /**
   * RF-21: Elimina un producto de la lista de deseos.
   */
  async function eliminarDeseo(varianteId: string, clienteId?: string): Promise<boolean> {
    error.value = null;

    if (clienteId && isValidUuid(clienteId)) {
      try {
        await apiClient.delete(`/api/v1/carrito/${clienteId}/deseos/${varianteId}`);
      } catch (err) {
        error.value = 'No se pudo quitar el producto de tu lista de deseos.';
        console.warn(error.value, err);
        return false;
      }
    }

    items.value = items.value.filter(item => item.variante_id !== varianteId);
    persistirLocal();
    return true;
  }

  /**
   * Alterna el estado de un producto (agregar si no está, quitar si ya está).
   */
  async function alternarDeseo(producto: any, clienteId?: string): Promise<boolean> {
    const varianteId = producto.variante_id || producto.id;
    if (estaEnDeseos(varianteId)) {
      const removed = await eliminarDeseo(varianteId, clienteId);
      return removed ? false : true; // Conserva estado visual si el servidor rechaza el cambio
    } else {
      const added = await agregarDeseo(producto, clienteId);
      return added; // Conserva estado visual si el servidor rechaza el cambio
    }
  }

  /**
   * US-21: Mover un producto individual de la lista de deseos al carrito.
   */
  async function moverAlCarrito(varianteId: string, clienteId?: string): Promise<boolean> {
    const item = items.value.find(i => i.variante_id === varianteId);
    if (!item) return false;

    const cartStore = useCartStore();
    try {
      const sku = item.sku || '';
      const stock = await consultarStock(sku);
      const added = cartStore.addItem({
        variante_id: item.variante_id,
        sku,
        nombre: item.nombre || 'Producto',
        cantidad: 1,
        precio_unitario: item.precio || 0,
        stock_disponible: stock.stock_disponible
      });
      if (!added) return false;
    } catch {
      cartStore.error = `No se pudo verificar el stock de ${item.nombre || 'este producto'}.`;
      cartStore.openDrawer();
      return false;
    }

    eliminarDeseo(varianteId, clienteId);
    return true;
  }

  /**
   * US-21 / Criterio de Aceptación:
   * Acción masiva "Mover todos al Carrito".
   */
  async function moverTodosAlCarrito(clienteId?: string): Promise<number> {
    if (items.value.length === 0) return 0;

    let count = 0;
    for (const item of [...items.value]) {
      if (await moverAlCarrito(item.variante_id, clienteId)) count++;
    }

    return count;
  }

  function estaEnDeseos(varianteId: string): boolean {
    return items.value.some(item => item.variante_id === varianteId);
  }

  function vaciarLista(clienteId?: string) {
    const todos = [...items.value];
    items.value = [];
    persistirLocal();

    if (clienteId && isValidUuid(clienteId)) {
      for (const item of todos) {
        apiClient.delete(`/api/v1/carrito/${clienteId}/deseos/${item.variante_id}`).catch(() => {});
      }
    }
  }

  return {
    items,
    loading,
    error,
    itemCount,
    cargarDeseos,
    agregarDeseo,
    eliminarDeseo,
    alternarDeseo,
    moverAlCarrito,
    moverTodosAlCarrito,
    estaEnDeseos,
    vaciarLista
  };
});
