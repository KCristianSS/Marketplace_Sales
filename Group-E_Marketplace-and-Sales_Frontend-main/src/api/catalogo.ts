import { apiClient } from './client';

export interface StockDisponibilidad {
  sku: string;
  sucursal_id: string | null;
  stock_disponible: number;
  origen: 'cache' | 'erp';
  modo?: string | null;
}

export interface StockSucursal {
  sucursal_id: string;
  sucursal_nombre: string;
  stock_disponible: number;
}

export interface ProductoStockResumen {
  producto_id: string | null;
  sku: string;
  nombre: string;
  stock_total: number;
  sucursales: StockSucursal[];
}

export interface BusquedaStockResponse {
  query: string;
  resultados: ProductoStockResumen[];
  origen_cache: boolean;
}

export interface SyncCatalogoItem {
  id: string;
  sku: string;
  nombre: string;
  precio_referencia: number;
  estado: string;
  updated_at: string;
  accion: 'upsert' | 'baja';
}

export interface SyncCatalogoResponse {
  items: SyncCatalogoItem[];
  cursor_siguiente: string | null;
  hay_mas: boolean;
  servidor_timestamp: string;
}

/**
 * RF-07: Consulta la disponibilidad de stock en tiempo real de un SKU
 * (resuelta en el backend con caché Redis de 30s sobre RIO-INV-01).
 */
export async function consultarStock(sku: string, sucursalId?: string): Promise<StockDisponibilidad> {
  const { data } = await apiClient.get<StockDisponibilidad>(`/api/v1/catalogo/stock/${encodeURIComponent(sku)}`, {
    params: sucursalId ? { sucursal_id: sucursalId } : undefined,
  });
  return data;
}

/**
 * Consulta rápida de stock por SKU/nombre con desglose por sucursal,
 * usada por el modal de consulta rápida (atajo F3) en el POS.
 */
export async function buscarStockMultisucursal(query: string): Promise<BusquedaStockResponse> {
  const { data } = await apiClient.get<BusquedaStockResponse>('/api/v1/catalogo/productos/buscar-stock', {
    params: { q: query },
  });
  return data;
}

/**
 * RF-08 [BE]: Trae el lote de productos creados/modificados después de `since`
 * (paginado por cursor), para hidratar/actualizar la caché local del POS.
 */
export async function sincronizarCatalogoDelta(since?: string, cursor?: string): Promise<SyncCatalogoResponse> {
  const { data } = await apiClient.get<SyncCatalogoResponse>('/api/v1/catalogo/sync-catalogo', {
    params: {
      ...(since ? { since } : {}),
      ...(cursor ? { cursor } : {}),
      page_size: 50,
    },
  });
  return data;
}

/**
 * RF-08 [BE]: Abre una conexión SSE persistente al notificador de cambios de
 * catálogo. El caller es responsable de cerrar el EventSource retornado
 * (p. ej. en el `onUnmounted` del componente/store que lo usa).
 */
export function suscribirseACambiosDeCatalogo(
  onEvento: (evento: SyncCatalogoItem & { tipo: string; emitido_en: string }) => void,
  onConexion?: (conectado: boolean) => void
): EventSource {
  const baseURL = apiClient.defaults.baseURL || 'http://localhost:8000';
  const source = new EventSource(`${baseURL}/api/v1/catalogo/sync-events`);

  source.addEventListener('connected', () => onConexion?.(true));
  source.addEventListener('catalogo-actualizado', (ev: MessageEvent) => {
    try {
      onEvento(JSON.parse(ev.data));
    } catch (err) {
      console.warn('No se pudo interpretar el evento de sincronización de catálogo:', err);
    }
  });
  source.onerror = () => onConexion?.(false);

  return source;
}

export interface SyncStatusResponse {
  suscriptores_activos: number;
  total_productos: number;
  ultima_sincronizacion: string | null;
  eventos_recientes: Array<{
    tipo: string;
    mensaje?: string;
    producto_id?: string;
    sku?: string;
    nombre?: string;
    precio?: number;
    estado?: string;
    total_productos?: number;
    origen?: string;
    emitido_en: string;
  }>;
  estado: string;
}

/**
 * RF-08: Obtiene métricas del Hub de sincronización multicanal (suscriptores activos, total catálogo, etc.)
 */
export async function obtenerEstadoSincronizacion(): Promise<SyncStatusResponse> {
  const { data } = await apiClient.get<SyncStatusResponse>('/api/v1/catalogo/sync-status');
  return data;
}

/**
 * RF-08: Emite un broadcast SSE forzado a todas las terminales POS para refrescar el catálogo.
 */
export async function forzarSincronizacionCatalogo(): Promise<{
  mensaje: string;
  suscriptores_notificados: number;
  total_productos: number;
  timestamp: string;
}> {
  const { data } = await apiClient.post('/api/v1/catalogo/sync-catalogo/forzar');
  return data;
}

// ============================================================================
// RF-04 / US-04: API DE LISTAS DE PRECIOS DIFERENCIADAS
// ============================================================================
import type { ListaPrecio, PrecioItem, PrecioResolucion } from '@/types';

export async function obtenerListasPrecios(params?: {
  canal?: string;
  tipo_cliente?: string;
  sucursal_id?: string;
  activo?: boolean;
}): Promise<ListaPrecio[]> {
  const { data } = await apiClient.get<ListaPrecio[]>('/api/v1/catalogo/listas-precios', { params });
  return data;
}

export async function crearListaPrecio(payload: Partial<ListaPrecio>): Promise<ListaPrecio> {
  const { data } = await apiClient.post<ListaPrecio>('/api/v1/catalogo/listas-precios', payload);
  return data;
}

export async function actualizarListaPrecio(id: string, payload: Partial<ListaPrecio>): Promise<ListaPrecio> {
  const { data } = await apiClient.put<ListaPrecio>(`/api/v1/catalogo/listas-precios/${id}`, payload);
  return data;
}

export async function eliminarListaPrecio(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/catalogo/listas-precios/${id}`);
}

export async function obtenerItemsListaPrecio(listaId: string): Promise<PrecioItem[]> {
  const { data } = await apiClient.get<PrecioItem[]>(`/api/v1/catalogo/listas-precios/${listaId}/items`);
  return data;
}

export async function asignarPrecioItem(listaId: string, payload: {
  variante_id: string;
  precio: number;
  fecha_inicio?: string;
  fecha_fin?: string;
}): Promise<PrecioItem> {
  const { data } = await apiClient.post<PrecioItem>(`/api/v1/catalogo/listas-precios/${listaId}/items`, payload);
  return data;
}

export async function eliminarPrecioItem(listaId: string, itemId: string): Promise<void> {
  await apiClient.delete(`/api/v1/catalogo/listas-precios/${listaId}/items/${itemId}`);
}

export async function resolverPrecioVariante(params: {
  variante_id: string;
  canal: string;
  tipo_cliente: string;
  sucursal_id?: string;
}): Promise<PrecioResolucion> {
  const { data } = await apiClient.get<PrecioResolucion>('/api/v1/catalogo/precios/resolver', { params });
  return data;
}

export async function resolverPreciosLote(params: {
  variante_ids: string[];
  canal: 'web' | 'pos' | 'b2b';
  tipo_cliente: 'retail' | 'corporativo_b2b';
  sucursal_id?: string;
}): Promise<Record<string, PrecioResolucion>> {
  const { data } = await apiClient.get<Record<string, PrecioResolucion>>('/api/v1/catalogo/precios/resolver-lote', {
    params: { ...params, variante_ids: params.variante_ids.join(',') }
  });
  return data;
}

export async function obtenerPreciosProducto(productoId: string): Promise<PrecioItem[]> {
  const { data } = await apiClient.get<PrecioItem[]>(`/api/v1/catalogo/productos/${productoId}/precios`);
  return data;
}

// ============================================================================
// RF-18 / US-18: COMBOS Y PAQUETES COMERCIALES
// ============================================================================
import type { Combo, ComboCreatePayload, ComboDisponibilidad } from '@/types';

export async function obtenerCombos(params?: {
  solo_activos?: boolean;
  q?: string;
}): Promise<Combo[]> {
  const { data } = await apiClient.get<Combo[]>('/api/v1/catalogo/combos', { params });
  return data;
}

export async function obtenerComboPorId(comboId: string): Promise<Combo> {
  const { data } = await apiClient.get<Combo>(`/api/v1/catalogo/combos/${comboId}`);
  return data;
}

export async function consultarDisponibilidadCombo(comboId: string): Promise<ComboDisponibilidad> {
  const { data } = await apiClient.get<ComboDisponibilidad>(`/api/v1/catalogo/combos/${comboId}/disponibilidad`);
  return data;
}

export async function crearCombo(payload: ComboCreatePayload): Promise<Combo> {
  const { data } = await apiClient.post<Combo>('/api/v1/catalogo/combos', payload);
  return data;
}

export async function actualizarCombo(comboId: string, payload: Partial<ComboCreatePayload>): Promise<Combo> {
  const { data } = await apiClient.put<Combo>(`/api/v1/catalogo/combos/${comboId}`, payload);
  return data;
}

export async function eliminarCombo(comboId: string): Promise<void> {
  await apiClient.delete(`/api/v1/catalogo/combos/${comboId}`);
}
