// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import B2BQuotesPanel from './B2BQuotesPanel.vue';
import { apiClient } from '@/api/client';
import { buscarClientesCorporativos, emitirCotizacion, listarCotizaciones, obtenerReglasB2B, type ReglasDescuentosB2B } from '@/api/cotizaciones';

vi.mock('@/api/client', () => ({ apiClient: { get: vi.fn() } }));
vi.mock('@/api/cotizaciones', async original => ({ ...await original<typeof import('@/api/cotizaciones')>(),
  buscarClientesCorporativos: vi.fn(), emitirCotizacion: vi.fn(), listarCotizaciones: vi.fn(), obtenerReglasB2B: vi.fn() }));
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
const company = { id: 'company-1', nombre_completo: 'Empresa', razon_social: 'Empresa SRL', nit_ci: '123456789', email: 'empresa@example.com' };
const rules = (): ReglasDescuentosB2B => ({ version: 7, actualizado_en: '2026-11-10T00:00:00Z', actualizado_por: null,
  configuracion: { habilitado: true, escalas: [{ minimo_unidades: 3, descuento_porcentaje: 12 }] } });
let wrapper: VueWrapper;
const button = (label: string) => wrapper.findAll('button').find(element => element.text() === label)!;
beforeEach(async () => {
  vi.mocked(apiClient.get).mockResolvedValue({ data: [{ id: 'product-1', nombre: 'Producto', estado: 'publicado', variantes: [{ id: 'variant-1', sku: 'SKU-1', precio: 100 }] }] });
  vi.mocked(obtenerReglasB2B).mockResolvedValue(rules());
  vi.mocked(buscarClientesCorporativos).mockResolvedValue([company]);
  vi.mocked(listarCotizaciones).mockResolvedValue({ items: [], total: 0, pagina: 1, limite: 10, total_paginas: 1 });
  vi.mocked(emitirCotizacion).mockResolvedValue({ id: 'quote-1', codigo_cotizacion: 'COT-2026-0001', cliente_id: company.id, nombre_cliente: company.nombre_completo } as any);
  wrapper = mount(B2BQuotesPanel, { global: { stubs: { CorporateCustomerModal: true, B2BDiscountSettings: true } } });
  await flushPromises();
});
afterEach(() => { wrapper.unmount(); vi.clearAllMocks(); });

describe('cotizaciones con empresas y descuentos configurables', () => {
  it('usa las escalas del servidor en el estimado y envía su versión al emitir', async () => {
    await wrapper.find('#quote-nit').setValue(company.nit_ci);
    await button('Buscar').trigger('click');
    await flushPromises();
    await wrapper.find('input[aria-label="Cantidad"]').setValue(3);
    expect(wrapper.text()).toContain('Descuento por volumen: 12%');
    expect(wrapper.text()).toContain('264');
    await button('Emitir cotización').trigger('click');
    await flushPromises();
    expect(emitirCotizacion).toHaveBeenCalledWith(expect.objectContaining({ cliente_id: company.id, configuracion_descuento_version: 7,
      items: [{ variante_id: 'variant-1', cantidad: 3 }] }));
  });

  it('selecciona la empresa registrada y actualiza el estimado al guardar nuevas reglas', async () => {
    await button('Registrar empresa').trigger('click');
    const created = { ...company, id: 'company-new', razon_social: 'Nueva empresa' };
    wrapper.findComponent({ name: 'CorporateCustomerModal' }).vm.$emit('registered', created, true);
    await flushPromises();
    expect(wrapper.text()).toContain('Cliente: Nueva empresa');
    expect(wrapper.findComponent({ name: 'CorporateCustomerModal' }).exists()).toBe(false);
    await wrapper.find('input[aria-label="Cantidad"]').setValue(3);
    wrapper.findComponent({ name: 'B2BDiscountSettings' }).vm.$emit('updated', { ...rules(), version: 8, configuracion: { habilitado: false, escalas: [] } });
    await flushPromises();
    expect(wrapper.text()).toContain('Descuento por volumen: 0%');
    await button('Emitir cotización').trigger('click');
    expect(emitirCotizacion).toHaveBeenCalledWith(expect.objectContaining({ cliente_id: created.id, configuracion_descuento_version: 8 }));
  });

  it('borra una selección anterior si la búsqueda de otro NIT no encuentra empresas', async () => {
    await button('Buscar').trigger('click'); await flushPromises();
    vi.mocked(buscarClientesCorporativos).mockResolvedValueOnce([]);
    await wrapper.find('#quote-nit').setValue('99999999');
    await button('Buscar').trigger('click'); await flushPromises();
    expect(wrapper.text()).not.toContain('Cliente: Empresa SRL');
    await button('Emitir cotización').trigger('click');
    expect(emitirCotizacion).not.toHaveBeenCalled();
    expect(wrapper.find('[role="alert"]').text()).toContain('Busca y selecciona');
  });
});
