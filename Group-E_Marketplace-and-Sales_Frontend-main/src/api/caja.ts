import { apiClient } from './client';
import type {
  CajaTurno,
  MovimientoCaja,
  MovimientosNetos,
  ArqueoCajaResultado,
  ArqueoCiegoPayload,
  ArqueoReporte,
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
    `/api/v1/pos/caja/${cajaId}/movimientos`,
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

export async function obtenerMovimientosNetosApi(cajaId: string): Promise<MovimientosNetos> {
  const res = await apiClient.get<MovimientosNetos>(`/api/v1/pos/caja/${cajaId}/movimientos/neto`);
  return res.data;
}

/**
 * KAN-342: confirmación de un supervisor. Inicia sesión con sus credenciales SOLO para obtener un token
 * de un uso; no toca la sesión del cajero (no se guarda en el store ni en localStorage).
 */
export async function obtenerTokenSupervisorApi(email: string, password: string): Promise<string> {
  const res = await apiClient.post<{ access_token: string; user: { role: string } }>(
    '/v1/clientes/auth/login',
    { email, password }
  );
  const rol = String(res.data.user?.role || '').toLowerCase();
  if (rol !== 'administrador' && rol !== 'supervisor') {
    throw new Error('El usuario indicado no tiene rol de supervisor.');
  }
  return res.data.access_token;
}

/** KAN-341: cierre del turno con arqueo ciego (el cajero declara el desglose sin ver el saldo teórico). */
export async function arqueoCiegoApi(cajaId: string, payload: ArqueoCiegoPayload): Promise<ArqueoReporte> {
  const res = await apiClient.post<ArqueoReporte>(`/api/v1/pos/caja/${cajaId}/arqueo-ciego`, payload);
  return res.data;
}

export async function obtenerReporteArqueoApi(cajaId: string): Promise<ArqueoReporte> {
  const res = await apiClient.get<ArqueoReporte>(`/api/v1/pos/caja/${cajaId}/arqueo`);
  return res.data;
}

/** @deprecated Cierre heredado con monto único (no ciego). Usa arqueoCiegoApi. */
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
