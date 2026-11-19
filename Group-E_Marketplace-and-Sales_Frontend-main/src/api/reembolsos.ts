import { apiClient } from './client';
import type {
  EstadoReembolso,
  ListaReembolsos,
  Reembolso,
  ReembolsosCreados,
  SolicitarReembolsoPayload
} from '@/types';

/** KAN-55: reembolsos totales o parciales de pagos aprobados (solo administrador). */
export const reembolsosApi = {
  async solicitar(payload: SolicitarReembolsoPayload): Promise<ReembolsosCreados> {
    const { data } = await apiClient.post<ReembolsosCreados>('/api/v1/reembolsos', payload);
    return data;
  },

  async reintentar(id: string, simularFallo = false): Promise<Reembolso> {
    const { data } = await apiClient.post<Reembolso>(`/api/v1/reembolsos/${id}/reintentar`, {
      simular_fallo: simularFallo
    });
    return data;
  },

  async listar(filtros: {
    estado?: EstadoReembolso | '';
    orden_id?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<ListaReembolsos> {
    const params: Record<string, string | number> = {};
    if (filtros.estado) params.estado = filtros.estado;
    if (filtros.orden_id) params.orden_id = filtros.orden_id;
    params.page = filtros.page ?? 1;
    params.limit = filtros.limit ?? 20;
    const { data } = await apiClient.get<ListaReembolsos>('/api/v1/reembolsos', { params });
    return data;
  }
};
