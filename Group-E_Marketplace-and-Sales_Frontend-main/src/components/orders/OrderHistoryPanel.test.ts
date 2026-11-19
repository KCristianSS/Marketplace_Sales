// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import OrderHistoryPanel from './OrderHistoryPanel.vue';
import { useCartStore } from '@/stores/cart';
import { obtenerHistorialOrdenes, obtenerOrden, prepararRecompra } from '@/api/ordenes';
import type { OrdenHistorial } from '@/types';

vi.mock('@/api/ordenes', () => ({
  obtenerHistorialOrdenes: vi.fn(), obtenerOrden: vi.fn(), prepararRecompra: vi.fn(),
  cambiarEstadoOrden: vi.fn(), descargarFacturaXml: vi.fn(), obtenerFacturaImpresion: vi.fn(),
}));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/api/catalogo', () => ({ consultarStock: vi.fn() }));
vi.mock('@/api/cupones', () => ({ validarCupon: vi.fn(), canjearCupon: vi.fn() }));

const pedido = {
  id: 'orden', codigo_orden: 'ORD-123', cliente_id: 'cliente', canal: 'web', estado: 'entregada',
  tipo_despacho: 'domicilio', subtotal: 10, descuento: 0, costo_envio: 0, total: 10,
  created_at: '2026-11-04T12:00:00Z', pagos: [],
  items: [{ id: 'linea', variante_id: 'variante', sku: 'SKU', nombre_producto: 'Habitual', cantidad: 1, precio_unitario: 10, total_linea: 10 }],
} as OrdenHistorial;

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); vi.resetAllMocks();
  setActivePinia(createPinia());
  vi.mocked(obtenerHistorialOrdenes).mockResolvedValue({ items: [pedido], total: 1, pagina: 1, limite: 10, total_paginas: 1 });
  vi.mocked(obtenerOrden).mockResolvedValue(pedido);
  vi.mocked(prepararRecompra).mockResolvedValue({ orden_id: 'orden', avisos: [], items: [{
    variante_id: 'variante', variante_original_id: 'variante', sku: 'SKU', nombre: 'Habitual',
    cantidad: 1, precio_unitario: 12, stock_disponible: 5,
  }] });
});

const opciones = { global: { stubs: { RouterLink: true, DispatchPanel: true } } };

describe('acción de recompra en el historial', () => {
  it('agrega al carrito con un clic desde el historial', async () => {
    const wrapper = mount(OrderHistoryPanel, opciones);
    await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Repetir pedido')!.trigger('click');
    await flushPromises();
    expect(prepararRecompra).toHaveBeenCalledWith('orden');
    expect(useCartStore().items[0]).toMatchObject({ cantidad: 1, precio_unitario: 12 });
    expect(useCartStore().isDrawerOpen).toBe(true);
    wrapper.unmount();
  });

  it('permite repetir desde el detalle y lo cierra al abrir el carrito', async () => {
    const wrapper = mount(OrderHistoryPanel, opciones);
    await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Ver detalle')!.trigger('click');
    await flushPromises();
    await wrapper.find('[role="dialog"]').findAll('button').find(b => b.text() === 'Repetir pedido')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(useCartStore().itemCount).toBe(1);
    wrapper.unmount();
  });

  it('muestra el error en el detalle y conserva el carrito', async () => {
    vi.mocked(prepararRecompra).mockRejectedValue({ response: { data: { detail: 'Catálogo temporalmente no disponible' } } });
    const wrapper = mount(OrderHistoryPanel, opciones);
    await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Ver detalle')!.trigger('click');
    await flushPromises();
    await wrapper.find('[role="dialog"]').findAll('button').find(b => b.text() === 'Repetir pedido')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="dialog"] [role="alert"]').text()).toContain('Catálogo temporalmente no disponible');
    expect(useCartStore().items).toEqual([]);
    wrapper.unmount();
  });

  it('no muestra recompra en el historial administrativo ni en su detalle', async () => {
    const wrapper = mount(OrderHistoryPanel, { ...opciones, props: { scope: 'administrador' } });
    await flushPromises();
    expect(wrapper.findAll('button').some(b => b.text() === 'Repetir pedido')).toBe(false);
    await wrapper.findAll('button').find(b => b.text() === 'Ver detalle')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="dialog"]').text()).not.toContain('Repetir pedido');
    wrapper.unmount();
  });
});


it('muestra las órdenes POS sin cliente identificado en el historial administrativo', async () => {
  vi.mocked(obtenerHistorialOrdenes).mockResolvedValue({ items: [{ ...pedido, cliente_id: null, canal: 'pos' }], total: 1, pagina: 1, limite: 10, total_paginas: 1 });
  const wrapper = mount(OrderHistoryPanel, { ...opciones, props: { scope: 'administrador' } });
  await flushPromises();
  expect(wrapper.text()).toContain('Cliente no identificado');
  expect(wrapper.text()).toContain('ORD-123');
  wrapper.unmount();
});
