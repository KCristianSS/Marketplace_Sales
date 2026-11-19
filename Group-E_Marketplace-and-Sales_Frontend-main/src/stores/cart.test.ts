// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { nextTick } from 'vue';
import { useCartStore } from './cart';
import { prepararRecompra } from '@/api/ordenes';
import type { RecompraResponse } from '@/types';

vi.mock('@/api/ordenes', () => ({ prepararRecompra: vi.fn() }));
vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/api/catalogo', () => ({ consultarStock: vi.fn() }));
vi.mock('@/api/cupones', () => ({ validarCupon: vi.fn(), canjearCupon: vi.fn() }));

const respuesta = (): RecompraResponse => ({ orden_id: 'pedido', avisos: ['Precio actualizado.'], items: [{
  variante_id: 'variante', variante_original_id: 'producto', sku: 'SKU', nombre: 'Habitual',
  cantidad: 3, precio_unitario: 12.5, stock_disponible: 4,
}] });
const existente = (cantidad = 2) => ({ variante_id: 'producto', sku: 'SKU', nombre: 'Anterior',
  cantidad, precio_unitario: 10, total_linea: cantidad * 10, stock_disponible: 10 });

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  setActivePinia(createPinia());
  vi.resetAllMocks();
  vi.mocked(prepararRecompra).mockResolvedValue(respuesta());
});

describe('repetir un pedido', () => {
  it('agrega productos actuales, abre el carrito y persiste la recompra', async () => {
    const cart = useCartStore();
    expect(await cart.repetirPedido('pedido')).toBe(true);
    expect(cart.items[0]).toMatchObject({ cantidad: 3, precio_unitario: 12.5, total_linea: 37.5 });
    expect(cart.isDrawerOpen).toBe(true);
    expect(cart.recompraResumen?.agregados).toBe(3);
    await nextTick();
    expect(JSON.parse(localStorage.getItem('maxiconecta_cart_items')!)[0].cantidad).toBe(3);
  });

  it('conserva otros productos, suma cantidades y actualiza precio sin superar stock', async () => {
    const cart = useCartStore();
    cart.items = [existente(), { ...existente(1), variante_id: 'otro', sku: 'OTRO' }];
    await cart.repetirPedido('pedido');
    expect(cart.items).toHaveLength(2);
    expect(cart.items[0]).toMatchObject({ cantidad: 4, precio_unitario: 12.5, total_linea: 50 });
    expect(cart.items[1].cantidad).toBe(1);
    expect(cart.recompraResumen?.agregados).toBe(2);
    expect(cart.recompraResumen?.avisos.join(' ')).toContain('se agregaron 2 de 3');
  });

  it('limita el stock compartido entre líneas con el mismo SKU', async () => {
    const cart = useCartStore();
    cart.items = [existente(3), { ...existente(1), variante_id: 'otra-variante' }];
    const antes = JSON.stringify(cart.items);
    await cart.repetirPedido('pedido');
    expect(JSON.stringify(cart.items)).toBe(antes);
    expect(cart.recompraResumen?.agregados).toBe(0);
  });

  it('informa productos omitidos y mantiene el carrito si todos están agotados', async () => {
    vi.mocked(prepararRecompra).mockResolvedValue({ orden_id: 'pedido', items: [], avisos: ['Habitual está agotado.'] });
    const cart = useCartStore();
    cart.items = [existente()];
    const antes = JSON.stringify(cart.items);
    await cart.repetirPedido('pedido');
    expect(JSON.stringify(cart.items)).toBe(antes);
    expect(cart.recompraResumen).toEqual({ agregados: 0, avisos: ['Habitual está agotado.'] });
  });

  it('evita duplicaciones por doble clic mientras la solicitud está en curso', async () => {
    let resolver!: (data: RecompraResponse) => void;
    vi.mocked(prepararRecompra).mockReturnValue(new Promise(resolve => { resolver = resolve; }));
    const cart = useCartStore();
    const primera = cart.repetirPedido('pedido');
    expect(await cart.repetirPedido('pedido')).toBe(false);
    expect(prepararRecompra).toHaveBeenCalledTimes(1);
    resolver(respuesta());
    await primera;
    expect(cart.itemCount).toBe(3);
    expect(cart.repeatingOrderId).toBeNull();
  });

  it('conserva cambios del carrito hechos durante la consulta', async () => {
    let resolver!: (data: RecompraResponse) => void;
    vi.mocked(prepararRecompra).mockReturnValue(new Promise(resolve => { resolver = resolve; }));
    const cart = useCartStore();
    const primera = cart.repetirPedido('pedido');
    cart.items = [existente(3)];
    resolver(respuesta());
    await primera;
    expect(cart.items[0].cantidad).toBe(4);
  });

  it('conserva el carrito ante fallos y permite reintentar una vez recuperado el servicio', async () => {
    vi.mocked(prepararRecompra).mockRejectedValueOnce({ response: { data: { detail: 'Servicio no disponible' } } });
    const cart = useCartStore();
    cart.items = [existente()];
    expect(await cart.repetirPedido('pedido')).toBe(false);
    expect(cart.items[0].cantidad).toBe(2);
    expect(cart.recompraError).toBe('Servicio no disponible');
    expect(cart.repeatingOrderId).toBeNull();
    expect(await cart.repetirPedido('pedido')).toBe(true);
    expect(cart.items[0].cantidad).toBe(4);
  });

  it('cuenta las unidades existentes aunque el SKU del catálogo haya cambiado', async () => {
    const cart = useCartStore();
    cart.items = [{ ...existente(3), sku: 'SKU-ANTERIOR' }];
    await cart.repetirPedido('pedido');
    expect(cart.items[0]).toMatchObject({ cantidad: 4, sku: 'SKU', total_linea: 50 });
    expect(cart.recompraResumen?.agregados).toBe(1);
  });

  it('no modifica un carrito con reserva activa', async () => {
    const cart = useCartStore();
    cart.reservaStatus = 'activa';
    expect(await cart.repetirPedido('pedido')).toBe(false);
    expect(prepararRecompra).not.toHaveBeenCalled();
    expect(cart.recompraError).toContain('checkout actual');
  });
});
