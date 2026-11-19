// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import ShippingManager from './ShippingManager.vue';
import * as feedback from '@/lib/feedback';
import { toast } from 'vue-sonner';
import { obtenerConfiguracionEnvios, guardarConfiguracionEnvios, type RegistroEnvios } from '@/api/envios';

vi.mock('@/api/envios', async importOriginal => {
  const original = await importOriginal<typeof import('@/api/envios')>();
  return { ...original, obtenerConfiguracionEnvios: vi.fn(), guardarConfiguracionEnvios: vi.fn() };
});

vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const datos = (): RegistroEnvios => ({ version: 1, almacenamiento: 'base_datos', actualizado_por: null, actualizado_en: null,
  configuracion: { envio_gratis_habilitado: true, umbral_envio_gratis: 500, recargo_express: 15,
    peso_incluido_kg: 5, recargo_por_kg: 5, peso_estimado_por_unidad_kg: 1.5,
    zonas: [{ id: 'zone-1', ciudad: 'La Paz', nombre: 'Centro', tarifa_base: 15, activa: true,
      estandar_habilitado: true, express_habilitado: true, plazo_estandar: '24 horas', plazo_express: '4 horas' }],
  },
});

let wrapper: VueWrapper;
const label = (texto: string, parent: VueWrapper | ReturnType<VueWrapper['find']> = wrapper) =>
  parent.findAll('label').find(item => item.text().includes(texto))!;

beforeEach(async () => {
  vi.mocked(obtenerConfiguracionEnvios).mockResolvedValue(datos());
  vi.mocked(guardarConfiguracionEnvios).mockImplementation(async (version, configuracion) => ({
    ...datos(), version: version + 1, configuracion: JSON.parse(JSON.stringify(configuracion)),
  }));
  wrapper = mount(ShippingManager, { global: { stubs: { ShippingTracePanel: true } } });
  await flushPromises();
});
afterEach(() => {
  wrapper.unmount();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('administración de envíos', () => {
  it('guarda las reglas con la versión que se está editando', async () => {
    await label('Monto mínimo').find('input').setValue(650);
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(guardarConfiguracionEnvios).toHaveBeenCalledWith(1, expect.objectContaining({ umbral_envio_gratis: 650 }));
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Configuración guardada'));
  });

  it('agrega una zona y la incluye al guardar la configuración', async () => {
    await wrapper.findAll('button').find(b => b.text().includes('Agregar zona'))!.trigger('click');
    const dialogo = wrapper.find('[role="dialog"]');
    await label('Ciudad', dialogo).find('input').setValue('Potosí');
    await label('Nombre de la zona', dialogo).find('input').setValue('Centro');
    await label('Tarifa base', dialogo).find('input').setValue(35);
    await dialogo.trigger('submit');
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Potosí');
    await wrapper.find('form').trigger('submit');
    expect(guardarConfiguracionEnvios).toHaveBeenCalledWith(1, expect.objectContaining({ zonas: expect.arrayContaining([
      expect.objectContaining({ ciudad: 'Potosí', nombre: 'Centro', tarifa_base: 35 }),
    ]) }));
  });

  it('desactiva una zona desde su formulario de edición', async () => {
    await wrapper.find('button[aria-label="Editar Centro, La Paz"]').trigger('click');
    const dialogo = wrapper.find('[role="dialog"]');
    await label('cobertura activa', dialogo).find('input').setValue(false);
    await dialogo.trigger('submit');
    await wrapper.find('form').trigger('submit');
    expect(guardarConfiguracionEnvios).toHaveBeenCalledWith(1, expect.objectContaining({ zonas: [expect.objectContaining({ activa: false })] }));
  });

  it('mantiene los cambios si otro administrador guardó una versión más reciente', async () => {
    vi.mocked(guardarConfiguracionEnvios).mockRejectedValue({ response: { status: 409, data: { detail: 'Otro administrador actualizó los envíos. Recarga la configuración.' } } });
    await label('Recargo express').find('input').setValue(25);
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Otro administrador');
    expect((label('Recargo express').find('input').element as HTMLInputElement).value).toBe('25');
    expect(wrapper.text()).toContain('Tienes cambios sin guardar');
  });

  it('conserva las reglas editadas cuando se cancela la confirmación de recarga', async () => {
    vi.spyOn(feedback, 'confirmAction').mockResolvedValue(false);
    await label('Recargo express').find('input').setValue(25);
    await wrapper.findAll('button').find(b => b.text().includes('Recargar'))!.trigger('click');
    await flushPromises();
    expect(obtenerConfiguracionEnvios).toHaveBeenCalledTimes(1);
    expect((label('Recargo express').find('input').element as HTMLInputElement).value).toBe('25');
  });
});
