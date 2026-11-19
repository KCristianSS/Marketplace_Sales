import { apiClient } from './client';

export interface Vale {
  id: string;
  comprador_id: string;
  codigo_ultimos: string;
  monto_inicial: number | string;
  saldo: number | string;
  moneda: string;
  estado: 'activa' | 'bloqueada' | 'anulada';
  origen: string;
  vence_en: string | null;
  created_at: string;
  codigo?: string;
}
export interface MovimientoVale {
  id: string;
  tipo: string;
  monto: number | string;
  actor: string;
  motivo: string;
  created_at: string;
}
export interface ReservaVale {
  id: string;
  monto: number | string;
  total: number | string;
  estado: string;
  expira_en: string;
}
const base = '/api/v1/ordenes/vales';
export const valesApi = {
  async listar(admin = false, estado = '', offset = 0, ultimos = ''): Promise<Vale[]> {
    return (await apiClient.get(admin ? `${base}/admin` : `${base}/`, { params: { estado: estado || undefined, offset, ultimos: ultimos || undefined } })).data;
  },
  async comprar(transaccion_id: string): Promise<Vale> {
    return (await apiClient.post(`${base}/comprar`, { transaccion_id })).data;
  },
  async emitir(payload: { solicitud_id: string; comprador_id: string; monto: number; motivo: string; vence_en?: string }): Promise<Vale> {
    return (await apiClient.post(`${base}/admin`, payload)).data;
  },
  async cambiarEstado(id: string, estado: Vale['estado'], motivo: string): Promise<Vale> {
    return (await apiClient.patch(`${base}/admin/${id}/estado`, { estado, motivo })).data;
  },
  async regenerar(id: string, motivo: string): Promise<Vale> {
    return (await apiClient.post(`${base}/admin/${id}/regenerar`, { motivo })).data;
  },
  async codigo(id: string): Promise<Vale> {
    return (await apiClient.get(`${base}/${id}/codigo`)).data;
  },
  async movimientos(id: string, offset = 0): Promise<MovimientoVale[]> {
    return (await apiClient.get(`${base}/${id}/movimientos`, { params: { offset } })).data;
  },
  async consultar(codigo: string): Promise<{ saldo: number | string }> {
    return (await apiClient.post(`${base}/consultar`, { codigo })).data;
  },
  async reservar(codigo: string, checkout_id: string, total: number): Promise<ReservaVale> {
    return (await apiClient.post(`${base}/reservas`, { codigo, checkout_id, total })).data;
  },
  async liberar(id: string): Promise<void> {
    await apiClient.delete(`${base}/reservas/${id}`);
  }
};
