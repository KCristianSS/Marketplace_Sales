// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import AuditLogPanel from './AuditLogPanel.vue';
import { obtenerAuditoria, type AuditPage } from '@/api/auditoria';

vi.mock('@/api/auditoria', () => ({ obtenerAuditoria: vi.fn() }));
const data = (): AuditPage => ({ total: 21, pagina: 1, total_paginas: 2, pendientes_locales: 0, items: [{
  id: 'event-1', user_id: 'admin-1', actor_id: 'admin-1', user_role: 'administrador',
  action: 'PRODUCTO_ACTUALIZADO', entity: 'productos', entity_id: 'product-1',
  ip_address: '192.0.2.10', created_at: '2026-11-10T03:00:00Z',
  payload_before: { precio: 100, nombre: 'Monitor' }, payload_after: { precio: 120, nombre: 'Monitor' },
  request_id: 'request-1', request_method: 'PATCH', request_path: '/api/v1/catalogo/productos/product-1',
  user_agent: 'Navegador de prueba', source: 'application',
}] });
let wrapper: VueWrapper;
beforeEach(async () => {
  vi.mocked(obtenerAuditoria).mockResolvedValue(data());
  wrapper = mount(AuditLogPanel);
  await flushPromises();
});
afterEach(() => { wrapper.unmount(); vi.clearAllMocks(); });

describe('consulta administrativa de auditoría', () => {
  it('presenta quién, qué, origen y únicamente los campos que cambiaron', () => {
    expect(wrapper.text()).toContain('admin-1');
    expect(wrapper.text()).toContain('PRODUCTO_ACTUALIZADO');
    expect(wrapper.text()).toContain('192.0.2.10');
    const details = wrapper.find('tbody details');
    expect(details.text()).toContain('precio');
    expect(details.text()).toContain('100');
    expect(details.text()).toContain('120');
    expect(details.findAll('strong').some(element => element.text() === 'nombre')).toBe(false);
  });

  it('aplica filtros y mantiene sus valores al cambiar de página', async () => {
    const fields = wrapper.findAll('input');
    await fields[0].setValue('PRODUCTO_ACTUALIZADO');
    await wrapper.findAll('select')[0].setValue('productos');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(obtenerAuditoria).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, entidad: 'productos', accion: 'PRODUCTO_ACTUALIZADO' }), expect.any(AbortSignal));
    await wrapper.findAll('button').find(button => button.text() === 'Siguiente')!.trigger('click');
    expect(obtenerAuditoria).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, entidad: 'productos', accion: 'PRODUCTO_ACTUALIZADO' }), expect.any(AbortSignal));
  });

  it('informa de eventos pendientes y de fallos sin presentar una lista vacía como correcta', async () => {
    vi.mocked(obtenerAuditoria).mockResolvedValueOnce({ ...data(), pendientes_locales: 3 });
    await wrapper.findAll('button').find(button => button.text() === 'Actualizar')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="status"]').text()).toContain('3 eventos pendientes');
    vi.mocked(obtenerAuditoria).mockRejectedValueOnce({ response: { status: 503, data: { detail: 'No se pudo consultar la auditoría.' } } });
    await wrapper.findAll('button').find(button => button.text() === 'Actualizar')!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('No se pudo consultar la auditoría');
    expect(wrapper.text()).not.toContain('No hay auditorías');
  });
});
