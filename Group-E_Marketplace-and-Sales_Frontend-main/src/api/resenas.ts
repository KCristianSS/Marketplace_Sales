import { apiClient } from '@/api/client';

export type EstadoModeracionResena = 'pendiente' | 'aprobada' | 'rechazada';

export interface Resena {
  id: string;
  producto_id: string;
  producto_nombre?: string | null;
  producto_sku?: string | null;
  cliente_id: string;
  orden_id: string;
  codigo_orden?: string | null;
  nombre_cliente?: string | null;
  calificacion: number;
  comentario: string;
  estado_moderacion: EstadoModeracionResena;
  motivo_rechazo?: string | null;
  created_at: string;
}

export interface OrdenElegibleResena {
  orden_id: string;
  codigo_orden: string;
  entregada_el: string;
}

export async function listarResenasAprobadas(productoId: string): Promise<Resena[]> {
  const { data } = await apiClient.get<Resena[]>(`/api/v1/ordenes/resenas/producto/${productoId}`);
  return data;
}

export async function listarOrdenesElegibles(productoId: string): Promise<OrdenElegibleResena[]> {
  const { data } = await apiClient.get<OrdenElegibleResena[]>(`/api/v1/ordenes/resenas/elegibles/${productoId}`);
  return data;
}

export async function enviarResena(payload: {
  producto_id: string;
  orden_id: string;
  calificacion: number;
  comentario: string;
}): Promise<Resena> {
  const { data } = await apiClient.post<Resena>('/api/v1/ordenes/resenas', payload);
  return data;
}

export async function listarResenasPendientes(): Promise<Resena[]> {
  const { data } = await apiClient.get<Resena[]>('/api/v1/ordenes/resenas/pendientes');
  return data;
}

export async function moderarResena(id: string, payload: { accion: 'aprobar' | 'rechazar'; motivo?: string }): Promise<Resena> {
  const { data } = await apiClient.patch<Resena>(`/api/v1/ordenes/resenas/${id}/moderacion`, payload);
  return data;
}
