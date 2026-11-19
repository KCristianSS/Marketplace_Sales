// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('@/api/caja', () => ({
  arqueoCiegoApi: vi.fn(),
  listarMovimientosCajaApi: vi.fn().mockResolvedValue([]),
  registrarMovimientoCajaApi: vi.fn(),
  obtenerTokenSupervisorApi: vi.fn().mockResolvedValue('tok-sup')
}));
vi.mock('@/api/pagos', () => ({ pagosApi: { pagosDeOrden: vi.fn(), registrarPagoOrden: vi.fn(), simularWebhook: vi.fn() } }));

import ArqueoCiegoView from '@/components/pos/ArqueoCiegoView.vue';
import CajaMovimientoModal from '@/components/pos/CajaMovimientoModal.vue';
import PanelPagosOrden from '@/components/orders/PanelPagosOrden.vue';
import { arqueoCiegoApi, registrarMovimientoCajaApi, obtenerTokenSupervisorApi } from '@/api/caja';
import { pagosApi } from '@/api/pagos';

beforeEach(() => vi.clearAllMocks());

describe('KAN-341 arqueo ciego', () => {
  it('no muestra esperado ni totales por método y envía el desglose', async () => {
    const w = mount(ArqueoCiegoView, { props: { open: true, cajaId: 'c1', cajeroNombre: 'Ana', sucursalNombre: 'Centro' } });
    const t = w.text().toLowerCase();
    expect(t).not.toContain('total esperado');
    expect(t).not.toContain('tarjeta');
    expect(w.findAll('input[type=number]')).toHaveLength(11);
    await w.get('[data-testid="den-200.00"]').setValue(2);
    await w.get('[data-testid="den-0.50"]').setValue(3);
    expect(w.get('[data-testid="total-declarado"]').text()).toContain('401,50');
    (arqueoCiegoApi as any).mockResolvedValue({ numero_reporte: 'ARQ-1', resultado: 'faltante', con_diferencia: true, fondo_inicial: 500, ventas_efectivo: 0, entradas_extraordinarias: 0, retiros_boveda: 0, total_esperado: 500, total_declarado: 401.5, diferencia: -98.5, desglose: [] });
    await w.get('[data-testid="btn-continuar"]').trigger('click');
    await w.get('[data-testid="btn-confirmar"]').trigger('click');
    await flushPromises();
    const payload = (arqueoCiegoApi as any).mock.calls[0][1];
    expect(payload.desglose).toHaveLength(11);
    expect(payload.desglose.find((d: any) => d.denominacion === 200).cantidad).toBe(2);
    expect(w.get('[data-testid="resultado-arqueo"]').text()).toContain('Faltante');
    expect(w.text()).toContain('Total esperado');
  });
  it('409: turno ya cerrado', async () => {
    (arqueoCiegoApi as any).mockRejectedValue({ response: { status: 409, data: { detail: 'El turno ya fue cerrado y no puede arquearse de nuevo.' } } });
    const w = mount(ArqueoCiegoView, { props: { open: true, cajaId: 'c1', cajeroNombre: 'Ana', sucursalNombre: 'Centro' } });
    await w.get('[data-testid="btn-continuar"]').trigger('click');
    await w.get('[data-testid="btn-confirmar"]').trigger('click');
    await flushPromises();
    expect(w.text()).toContain('ya fue cerrado');
  });
});

describe('KAN-342 movimientos', () => {
  it('retiro > límite pide supervisor y reenvía con token', async () => {
    (registrarMovimientoCajaApi as any)
      .mockRejectedValueOnce({ response: { status: 428, data: { detail: { codigo: 'SUPERVISOR_REQUERIDO', mensaje: 'Requiere supervisor', limite: '2000.00' } } } })
      .mockResolvedValueOnce({ id: 'm1', tipo: 'retiro', monto: 2500, motivo: 'Exceso', numero_comprobante: 'MOV-1', requiere_supervisor: true, comprobante: null });
    const w = mount(CajaMovimientoModal, { props: { open: false, cajaId: 'c1' } });
    await w.setProps({ open: true });
    await w.get('[data-testid="tipo-retiro"]').trigger('click');
    await w.get('[data-testid="mov-monto"]').setValue(2500);
    await w.get('[data-testid="mov-motivo"]').setValue('Exceso de efectivo');
    await w.get('form').trigger('submit');
    await flushPromises();
    expect(w.find('[data-testid="panel-supervisor"]').exists()).toBe(true);
    await w.get('[data-testid="sup-email"]').setValue('adm@x.com');
    await w.get('[data-testid="sup-password"]').setValue('secreto');
    await w.get('form').trigger('submit');
    await flushPromises();
    expect(obtenerTokenSupervisorApi).toHaveBeenCalledWith('adm@x.com', 'secreto');
    expect((registrarMovimientoCajaApi as any).mock.calls[1][1].supervisor_token).toBe('tok-sup');
    expect(w.find('[data-testid="movimiento-registrado"]').exists()).toBe(true);
  });
  it('no envía sin motivo', async () => {
    const w = mount(CajaMovimientoModal, { props: { open: true, cajaId: 'c1' } });
    await w.get('[data-testid="mov-monto"]').setValue(50);
    expect((w.get('[data-testid="mov-registrar"]').element as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('KAN-54 panel de pagos', () => {
  const base = { orden_id: 'o1', codigo_orden: 'ORD-1', estado_orden: 'pendiente', total: 100, total_aprobado: 0, total_pendiente: 0, saldo_pendiente: 100, apta_para_preparacion: false, historial: [] };
  it('muestra rechazado y permite reintentar con otro medio', async () => {
    (pagosApi.pagosDeOrden as any).mockResolvedValue({ ...base, pagos: [{ id: 'p1', orden_id: 'o1', transaccion_id: 'TX1', metodo: 'tarjeta', monto: 100, estado: 'rechazado', intento: 1, motivo_rechazo: 'Fondos insuficientes', monto_reembolsado: 0, saldo_reembolsable: 0 }] });
    (pagosApi.registrarPagoOrden as any).mockResolvedValue({ pago: { estado: 'aprobado' }, cambio: 0 });
    const w = mount(PanelPagosOrden, { props: { ordenId: 'o1', puedeRegistrar: true } });
    await flushPromises();
    expect(w.text()).toContain('Rechazado');
    expect(w.find('[data-testid="orden-no-apta"]').exists()).toBe(true);
    await w.get('[data-testid="btn-reintentar"]').trigger('click');
    await w.get('[data-testid="btn-registrar-pago"]').trigger('click');
    await w.get('form').trigger('submit');
    await flushPromises();
    expect((pagosApi.registrarPagoOrden as any).mock.calls[0][0]).toMatchObject({ orden_id: 'o1', reintento_de: 'p1', metodo: 'efectivo', monto: 100 });
  });
  it('orden confirmada: apta para preparación y sin formulario', async () => {
    (pagosApi.pagosDeOrden as any).mockResolvedValue({ ...base, estado_orden: 'confirmada', total_aprobado: 100, saldo_pendiente: 0, apta_para_preparacion: true, pagos: [] });
    const w = mount(PanelPagosOrden, { props: { ordenId: 'o1', puedeRegistrar: true } });
    await flushPromises();
    expect(w.find('[data-testid="orden-apta"]').exists()).toBe(true);
    expect(w.find('form').exists()).toBe(false);
  });
});
