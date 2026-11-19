// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import DeliveryMethodSelector from './DeliveryMethodSelector.vue';
import { apiClient } from '@/api/client';

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

const respuesta = (costo = 15) => ({ data: {
  ciudad: 'La Paz', zona: 'Centro', costo_flete: costo, costo_original: costo,
  flete_gratis: false, umbral_flete_gratis: 500, tiempo_estimado: '24 horas hábiles',
  tipo_envio: 'estandar', mensaje: '', moneda: 'BOB', total: 100 + costo,
  cotizacion_flete: `cotizacion-${costo}`, expira_en: Date.now() / 1000 + 60,
  desglose: { tarifa_base_zona: costo, peso_estimado_kg: 1.5 },
} });

let wrapper: VueWrapper;
const opciones = (version = 1) => ({ version, envio_gratis_habilitado: true, umbral_envio_gratis: 500,
  zonas: ['Centro', 'Miraflores'].map((nombre, index) => ({ id: String(index), ciudad: 'La Paz', nombre,
    tarifa_base: 15, estandar_habilitado: true, express_habilitado: true,
    plazo_estandar: '24 horas hábiles', plazo_express: '4 horas hábiles' })) });
const valido = () => wrapper.emitted('validation-change')?.at(-1)?.[0];
const entrega = () => wrapper.emitted('update:modelValue')?.at(-1)?.[0] as any;

async function iniciar() {
  wrapper = mount(DeliveryMethodSelector, { props: {
    subtotal: 100, reservaId: 'RES-TEST',
    initialData: { ciudad: 'La Paz', zona: 'Centro', direccion_exacta: 'Av. Arce 123' },
  } });
  await vi.advanceTimersByTimeAsync(300);
  await flushPromises();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(apiClient.get).mockImplementation(async url => ({ data: String(url).endsWith('/opciones') ? opciones() : [] }));
  vi.mocked(apiClient.post).mockImplementation(async () => respuesta());
});
afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('cotización en checkout', () => {
  it('usa la ciudad, zona y dirección guardadas sin volver a solicitarlas', async () => {
    wrapper = mount(DeliveryMethodSelector, { props: {
      subtotal: 100, reservaId: 'RES-TEST', direccionGuardada: true,
      initialData: { ciudad: 'La Paz', zona: 'Centro', direccion_exacta: 'Av. Arce 123', referencia_entrega: 'Edificio azul' },
    } });
    await flushPromises();
    expect(wrapper.findAll('select')).toHaveLength(0);
    expect(wrapper.find('input[placeholder*="Av. 6 de Agosto"]').exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(300);
    expect(apiClient.post).toHaveBeenLastCalledWith('/api/v1/ordenes/flete/calcular', expect.objectContaining({
      ciudad: 'La Paz', zona: 'Centro', direccion: 'Av. Arce 123', referencia: 'Edificio azul',
    }));
    expect(valido()).toBe(true);
  });

  it('indica que se edite la dirección guardada cuando no tiene zona', async () => {
    wrapper = mount(DeliveryMethodSelector, { props: { subtotal: 100, reservaId: 'RES-TEST', direccionGuardada: true,
      initialData: { ciudad: 'La Paz', direccion_exacta: 'Av. Arce 123' } } });
    await flushPromises();
    expect(wrapper.findAll('select')).toHaveLength(0);
    expect(wrapper.text()).toContain('Edita tu dirección en Mi cuenta');
    expect(valido()).toBe(false);
  });

  it('ofrece nuevas ciudades y respeta las modalidades administradas', async () => {
    const actuales = opciones();
    actuales.zonas = [{ ...actuales.zonas[0], ciudad: 'Potosí', nombre: 'Centro histórico', estandar_habilitado: false }];
    vi.mocked(apiClient.get).mockImplementation(async url => ({ data: String(url).endsWith('/opciones') ? actuales : [] }));
    await iniciar();
    expect(wrapper.findAll('select')[0].text()).toContain('Potosí');
    expect(wrapper.findAll('select')[0].text()).not.toContain('La Paz');
    await wrapper.findAll('select')[0].setValue('Potosí');
    await wrapper.findAll('select')[1].setValue('Centro histórico');
    const estandar = wrapper.findAll('button').find(b => b.text().includes('Envío Estándar'))!;
    expect(estandar.attributes('disabled')).toBeDefined();
    await vi.advanceTimersByTimeAsync(300);
    expect(apiClient.post).toHaveBeenLastCalledWith('/api/v1/ordenes/flete/calcular', expect.objectContaining({
      ciudad: 'Potosí', zona: 'Centro histórico', tipo_envio: 'express_mismo_dia',
    }));
  });

  it('refresca una cotización cuando el administrador cambia las reglas', async () => {
    await iniciar();
    const actuales = opciones(2);
    actuales.zonas[0].tarifa_base = 99;
    vi.mocked(apiClient.get).mockImplementation(async url => ({ data: String(url).endsWith('/opciones') ? actuales : [] }));
    vi.mocked(apiClient.post).mockImplementation(async () => respuesta(99));
    await vi.advanceTimersByTimeAsync(29700);
    expect(valido()).toBe(false);
    await vi.advanceTimersByTimeAsync(300);
    expect(entrega().costo_flete).toBe(99);
    expect(valido()).toBe(true);
  });

  it('conserva la selección durante un pago y detiene la actualización de opciones', async () => {
    await iniciar();
    const consultas = vi.mocked(apiClient.get).mock.calls.length;
    await wrapper.setProps({ bloqueado: true });
    await vi.advanceTimersByTimeAsync(30000);
    expect(apiClient.get).toHaveBeenCalledTimes(consultas);
    expect(entrega().costo_flete).toBe(15);
  });

  it('mantiene el retiro en sucursal sin costo de flete', async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => ({ data: String(url).endsWith('/opciones') ? opciones() : [{
      id: 'suc-1', ciudad: 'La Paz', nombre: 'Central', direccion: 'El Prado 100',
      coordenadas: { lat: -16.5, lng: -68.1 }, tiempo_preparacion: 'Listo en 2 horas',
      horario_atencion: '09:00 a 18:00', es_habilitada: true,
    }] }));
    await iniciar();
    await wrapper.findAll('button').find(button => button.text().includes('Retiro en'))!.trigger('click');
    expect(valido()).toBe(true);
    expect(entrega().tipo_despacho).toBe('retiro_sucursal');
    expect(entrega().costo_flete).toBe(0);
    expect(entrega().cotizacion_flete).toBeUndefined();
  });

  it('muestra costo y plazo y exige elegir zona para una dirección sin zona', async () => {
    await iniciar();
    expect(valido()).toBe(true);
    expect(wrapper.text()).toContain('24 horas hábiles');
    expect(entrega().costo_flete).toBe(15);
    wrapper.unmount();
    wrapper = mount(DeliveryMethodSelector, { props: { subtotal: 100, reservaId: 'RES-TEST',
      initialData: { ciudad: 'La Paz', direccion_exacta: 'Av. Arce 123' } } });
    await flushPromises();
    expect(valido()).toBe(false);
    expect(wrapper.findAll('select')[1].element.value).toBe('');
  });

  it('invalida al cambiar zona y permite reintentar tras un error', async () => {
    await iniciar();
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error('sin conexión'));
    await wrapper.findAll('select')[1].setValue('Miraflores');
    expect(valido()).toBe(false);
    expect(entrega().cotizacion_flete).toBeUndefined();
    await vi.advanceTimersByTimeAsync(300);
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    expect(valido()).toBe(false);
    await wrapper.find('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(valido()).toBe(true);
  });

  it('descarta una respuesta anterior que llega después de cambiar la zona', async () => {
    let responder!: (data: any) => void;
    vi.mocked(apiClient.post).mockImplementationOnce(() => new Promise(resolve => { responder = resolve; }));
    await iniciar();
    await wrapper.findAll('select')[1].setValue('Miraflores');
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    responder(respuesta(99));
    await flushPromises();
    expect(entrega().costo_flete).toBe(15);
    expect(valido()).toBe(true);
  });

  it('invalida por vencimiento y vuelve a cotizar al cambiar puntos o cupón', async () => {
    await iniciar();
    await vi.advanceTimersByTimeAsync(60000);
    expect(valido()).toBe(false);
    expect(wrapper.text()).toContain('venció');
    await wrapper.setProps({ puntosCanjeados: 10, cupon: 'MAXI10' });
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    expect(apiClient.post).toHaveBeenLastCalledWith('/api/v1/ordenes/flete/calcular', expect.objectContaining({
      puntos_canjeados: 10, cupon: 'MAXI10', reserva_id: 'RES-TEST',
    }));
    expect(valido()).toBe(true);
  });
});
