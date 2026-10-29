import { apiClient } from '@/api/client';
import type {
  EstadoOrden,
  HistorialOrdenesFiltros,
  HistorialOrdenesResponse,
  OrdenHistorial
} from '@/types';

/**
 * Consulta el historial. El backend determina el alcance final desde el JWT:
 * un cliente solo recibe sus propias compras.
 */
export async function obtenerHistorialOrdenes(
  filtros: HistorialOrdenesFiltros = {}
): Promise<HistorialOrdenesResponse> {
  const { data } = await apiClient.get<HistorialOrdenesResponse>('/api/v1/ordenes/', {
    params: filtros
  });
  return data;
}

export async function obtenerOrden(id: string): Promise<OrdenHistorial> {
  const { data } = await apiClient.get<OrdenHistorial>(`/api/v1/ordenes/${encodeURIComponent(id)}`);
  return data;
}

/** RF-28: avanza la orden por la máquina de estados; el backend valida la transición. */
export async function cambiarEstadoOrden(id: string, nuevoEstado: EstadoOrden): Promise<OrdenHistorial> {
  const { data } = await apiClient.patch<OrdenHistorial>(
    `/api/v1/ordenes/${encodeURIComponent(id)}/estado`,
    { nuevo_estado: nuevoEstado }
  );
  return data;
}

/** Descarga el XML fiscal autenticado como Blob; el JWT no viaja en la URL. */
export async function descargarFacturaXml(cuf: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(
    `/api/v1/facturacion/facturas/${encodeURIComponent(cuf)}/xml`,
    { responseType: 'blob' }
  );
  return data;
}

/** Obtiene el HTML imprimible autenticado del comprobante o factura. */
export async function obtenerFacturaImpresion(cuf: string): Promise<string> {
  const { data } = await apiClient.get<string>(
    `/api/v1/facturacion/facturas/${encodeURIComponent(cuf)}/impresion`,
    { responseType: 'text' }
  );
  return data;
}
