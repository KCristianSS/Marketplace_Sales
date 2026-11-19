import { apiClient } from '@/api/client';

export interface ClienteCorporativo {
  id: string;
  nombre_completo: string;
  razon_social?: string | null;
  nit_ci: string;
  email: string;
  telefono?: string | null;
}

export interface ConfiguracionDescuentosB2B {
  habilitado: boolean;
  escalas: Array<{ minimo_unidades: number; descuento_porcentaje: number }>;
}
export interface ReglasDescuentosB2B {
  version: number;
  configuracion: ConfiguracionDescuentosB2B;
  actualizado_por: string | null;
  actualizado_en: string;
}
function normalizarReglas(data: ReglasDescuentosB2B): ReglasDescuentosB2B {
  return { ...data, configuracion: { ...data.configuracion, escalas: data.configuracion.escalas.map(e => ({
    minimo_unidades: Number(e.minimo_unidades), descuento_porcentaje: Number(e.descuento_porcentaje)
  })) } };
}
export async function obtenerReglasB2B(): Promise<ReglasDescuentosB2B> {
  const { data } = await apiClient.get<ReglasDescuentosB2B>('/api/v1/cotizaciones/configuracion');
  return normalizarReglas(data);
}
export async function guardarReglasB2B(version: number, configuracion: ConfiguracionDescuentosB2B): Promise<ReglasDescuentosB2B> {
  const { data } = await apiClient.put<ReglasDescuentosB2B>('/api/v1/cotizaciones/configuracion', { version, configuracion });
  return normalizarReglas(data);
}
export async function registrarEmpresaB2B(payload: { nit_ci: string; razon_social: string; email: string; nombre_completo?: string; telefono?: string }): Promise<{ cliente: ClienteCorporativo; creado: boolean }> {
  const { data } = await apiClient.post<{ cliente: ClienteCorporativo; creado: boolean }>('/api/v1/clientes/corporativos', payload);
  return data;
}
export function errorB2B(err: any, fallback: string): string {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg).filter(Boolean).join(' ') || fallback : fallback;
}

export interface CotizacionItem {
  variante_id: string;
  sku: string;
  nombre_producto: string;
  cantidad: number;
  precio_unitario: number;
  total_linea: number;
}

export interface CotizacionB2B {
  id: string;
  codigo_cotizacion: string;
  cliente_id: string;
  nombre_cliente: string;
  razon_social?: string | null;
  nit_ci: string;
  gerente_id?: string | null;
  subtotal: number;
  descuento_porcentaje: number;
  descuento_monto: number;
  total: number;
  vigencia_dias: number;
  vigencia_hasta: string;
  estado: 'emitida' | 'pendiente_aprobacion' | 'aprobada' | 'rechazada' | 'convertida' | 'vencida';
  created_at: string;
  items: CotizacionItem[];
}

export interface CotizacionesResponse {
  items: CotizacionB2B[];
  total: number;
  pagina: number;
  limite: number;
  total_paginas: number;
}

export async function buscarClientesCorporativos(q = ''): Promise<ClienteCorporativo[]> {
  const { data } = await apiClient.get<ClienteCorporativo[]>('/api/v1/cotizaciones/clientes', { params: { q: q || undefined } });
  return data;
}

export async function emitirCotizacion(payload: {
  cliente_id: string;
  vigencia_dias: 7 | 15 | 30;
  items: Array<{ variante_id: string; cantidad: number }>;
  configuracion_descuento_version?: number;
}): Promise<CotizacionB2B> {
  const { data } = await apiClient.post<CotizacionB2B>('/api/v1/cotizaciones', payload);
  return data;
}

export async function listarCotizaciones(params: {
  estado?: string;
  cliente_id?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  page?: number;
  limit?: number;
} = {}): Promise<CotizacionesResponse> {
  const { data } = await apiClient.get<CotizacionesResponse>('/api/v1/cotizaciones', { params });
  return data;
}

export async function descargarCotizacionPdf(id: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/api/v1/cotizaciones/${encodeURIComponent(id)}/pdf`, { responseType: 'blob' });
  return data;
}
