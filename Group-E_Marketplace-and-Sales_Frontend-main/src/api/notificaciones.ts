import { apiClient } from '@/api/client';

export type EstadoNotificacion = 'pendiente' | 'procesando' | 'enviada' | 'fallida';

export interface NotificacionLog {
  id: string;
  event_key: string;
  orden_id: string;
  cliente_id?: string | null;
  correo_destino: string;
  estado_orden: string;
  asunto: string;
  estado: EstadoNotificacion;
  intentos: number;
  max_intentos: number;
  proximo_intento_at: string;
  ultimo_error?: string | null;
  enviado_at?: string | null;
  creado_at: string;
  actualizado_at: string;
}

export interface NotificacionesLogResponse {
  items: NotificacionLog[];
  total: number;
  pagina: number;
  limite: number;
  total_paginas: number;
}

export async function obtenerBitacoraNotificaciones(params: {
  estado?: EstadoNotificacion | '';
  correo?: string;
  orden_id?: string;
  page?: number;
  limit?: number;
} = {}): Promise<NotificacionesLogResponse> {
  const { data } = await apiClient.get<NotificacionesLogResponse>('/api/v1/notificaciones', { params });
  return data;
}

export async function reenviarNotificacion(id: string): Promise<NotificacionLog> {
  const { data } = await apiClient.post<NotificacionLog>(`/api/v1/notificaciones/${encodeURIComponent(id)}/reenviar`);
  return data;
}
