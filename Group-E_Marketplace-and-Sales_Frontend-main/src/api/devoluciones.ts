import { apiClient } from '@/api/client';

export interface ItemDevolucion {
  orden_item_id: string;
  variante_id: string;
  sku: string;
  nombre_producto: string;
  cantidad: number;
  precio_unitario: number;
}

export interface Devolucion {
  id: string;
  orden_id: string;
  cliente_id: string;
  motivo: string;
  items: ItemDevolucion[];
  evidencia_urls: string[];
  estado: 'solicitada' | 'aprobada' | 'rechazada' | 'completada';
  comentario_resolucion?: string | null;
  created_at: string;
  resolucion_at?: string | null;
  ordenes?: { codigo_orden?: string };
}

export async function listarDevoluciones(): Promise<Devolucion[]> {
  const { data } = await apiClient.get<Devolucion[]>('/api/v1/ordenes/devoluciones/solicitudes');
  return data;
}

export async function solicitarDevolucion(payload: {
  ordenId: string;
  motivo: string;
  items: ItemDevolucion[];
  evidencias: File[];
}): Promise<Devolucion> {
  const form = new FormData();
  form.append('orden_id', payload.ordenId);
  form.append('motivo', payload.motivo);
  form.append('items', JSON.stringify(payload.items));
  payload.evidencias.forEach(file => form.append('evidencias', file));
  const { data } = await apiClient.post<Devolucion>('/api/v1/ordenes/devoluciones', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}

export async function resolverDevolucion(id: string, accion: 'aprobar' | 'rechazar', comentario: string): Promise<Devolucion> {
  const form = new FormData();
  form.append('accion', accion);
  form.append('comentario', comentario);
  const { data } = await apiClient.patch<Devolucion>(`/api/v1/ordenes/devoluciones/${encodeURIComponent(id)}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return data;
}
