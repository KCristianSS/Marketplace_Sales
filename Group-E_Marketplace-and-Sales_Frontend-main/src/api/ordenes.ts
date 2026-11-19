import { apiClient } from '@/api/client';
import type {
  EstadoOrden,
  HistorialOrdenesFiltros,
  HistorialOrdenesResponse,
  OrdenHistorial,
  RecompraResponse
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

export interface EventoSeguimiento {
  estado: EstadoOrden;
  fecha_hora: string | null;
  actual: boolean;
}

export interface SeguimientoPedido {
  orden_id: string;
  codigo_orden: string;
  estado_actual: EstadoOrden;
  tipo_despacho: 'domicilio' | 'retiro_sucursal' | string;
  tracking_number: string | null;
  fecha_estimada: string | null;
  tipo_estimacion: 'entrega' | 'retiro';
  motivo_cancelacion: string | null;
  historial: EventoSeguimiento[];
}

export async function obtenerSeguimientoPedido(id: string): Promise<SeguimientoPedido> {
  const { data } = await apiClient.get<SeguimientoPedido>(`/api/v1/ordenes/${encodeURIComponent(id)}/seguimiento`);
  return data;
}

/** Consume el SSE con Bearer JWT sin exponer el token en la URL. */
export async function escucharSeguimientoPedido(
  id: string,
  signal: AbortSignal,
  onUpdate: (seguimiento: SeguimientoPedido) => void
): Promise<void> {
  const token = localStorage.getItem('maxiconecta_token');
  const response = await fetch(`${apiClient.defaults.baseURL}/api/v1/ordenes/${encodeURIComponent(id)}/seguimiento/stream`, {
    headers: token ? { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' } : { Accept: 'text/event-stream' },
    signal
  });
  if (!response.ok || !response.body) throw new Error(`El stream respondió ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const mensajes = buffer.split('\n\n');
    buffer = mensajes.pop() || '';
    for (const mensaje of mensajes) {
      const data = mensaje.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n');
      if (data) onUpdate(JSON.parse(data) as SeguimientoPedido);
    }
  }
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

/** KAN-54: crea una orden en estado «pendiente» (sin cobrar) para registrar sus pagos después. */
export async function crearOrdenPendiente(payload: {
  canal?: 'web' | 'pos' | 'b2b';
  items: { variante_id: string; sku: string; nombre_producto: string; cantidad: number; precio_unitario: number }[];
}): Promise<OrdenHistorial> {
  const { data } = await apiClient.post<OrdenHistorial>('/api/v1/ordenes/pendiente', { canal: 'pos', ...payload });
  return data;
}
/** Prepara la recompra sin crear órdenes, cobros ni reservas. */
export async function prepararRecompra(id: string): Promise<RecompraResponse> {
  const { data } = await apiClient.post<RecompraResponse>(`/api/v1/ordenes/${encodeURIComponent(id)}/repetir`);
  return {
    ...data,
    items: data.items.map(item => ({ ...item, precio_unitario: Number(item.precio_unitario) }))
  };
}
