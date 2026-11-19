import { apiClient } from './client';

export type TipoDescuento = 'porcentaje' | 'monto_fijo';
export type EstadoVigencia = 'vigente' | 'programado' | 'vencido' | 'agotado' | 'inactivo';

export interface ValidacionCupon {
  valido: boolean;
  codigo: string;
  motivo: string | null;
  mensaje: string;
  descuento: number;
  tipo_descuento: TipoDescuento | null;
  valor_descuento: number | null;
  monto_minimo: number;
  total_con_descuento: number;
}

export interface CuponAdmin {
  id?: string | null;
  codigo: string;
  descripcion: string | null;
  tipo_descuento: TipoDescuento;
  valor_descuento: number;
  monto_minimo: number;
  usos_maximos: number | null;
  usos_actuales: number;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  activo: boolean;
  estado_vigencia: EstadoVigencia;
}

export interface CuponAdminPayload {
  codigo?: string;
  descripcion?: string | null;
  tipo_descuento?: TipoDescuento;
  valor_descuento?: number;
  monto_minimo?: number;
  usos_maximos?: number | null;
  fecha_inicio?: string | null;
  fecha_fin?: string | null;
  activo?: boolean;
}

/** RF-17: valida el cupón contra el subtotal actual (no consume el cupón). */
export async function validarCupon(codigo: string, subtotal: number): Promise<ValidacionCupon> {
  const { data } = await apiClient.post<ValidacionCupon>('/api/v1/carrito/validar-cupon', { codigo, subtotal });
  return normalizarValidacion(data);
}

/** RF-17: consume un canje del cupón al confirmarse la compra. */
export async function canjearCupon(codigo: string, subtotal: number): Promise<ValidacionCupon> {
  const { data } = await apiClient.post<ValidacionCupon>('/api/v1/carrito/canjear-cupon', { codigo, subtotal });
  return normalizarValidacion(data);
}

function normalizarValidacion(data: ValidacionCupon): ValidacionCupon {
  return {
    ...data,
    descuento: Number(data.descuento),
    valor_descuento: data.valor_descuento === null ? null : Number(data.valor_descuento),
    monto_minimo: Number(data.monto_minimo),
    total_con_descuento: Number(data.total_con_descuento),
  };
}

function normalizarCupon(c: CuponAdmin): CuponAdmin {
  return { ...c, valor_descuento: Number(c.valor_descuento), monto_minimo: Number(c.monto_minimo) };
}

// --- Administración (roles: administrador, gerente_comercial) ---
export async function listarCupones(): Promise<CuponAdmin[]> {
  const { data } = await apiClient.get<CuponAdmin[]>('/api/v1/carrito/cupones');
  return data.map(normalizarCupon);
}

export async function crearCupon(payload: CuponAdminPayload): Promise<CuponAdmin> {
  const { data } = await apiClient.post<CuponAdmin>('/api/v1/carrito/cupones', payload);
  return normalizarCupon(data);
}

export async function actualizarCupon(codigo: string, cambios: CuponAdminPayload): Promise<CuponAdmin> {
  const { data } = await apiClient.patch<CuponAdmin>(`/api/v1/carrito/cupones/${encodeURIComponent(codigo)}`, cambios);
  return normalizarCupon(data);
}

export async function eliminarCupon(codigo: string): Promise<void> {
  await apiClient.delete(`/api/v1/carrito/cupones/${encodeURIComponent(codigo)}`);
}

/** Extrae el mensaje legible de un error de la API (FastAPI: detail string o lista de validaciones). */
export function mensajeDeError(err: any, porDefecto = 'No se pudo completar la operación.'): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d: any) => d.msg).join(' · ');
  return porDefecto;
}
