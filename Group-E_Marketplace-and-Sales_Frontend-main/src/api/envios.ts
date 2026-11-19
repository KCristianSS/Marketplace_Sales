import { apiClient } from './client';

export interface ZonaEnvio {
  id: string;
  ciudad: string;
  nombre: string;
  tarifa_base: number;
  activa: boolean;
  estandar_habilitado: boolean;
  express_habilitado: boolean;
  plazo_estandar: string;
  plazo_express: string;
}

export interface ConfiguracionEnvios {
  envio_gratis_habilitado: boolean;
  umbral_envio_gratis: number;
  recargo_express: number;
  peso_incluido_kg: number;
  recargo_por_kg: number;
  peso_estimado_por_unidad_kg: number;
  zonas: ZonaEnvio[];
}

export interface RegistroEnvios {
  version: number;
  configuracion: ConfiguracionEnvios;
  actualizado_por: string | null;
  actualizado_en: string | null;
  almacenamiento: 'base_datos' | 'memoria';
}

export interface OpcionesEnvio {
  version: number;
  envio_gratis_habilitado: boolean;
  umbral_envio_gratis: number;
  zonas: Omit<ZonaEnvio, 'activa'>[];
}

function normalizarRegistro(registro: RegistroEnvios): RegistroEnvios {
  const config = registro.configuracion;
  return { ...registro, configuracion: {
    ...config,
    umbral_envio_gratis: Number(config.umbral_envio_gratis),
    recargo_express: Number(config.recargo_express),
    peso_incluido_kg: Number(config.peso_incluido_kg),
    recargo_por_kg: Number(config.recargo_por_kg),
    peso_estimado_por_unidad_kg: Number(config.peso_estimado_por_unidad_kg),
    zonas: config.zonas.map(zona => ({ ...zona, tarifa_base: Number(zona.tarifa_base) })),
  } };
}

export async function obtenerConfiguracionEnvios(): Promise<RegistroEnvios> {
  const { data } = await apiClient.get<RegistroEnvios>('/api/v1/ordenes/flete/configuracion');
  return normalizarRegistro(data);
}

export async function guardarConfiguracionEnvios(version: number, configuracion: ConfiguracionEnvios): Promise<RegistroEnvios> {
  const { data } = await apiClient.put<RegistroEnvios>('/api/v1/ordenes/flete/configuracion', { version, configuracion });
  return normalizarRegistro(data);
}

export async function obtenerOpcionesEnvio(): Promise<OpcionesEnvio> {
  const { data } = await apiClient.get<OpcionesEnvio>('/api/v1/ordenes/flete/opciones');
  return { ...data, umbral_envio_gratis: Number(data.umbral_envio_gratis),
    zonas: data.zonas.map(zona => ({ ...zona, tarifa_base: Number(zona.tarifa_base) })) };
}

export function mensajeErrorEnvios(error: any, defecto: string): string {
  const detalle = error.response?.data?.detail;
  if (typeof detalle === 'string') return detalle;
  if (Array.isArray(detalle)) return detalle.map(item => item.msg).join(' ');
  return defecto;
}
