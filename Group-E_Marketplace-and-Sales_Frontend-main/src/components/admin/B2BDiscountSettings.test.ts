// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import B2BDiscountSettings from './B2BDiscountSettings.vue';
import { guardarReglasB2B, type ReglasDescuentosB2B } from '@/api/cotizaciones';

vi.mock('@/api/cotizaciones', async original => ({ ...await original<typeof import('@/api/cotizaciones')>(), guardarReglasB2B: vi.fn() }));
vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
const record = (): ReglasDescuentosB2B => ({ version: 2, actualizado_en: '2026-11-10T00:00:00Z', actualizado_por: null,
  configuracion: { habilitado: true, escalas: [{ minimo_unidades: 5, descuento_porcentaje: 5 }, { minimo_unidades: 10, descuento_porcentaje: 10 }] } });
let wrapper: VueWrapper;
beforeEach(() => {
  vi.mocked(guardarReglasB2B).mockImplementation(async (version, configuracion) => ({ ...record(), version: version + 1, configuracion }));
  wrapper = mount(B2BDiscountSettings, { props: { record: record() } });
});
afterEach(() => { wrapper.unmount(); vi.clearAllMocks(); });

describe('parámetros de descuentos B2B', () => {
  it('guarda porcentajes editados con la versión que se abrió', async () => {
    await wrapper.find('input[aria-label="Descuento de escala 1"]').setValue(7.5);
    await wrapper.find('form').trigger('submit'); await flushPromises();
    expect(guardarReglasB2B).toHaveBeenCalledWith(2, { habilitado: true, escalas: [{ minimo_unidades: 5, descuento_porcentaje: 7.5 }, { minimo_unidades: 10, descuento_porcentaje: 10 }] });
    expect(wrapper.emitted('updated')?.[0]?.[0]).toEqual(expect.objectContaining({ version: 3 }));
  });
  it('mantiene la edición si otro usuario guardó primero', async () => {
    vi.mocked(guardarReglasB2B).mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Otro usuario actualizó los descuentos.' } } });
    await wrapper.find('input[aria-label="Descuento de escala 1"]').setValue(7.5);
    await wrapper.find('form').trigger('submit'); await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Otro usuario');
    expect((wrapper.find('input[aria-label="Descuento de escala 1"]').element as HTMLInputElement).value).toBe('7.5');
    expect(wrapper.text()).toContain('Tienes cambios sin guardar');
  });
  it('rechaza cantidades mínimas duplicadas sin enviar cambios', async () => {
    await wrapper.find('input[aria-label="Cantidad mínima de escala 2"]').setValue(5);
    await wrapper.find('form').trigger('submit');
    expect(guardarReglasB2B).not.toHaveBeenCalled();
    expect(wrapper.find('[role="alert"]').text()).toContain('No repitas');
  });
});
