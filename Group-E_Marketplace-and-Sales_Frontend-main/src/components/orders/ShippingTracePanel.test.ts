// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import ShippingTracePanel from './ShippingTracePanel.vue';
import { despachosApi, type TrazabilidadEnvios } from '@/api/despachos';

vi.mock('@/api/despachos', () => ({ despachosApi: { trazabilidad: vi.fn() } }));
const respuesta = (): TrazabilidadEnvios => ({ total: 21, pagina: 1, total_paginas: 2, items: [{
  id: 'log-1', event_id: 'evt-1', tipo_evento: 'despacho.cotizacion.calculada', direccion: 'salida',
  estado: 'publicado', orden_id: null, correlation_id: 'cot-1', simulacion: true, topic: 'topic-envios',
  message_id: 'gcp-1', intentos: 1, ultimo_error: null, estado_logistico: null, registro: 'mensaje',
  created_at: '2026-11-09T12:00:00Z', mensaje: { payload: { calculo: { costo_flete: '35.00', total: '435.00' } } },
  atributos: { destino: 'entregas', simulacion: 'true' },
}] });
let wrapper: VueWrapper;
beforeEach(() => { vi.useFakeTimers(); vi.mocked(despachosApi.trazabilidad).mockResolvedValue(respuesta()); });
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.resetAllMocks(); });

describe('trazabilidad administrativa de envíos', () => {
  it('muestra el JSON enviado, identificadores y cálculo simulado', async () => {
    wrapper = mount(ShippingTracePanel);
    await flushPromises();
    expect(wrapper.text()).toContain('Simulación de cotización');
    expect(wrapper.text()).toContain('gcp-1');
    expect(wrapper.find('pre').text()).toContain('35.00');
    expect(wrapper.find('pre').text()).toContain('435.00');
    expect(despachosApi.trazabilidad).toHaveBeenCalledWith({ page: 1, limit: 20 });
  });
  it('pagina sin perder el alcance del pedido', async () => {
    wrapper = mount(ShippingTracePanel, { props: { orderId: 'orden-1' } });
    await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Siguiente')!.trigger('click');
    await flushPromises();
    expect(despachosApi.trazabilidad).toHaveBeenLastCalledWith({ orden_id: 'orden-1', page: 2, limit: 20 });
  });
  it('filtra estados y respuestas recibidas y actualiza el historial automáticamente', async () => {
    wrapper = mount(ShippingTracePanel);
    await flushPromises();
    await wrapper.find('[aria-label="Estado del mensaje"]').setValue('aplicado');
    await wrapper.find('[aria-label="Dirección del mensaje"]').setValue('entrada');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(despachosApi.trazabilidad).toHaveBeenLastCalledWith({ estado: 'aplicado', direccion: 'entrada', page: 1, limit: 20 });
    await vi.advanceTimersByTimeAsync(5000);
    expect(despachosApi.trazabilidad).toHaveBeenCalledTimes(3);
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(5000);
    expect(despachosApi.trazabilidad).toHaveBeenCalledTimes(3);
  });
  it('muestra el error del servicio y permite reintentar', async () => {
    vi.mocked(despachosApi.trazabilidad).mockRejectedValueOnce({ response: { data: { detail: 'Servicio no disponible' } } });
    wrapper = mount(ShippingTracePanel);
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Servicio no disponible');
    await wrapper.findAll('button').find(b => b.text() === 'Actualizar mensajes')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
});
