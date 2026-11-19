// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import CorporateCustomerModal from './CorporateCustomerModal.vue';
import { registrarEmpresaB2B } from '@/api/cotizaciones';

vi.mock('@/api/cotizaciones', async original => ({ ...await original<typeof import('@/api/cotizaciones')>(), registrarEmpresaB2B: vi.fn() }));
let wrapper: VueWrapper;
const company = { id: 'company-1', nombre_completo: 'Empresa SRL', razon_social: 'Empresa SRL', nit_ci: '123456789', email: 'ventas@example.com' };
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true; } });
  vi.mocked(registrarEmpresaB2B).mockResolvedValue({ cliente: company, creado: true });
  wrapper = mount(CorporateCustomerModal, { props: { initialNit: company.nit_ci }, global: { stubs: { teleport: true } } });
});
afterEach(() => { wrapper.unmount(); vi.clearAllMocks(); });
async function fill() {
  await wrapper.find('input[autocomplete="organization"]').setValue(company.razon_social);
  await wrapper.find('input[type="email"]').setValue(company.email);
}
describe('alta comercial de empresas', () => {
  it('usa el NIT buscado y entrega la empresa al formulario de cotización', async () => {
    await fill(); await wrapper.find('form').trigger('submit'); await flushPromises();
    expect(registrarEmpresaB2B).toHaveBeenCalledWith(expect.objectContaining({ nit_ci: company.nit_ci, razon_social: company.razon_social, email: company.email }));
    expect(wrapper.emitted('registered')?.[0]).toEqual([company, true]);
    expect(wrapper.find('input[type="password"]').exists()).toBe(false);
  });
  it('muestra conflictos sin perder los datos escritos', async () => {
    vi.mocked(registrarEmpresaB2B).mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Este correo ya pertenece a otro cliente.' } } });
    await fill(); await wrapper.find('form').trigger('submit'); await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Este correo');
    expect((wrapper.find('input[type="email"]').element as HTMLInputElement).value).toBe(company.email);
    expect(wrapper.emitted('registered')).toBeUndefined();
  });
});
