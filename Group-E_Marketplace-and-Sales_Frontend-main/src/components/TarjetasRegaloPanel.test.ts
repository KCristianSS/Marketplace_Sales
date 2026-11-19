// @vitest-environment jsdom
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import TarjetasRegaloPanel from './TarjetasRegaloPanel.vue';
import { valesApi, type Vale } from '@/api/vales';
import { pagosApi } from '@/api/pagos';

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'cliente', nombre_completo: 'Ana' } }) }));
vi.mock('@/api/vales', () => ({ valesApi: { listar: vi.fn(), emitir: vi.fn(), comprar: vi.fn(),
  cambiarEstado: vi.fn(), regenerar: vi.fn(), codigo: vi.fn(), movimientos: vi.fn() } }));
vi.mock('@/api/pagos', () => ({ pagosApi: { iniciarPago: vi.fn(), consultarEstado: vi.fn() } }));

const tarjeta: Vale = { id: 'tarjeta', comprador_id: 'cliente', codigo_ultimos: '1234ABCD',
  monto_inicial: 100, saldo: 70, moneda: 'BOB', estado: 'activa', origen: 'compra',
  vence_en: null, created_at: '2026-11-05T12:00:00Z' };
let wrapper: VueWrapper;
const montar = async (administracion = false) => {
  wrapper = mount(TarjetasRegaloPanel, { props: { administracion }, global: { stubs: { DynamicPaymentProcessingModal: true } } });
  await flushPromises();
};
const boton = (texto: string) => wrapper.findAll('button').find(b => b.text() === texto)!;

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(valesApi.listar).mockResolvedValue([tarjeta]);
  vi.mocked(valesApi.movimientos).mockResolvedValue([]);
});
afterEach(() => { wrapper?.unmount(); vi.clearAllMocks(); });

describe('tarjetas de regalo', () => {
  it('muestra saldo y oculta las acciones administrativas al cliente', async () => {
    await montar();
    expect(wrapper.text()).toContain('Bs 70.00');
    expect(wrapper.text()).not.toContain('Regenerar código');
    expect(wrapper.text()).not.toContain('Bloquear');
  });

  it('exige un motivo para bloquear y conserva el error del servidor', async () => {
    await montar(true);
    await boton('Bloquear').trigger('click');
    await flushPromises();
    expect(valesApi.cambiarEstado).not.toHaveBeenCalled();
    expect(wrapper.find('[role="dialog"]').text()).toContain('Motivo de la gestión');
    const motivo = wrapper.find('[role="dialog"] textarea');
    await motivo.setValue('Bloqueo por extravío');
    vi.mocked(valesApi.cambiarEstado).mockRejectedValue({ response: { data: { detail: 'Hay un checkout activo.' } } });
    await wrapper.find('[role="dialog"]').trigger('submit');
    await flushPromises();
    expect(valesApi.cambiarEstado).toHaveBeenCalledWith('tarjeta', 'bloqueada', 'Bloqueo por extravío');
    expect(wrapper.find('[role="dialog"] [role="alert"]').text()).toContain('checkout activo');
  });

  it('no muestra el código completo hasta solicitarlo', async () => {
    vi.mocked(valesApi.codigo).mockResolvedValue({ ...tarjeta, codigo: 'MAXI-CODIGO-SECRETO' });
    await montar();
    expect(wrapper.text()).not.toContain('MAXI-CODIGO-SECRETO');
    await boton('Código').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('MAXI-CODIGO-SECRETO');
    await boton('Ocultar').trigger('click');
    expect(wrapper.text()).not.toContain('MAXI-CODIGO-SECRETO');
  });

  it('recupera un pago aprobado sin iniciar un segundo cobro', async () => {
    sessionStorage.setItem('maxiconecta:vale-pago:cliente', 'TX-EXISTENTE');
    vi.mocked(pagosApi.consultarEstado).mockResolvedValue({ estado: 'aprobado' } as any);
    vi.mocked(valesApi.comprar).mockResolvedValue({ ...tarjeta, codigo: 'MAXI-RECUPERADO' });
    await montar();
    await boton('Consultar pago y recuperar tarjeta').trigger('click');
    await flushPromises();
    expect(valesApi.comprar).toHaveBeenCalledWith('TX-EXISTENTE');
    expect(pagosApi.iniciarPago).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('MAXI-RECUPERADO');
    expect(sessionStorage.getItem('maxiconecta:vale-pago:cliente')).toBeNull();
  });
});
