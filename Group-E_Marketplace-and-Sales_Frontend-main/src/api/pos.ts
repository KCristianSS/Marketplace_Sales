import { apiClient } from './client';

export interface VentaPOSReciente {
  orden_id: string;
  codigo_orden: string;
  total: number;
  numero_factura?: number | null;
  created_at?: string | null;
}

export async function obtenerVentasRecientesPos(cajaId: string): Promise<VentaPOSReciente[]> {
  const response = await apiClient.get<VentaPOSReciente[]>('/api/v1/pos/orders/recientes', {
    params: { caja_id: cajaId, limit: 10 }
  });
  return response.data;
}

export async function obtenerTicketParaReimpresion(ordenId: string) {
  const response = await apiClient.get(`/api/v1/pos/orders/${ordenId}/ticket`);
  return response.data;
}
