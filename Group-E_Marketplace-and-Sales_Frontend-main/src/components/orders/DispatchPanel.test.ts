// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import DispatchPanel from './DispatchPanel.vue';
import { despachosApi, type Despacho } from '@/api/despachos';

vi.mock('@/api/despachos', () => ({ despachosApi: { consultar: vi.fn(), obtener: vi.fn(), reintentar: vi.fn(), trazabilidad: vi.fn() } }));
const inicial = (): Despacho => ({ id: 'despacho', orden_id: 'orden', estado: 'pendiente', guia: null,
  version: 0,
  transportista: null, ruta: null, ubicacion_actual: null, fecha_estimada: null, motivo: null,
  actualizado_en: '2026-11-06T12:00:00Z', eventos: [{ id: 'evento', tipo_evento: 'despacho.solicitado',
    estado: 'publicado', intentos: 1, message_id: 'gcp-123', ultimo_error: null, created_at: '2026-11-06T12:00:00Z' }] });
let wrapper: VueWrapper;
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(despachosApi.trazabilidad).mockResolvedValue({ total: 1, pagina: 1, total_paginas: 1, items: [{
    ...inicial().eventos[0], event_id: 'evento', direccion: 'salida', orden_id: 'orden', correlation_id: 'despacho',
    simulacion: false, topic: 'topic', estado_logistico: 'pendiente', mensaje: { payload: { orden_id: 'orden' } }, atributos: {}, registro: 'estado_actual',
  }] });
  vi.mocked(despachosApi.consultar).mockResolvedValue(inicial());
  vi.mocked(despachosApi.obtener).mockResolvedValue({ ...inicial(), version: 1, estado: 'programado', guia: 'TRK-ERP', transportista: 'Transportista ERP', ruta: 'Ruta 5' });
  vi.mocked(despachosApi.reintentar).mockResolvedValue(inicial());
});
afterEach(() => { wrapper?.unmount(); vi.useRealTimers(); vi.clearAllMocks(); });

describe('seguimiento de despacho', () => {
  it('al abrir publica una consulta y no inventa una guía al confirmar la publicación', async () => {
    wrapper = mount(DispatchPanel, { props: { orderId: 'orden' } });
    await flushPromises();
    expect(despachosApi.consultar).toHaveBeenCalledWith('orden');
    expect(wrapper.text()).toContain('Pendiente de respuesta de Entregas');
    expect(wrapper.text()).toContain('Esperando respuesta del ERP');
  });
  it('el polling lee la respuesta local sin publicar consultas repetidas', async () => {
    wrapper = mount(DispatchPanel, { props: { orderId: 'orden' } });
    await flushPromises();
    await vi.advanceTimersByTimeAsync(5000);
    await flushPromises();
    expect(despachosApi.consultar).toHaveBeenCalledTimes(1);
    expect(despachosApi.obtener).toHaveBeenCalledWith('orden');
    expect(wrapper.text()).toContain('TRK-ERP');
    expect(wrapper.text()).toContain('Ruta 5');
  });
  it('Actualizar estado solicita otro mensaje y reintentar queda disponible solo para administración', async () => {
    wrapper = mount(DispatchPanel, { props: { orderId: 'orden', admin: true } });
    await flushPromises();
    await wrapper.findAll('button').find(b => b.text() === 'Actualizar estado en ERP')!.trigger('click');
    await flushPromises();
    expect(despachosApi.consultar).toHaveBeenCalledTimes(2);
    await wrapper.findAll('button').find(b => b.text() === 'Reintentar solicitud')!.trigger('click');
    await flushPromises();
    expect(despachosApi.reintentar).toHaveBeenCalledWith('orden');
    expect(wrapper.text()).toContain('gcp-123');
    await wrapper.setProps({ admin: false });
    expect(wrapper.text()).not.toContain('Reintentar solicitud');
  });
  it('una orden cancelada consulta solo información local', async () => {
    wrapper = mount(DispatchPanel, { props: { orderId: 'orden', cancelled: true } });
    await flushPromises();
    expect(despachosApi.consultar).not.toHaveBeenCalled();
    expect(despachosApi.obtener).toHaveBeenCalledWith('orden');
    expect(wrapper.text()).not.toContain('Actualizar estado en ERP');
  });
});
