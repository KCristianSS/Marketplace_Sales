import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ItemCarrito } from '@/types';
import { apiClient } from '@/api/client';

export const useCartStore = defineStore('cart', () => {
  const isDrawerOpen = ref(false);
  const items = ref<ItemCarrito[]>([
    {
      variante_id: 'b0000000-0000-0000-0000-000000000001',
      sku: 'LAP-DELL-XPS15-16GB',
      nombre: 'Laptop Dell XPS 15 (16GB RAM / 512GB SSD)',
      cantidad: 1,
      precio_unitario: 8999.00,
      total_linea: 8999.00
    }
  ]);
  const cupon = ref<string | null>(null);
  const descuento = ref(0);

  const itemCount = computed(() => items.value.reduce((acc, curr) => acc + curr.cantidad, 0));
  const subtotal = computed(() => items.value.reduce((acc, curr) => acc + curr.total_linea, 0));
  const total = computed(() => Math.max(0, subtotal.value - descuento.value));

  function toggleDrawer() {
    isDrawerOpen.value = !isDrawerOpen.value;
  }

  function addItem(item: Omit<ItemCarrito, 'total_linea'>) {
    const existing = items.value.find(i => i.variante_id === item.variante_id);
    if (existing) {
      existing.cantidad += item.cantidad;
      existing.total_linea = existing.cantidad * existing.precio_unitario;
    } else {
      items.value.push({
        ...item,
        total_linea: item.cantidad * item.precio_unitario
      });
    }
    isDrawerOpen.value = true;
  }

  function removeItem(varianteId: string) {
    items.value = items.value.filter(i => i.variante_id !== varianteId);
  }

  function updateQuantity(varianteId: string, delta: number) {
    const item = items.value.find(i => i.variante_id === varianteId);
    if (item) {
      item.cantidad += delta;
      if (item.cantidad <= 0) {
        removeItem(varianteId);
      } else {
        item.total_linea = item.cantidad * item.precio_unitario;
      }
    }
  }

  function aplicarCupon(codigo: string) {
    if (codigo.toUpperCase() === 'MAXI10') {
      cupon.value = 'MAXI10';
      descuento.value = subtotal.value * 0.10;
      return true;
    }
    return false;
  }

  return {
    isDrawerOpen,
    items,
    cupon,
    descuento,
    itemCount,
    subtotal,
    total,
    toggleDrawer,
    addItem,
    removeItem,
    updateQuantity,
    aplicarCupon
  };
});
