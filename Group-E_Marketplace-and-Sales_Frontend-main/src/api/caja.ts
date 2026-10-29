import { apiClient } from './client';
import type {
  CajaTurno,
  MovimientoCaja,
  ArqueoCajaResultado,
  AbrirCajaPayload,
  MovimientoCajaPayload,
  CerrarCajaPayload
} from '@/types';

/**
 * Servicio API para Apertura, Control y Cierre de Caja por Turno (RF-09).
 */

export async function obtenerCajaActivaApi(): Promise<CajaTurno | null> {
  try {
    const res = await apiClient.get<CajaTurno>('/api/v1/pos/caja/activa');
    return res.data;
  } catch (err: any) {
    if (err.response?.status === 404) {
      return null;
    }
    throw err;
  }
}

export async function abrirCajaApi(payload: AbrirCajaPayload): Promise<CajaTurno> {
  const res = await apiClient.post<CajaTurno>('/api/v1/pos/caja/abrir', payload);
  return res.data;
}

export async function obtenerCajaPorIdApi(cajaId: string): Promise<CajaTurno> {
  const res = await apiClient.get<CajaTurno>(`/api/v1/pos/caja/${cajaId}`);
  return res.data;
}

export async function registrarMovimientoCajaApi(
  cajaId: string,
  payload: MovimientoCajaPayload
): Promise<MovimientoCaja> {
  const res = await apiClient.post<MovimientoCaja>(
    `/api/v1/pos/caja/${cajaId}/movimiento`,
    payload
  );
  return res.data;
}

export async function listarMovimientosCajaApi(
  cajaId: string
): Promise<MovimientoCaja[]> {
  const res = await apiClient.get<MovimientoCaja[]>(
    `/api/v1/pos/caja/${cajaId}/movimientos`
  );
  return res.data;
}

export async function cerrarCajaApi(
  cajaId: string,
  payload: CerrarCajaPayload
): Promise<ArqueoCajaResultado> {
  const res = await apiClient.post<ArqueoCajaResultado>(
    `/api/v1/pos/caja/${cajaId}/cerrar`,
    payload
  );
  return res.data;
}

export async function obtenerHistorialCajasApi(
  limit: number = 20,
  offset: number = 0
): Promise<CajaTurno[]> {
  const res = await apiClient.get<CajaTurno[]>('/api/v1/pos/caja/historial', {
    params: { limit, offset }
  });
  return res.data;
}
