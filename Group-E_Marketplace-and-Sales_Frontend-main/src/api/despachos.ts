import { apiClient } from './client';

export interface EventoDespacho {
  id: string;
  tipo_evento: string;
  estado: string;
  intentos: number;
  message_id: string | null;
  ultimo_error: string | null;
  created_at: string;
}
export interface Despacho {
  id: string;
  orden_id: string;
  estado: string;
  guia: string | null;
  version: number;
  transportista: string | null;
  ruta: string | null;
  ubicacion_actual: string | null;
  fecha_estimada: string | null;
  actualizado_en: string;
  motivo: string | null;
  eventos: EventoDespacho[];
}
export interface TrazaEnvio {
  id: string;
  event_id: string;
  tipo_evento: string;
  direccion: 'entrada' | 'salida';
  estado: string;
  orden_id: string | null;
  correlation_id: string | null;
  simulacion: boolean;
  topic: string | null;
  message_id: string | null;
  intentos: number;
  ultimo_error: string | null;
  estado_logistico: string | null;
  mensaje: Record<string, unknown>;
  atributos: Record<string, unknown>;
  created_at: string;
  registro: 'mensaje' | 'estado_actual' | 'metadatos_historicos';
}
export interface TrazabilidadEnvios {
  items: TrazaEnvio[];
  total: number;
  pagina: number;
  total_paginas: number;
}
export interface FiltrosTrazabilidad {
  orden_id?: string;
  estado?: string;
  tipo_evento?: string;
  direccion?: 'entrada' | 'salida';
  simulacion?: boolean;
  estado_logistico?: string;
  page?: number;
  limit?: number;
}
export const despachosApi = {
  async trazabilidad(filtros: FiltrosTrazabilidad = {}): Promise<TrazabilidadEnvios> {
    return (await apiClient.get('/api/v1/ordenes/despachos/trazabilidad', { params: filtros })).data;
  },
  async obtener(id: string): Promise<Despacho> {
    return (await apiClient.get(`/api/v1/ordenes/${encodeURIComponent(id)}/despacho`)).data;
  },
  async consultar(id: string): Promise<Despacho> {
    return (await apiClient.post(`/api/v1/ordenes/${encodeURIComponent(id)}/despacho/consultar`)).data;
  },
  async reintentar(id: string): Promise<Despacho> {
    return (await apiClient.post(`/api/v1/ordenes/${encodeURIComponent(id)}/despacho/reintentar`)).data;
  }
};
