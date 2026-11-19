import { apiClient } from './client';

export interface VentaPOSReciente {
  orden_id: string;
  codigo_orden: string;
  total: number;
  numero_factura?: number | null;
  created_at?: string | null;
  estado_venta?: 'completada' | 'anulando' | 'anulada' | 'anulacion_pendiente';
  motivo_anulacion?: string | null;
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

// ============================================================================
// HISTORIA KAN-10 / KAN-345: DESCUENTO MANUAL AUTORIZADO (KAN-362, KAN-392)
// ============================================================================

export interface AutorizarDescuentoRequest {
  supervisor_username: string;
  pin: string;
  tipo: 'item' | 'total';
  porcentaje: number;
  monto_base: number;
  motivo: string;
  item_sku?: string;
  cajero_id?: string;
  cajero_nombre?: string;
  sucursal_id?: string;
}

export interface AutorizacionDescuentoResponse {
  autorizacion_id: string;
  autorizado: boolean;
  supervisor_id: string;
  supervisor_nombre: string;
  tipo: 'item' | 'total';
  item_sku?: string;
  porcentaje: number;
  monto_base: number;
  monto_descuento: number;
  motivo: string;
  expires_at: string;
  mensaje: string;
}

export async function autorizarDescuentoManual(
  payload: AutorizarDescuentoRequest
): Promise<AutorizacionDescuentoResponse> {
  const response = await apiClient.post<AutorizacionDescuentoResponse>(
    '/api/v1/pos/descuentos/autorizar',
    payload
  );
  return response.data;
}

export async function anularVentaPos(
  ordenId: string,
  payload: { caja_id: string; motivo: string; supervisor_username: string; pin: string },
) {
  const response = await apiClient.post(`/api/v1/pos/ventas/${ordenId}/anular`, payload);
  return response.data;
}
