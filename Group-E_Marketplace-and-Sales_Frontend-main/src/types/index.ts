export interface Categoria {
  id: string;
  nombre: string;
  descripcion?: string;
  padre_id?: string;
}

export interface Variante {
  id: string;
  producto_id: string;
  sku: string;
  nombre_variante: string;
  atributos: Record<string, any>;
  precio: number;
  precio_costo?: number;
  codigo_barras?: string;
}

export interface ImagenProducto {
  id: string;
  producto_id: string;
  variante_id?: string | null;
  url: string;
  thumbnailUrl?: string;
  es_principal: boolean;
  orden: number;
  created_at?: string;
  stats?: {
    nombreOriginal?: string;
    pesoOriginalBytes?: number;
    pesoOptimizadoBytes?: number;
    pesoThumbnailBytes?: number;
    porcentajeAhorro?: number;
  };
}

export interface Producto {
  id: string;
  sku: string;
  nombre: string;
  descripcion?: string;
  marca?: string;
  categoria_id: string;
  estado: string;
  variantes?: Variante[];
  categorias?: { id: string; nombre: string };
  imagenes_producto?: ImagenProducto[];
  precio?: number;
  precio_costo?: number;
  variante_id?: string;
}

export interface ItemCarrito {
  variante_id: string;
  sku: string;
  nombre: string;
  cantidad: number;
  precio_unitario: number;
  total_linea: number;
  stock_disponible?: number;
}

export interface Carrito {
  cliente_o_sesion_id: string;
  items: ItemCarrito[];
  subtotal: number;
  descuento_cupon: number;
  cupon_codigo?: string;
  total: number;
}

export type UserRole = 'cliente' | 'cajero' | 'administrador' | 'gerente_comercial';

export interface UserProfile {
  id: string;
  user_id?: string;
  nombre_completo: string;
  email: string;
  telefono?: string;
  nit_ci?: string;
  razon_social?: string;
  tipo_cliente?: string;
  role: UserRole;
  sucursal_id?: string | null;
  puntos_saldo: number;
  mensaje?: string;
}

export interface DireccionCliente {
  id: string;
  cliente_id: string;
  direccion: string;
  referencia?: string | null;
  ciudad: string;
  latitud?: number | null;
  longitud?: number | null;
  es_predeterminada: boolean;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  nombre_completo: string;
  email: string;
  password: string;
  telefono?: string;
  nit_ci?: string;
  razon_social?: string;
  tipo_cliente?: string;
}

export interface OrderSummary {
  id: string;
  codigo: string;
  fecha: string;
  total: number;
  estado: 'pendiente' | 'confirmada' | 'en_preparacion' | 'despachada' | 'entregada' | 'cancelada';
  items_count: number;
  metodo_pago: string;
}

// ============================================================================
// US-37 / RF-37: HISTORIAL DE COMPRAS, ÓRDENES Y COMPROBANTES
// ============================================================================
export type EstadoOrden =
  | 'pendiente'
  | 'confirmada'
  | 'en_preparacion'
  | 'despachada'
  | 'entregada'
  | 'cancelada';

export interface ItemOrdenHistorial {
  id: string;
  variante_id: string;
  sku: string;
  nombre_producto: string;
  cantidad: number;
  precio_unitario: number;
  total_linea: number;
}

export interface PagoOrdenHistorial {
  metodo: string;
  monto: number;
  transaccion_id?: string;
  referencia?: string;
}

export interface FacturaOrdenHistorial {
  numero_factura?: number;
  cuf?: string;
  fecha_emision?: string;
  modalidad?: 'con_factura' | 'sin_factura' | string;
  datos_comprador?: {
    tipo_documento?: string;
    nit_ci?: string;
    razon_social?: string;
    email_facturacion?: string;
  };
  monto_total?: number;
  monto_iva?: number;
  codigo_qr?: string;
}

export interface OrdenHistorial {
  id: string;
  codigo_orden: string;
  cliente_id: string;
  canal: string;
  tipo_despacho: 'domicilio' | 'retiro_sucursal' | string;
  subtotal: number;
  descuento: number;
  costo_envio: number;
  total: number;
  estado: EstadoOrden;
  tracking_number?: string | null;
  cuf_factura?: string | null;
  numero_factura?: number | null;
  factura?: FacturaOrdenHistorial | null;
  created_at: string;
  items: ItemOrdenHistorial[];
  pagos: PagoOrdenHistorial[];
  motivo_cancelacion?: string | null;
  historial_estados?: TransicionEstadoOrden[];
}

export interface TransicionEstadoOrden {
  estado_anterior: EstadoOrden;
  estado_nuevo: EstadoOrden;
  usuario_id: string;
  rol?: string | null;
  cambiado_en: string;
}

export interface HistorialOrdenesResponse {
  items: OrdenHistorial[];
  total: number;
  pagina: number;
  limite: number;
  total_paginas: number;
}

export interface HistorialOrdenesFiltros {
  cliente_id?: string;
  codigo_orden?: string;
  estado?: EstadoOrden;
  canal?: string;
  fecha_desde?: string;
  fecha_hasta?: string;
  busqueda?: string;
  page?: number;
  limit?: number;
}

export interface WishlistItem {
  id: string;
  cliente_id?: string;
  variante_id: string;
  created_at: string;
  sku?: string;
  nombre?: string;
  precio?: number;
  imagen_url?: string;
}

// ============================================================================
// HISTORIA KAN-346 / KAN-13: DATOS FISCALES Y FACTURACIÓN ELECTRÓNICA
// ============================================================================
export type TipoDocumentoFiscal = 'NIT' | 'CI' | 'CEX' | 'PAS';

export interface DatosFiscales {
  modalidad: 'con_factura' | 'sin_factura';
  tipo_documento: TipoDocumentoFiscal;
  nit_ci: string;
  razon_social: string;
  email_facturacion?: string;
  guardar_perfil?: boolean;
}

export interface PerfilFiscal {
  id: string;
  cliente_id?: string;
  tipo_documento: TipoDocumentoFiscal;
  nit_ci: string;
  razon_social: string;
  email_facturacion?: string;
  es_predeterminado?: boolean;
  creado_el?: string;
}

export interface ValidacionNitResponse {
  valido: boolean;
  nit_ci: string;
  razon_social?: string;
  estado: 'ACTIVO' | 'INACTIVO' | 'NO_ENCONTRADO';
  mensaje?: string;
}

export interface FacturaEmitida {
  id: string;
  numero_factura: number;
  cuf: string;
  cufd: string;
  fecha_emision: string;
  modalidad: 'con_factura' | 'sin_factura';
  datos_comprador: {
    tipo_documento: TipoDocumentoFiscal;
    nit_ci: string;
    razon_social: string;
    email_facturacion?: string;
  };
  sucursal: string;
  punto_venta: number;
  total: number;
  total_sujeto_iva: number;
  descuento: number;
  metodo_pago: string;
  /** Transacciones de pago (más de una cuando se dividió el pago). */
  pagos?: PagoProcesadoPos[];
  cambio_total?: number;
  codigo_qr: string;
  tipo_despacho?: 'domicilio' | 'retiro_sucursal';
  costo_envio?: number;
  subtotal?: number;
  codigo_retiro?: string;
  tracking_number?: string;
  datos_despacho?: any;
  items: Array<{
    sku: string;
    nombre: string;
    cantidad: number;
    precio_unitario: number;
    subtotal: number;
  }>;
}

export type CheckoutModalidad = 'domicilio' | 'retiro_sucursal';
export type CheckoutMetodoPago = 'tarjeta' | 'qr' | 'pasarela';
export type ReservaStockStatus = 'idle' | 'reservando' | 'activa' | 'expirada' | 'confirmada' | 'error';

export interface ReservaStockResponse {
  reserva_id: string;
  ttl_expira_en_segundos: number;
  expira_en_timestamp?: number;
  monto_total: number;
  metodo_pago?: string;
  status: string;
  mensaje?: string;
}

export interface CheckoutPayload {
  tipo_despacho: CheckoutModalidad;
  metodo_pago: CheckoutMetodoPago;
  sucursal_id?: string;
  direccion_entrega?: string;
  direccion_entrega_id?: string;
  costo_envio: number;
  puntos_canjeados?: number;
  descuento_puntos?: number;
  notas?: string;
  datos_fiscales?: DatosFiscales;
  transaccion_id?: string;
}

// -----------------------------------------------------------------------------
// HISTORIA US-16: PROCESAMIENTO DE PAGO Y PASARELA DIGITAL (RIO-PAG-01)
// -----------------------------------------------------------------------------
export interface DatosTarjeta {
  numero_tarjeta: string;
  nombre_titular: string;
  fecha_vencimiento: string;
  cvv: string;
}

export interface IniciarPagoPayload {
  monto: number;
  moneda?: string;
  metodo_pago: CheckoutMetodoPago;
  cliente_id?: string;
  reserva_id?: string;
  orden_id?: string;
  descripcion?: string;
  datos_tarjeta?: DatosTarjeta;
}

export interface IniciarPagoResponse {
  transaccion_id: string;
  token_pago: string;
  estado: 'pendiente' | 'aprobado' | 'rechazado';
  metodo_pago: CheckoutMetodoPago;
  monto: number;
  moneda: string;
  codigo_autorizacion?: string;
  qr_payload?: string;
  redirect_url?: string;
  expira_en_segundos: number;
  mensaje: string;
  created_at: string;
}

export interface TransaccionPagoResponse {
  transaccion_id: string;
  token_pago?: string;
  estado: 'pendiente' | 'aprobado' | 'rechazado';
  metodo_pago: CheckoutMetodoPago;
  monto: number;
  moneda: string;
  codigo_autorizacion?: string;
  orden_id?: string;
  reserva_id?: string;
  motivo_rechazo?: string;
  created_at: string;
  updated_at: string;
}


// -----------------------------------------------------------------------------
// BÚSQUEDA FACETADA Y SUGERENCIAS (RF-06 / US-06)
// -----------------------------------------------------------------------------
export interface FacetItem {
  id: string;
  etiqueta: string;
  total: number;
  seleccionado: boolean;
}

export interface RangoPrecioFacet {
  min: number;
  max: number;
}

export interface FacetasCatalogo {
  categorias: FacetItem[];
  marcas: FacetItem[];
  precio: RangoPrecioFacet;
  en_stock: number;
  total_general: number;
}

export interface BusquedaFacetadaResponse {
  items: Producto[];
  total_coincidencias: number;
  pagina: number;
  limite: number;
  facetas: FacetasCatalogo;
}

export interface SugerenciaItem {
  id: string;
  nombre: string;
  sku: string;
  categoria: string;
  marca?: string | null;
  precio: number;
  imagen_url?: string | null;
  stock: number;
}

export interface MarketplaceProduct {
  id: string;
  sku: string;
  nombre: string;
  descripcion?: string;
  categoria: string;
  categoria_id?: string;
  marca?: string;
  precio: number;
  rating: number;
  stock: number;
  badge: string;
  image: string;
  galleryImages: Array<{ id: string; url: string; es_principal: boolean; orden: number }>;
  atributos?: Record<string, any>;
  variantes?: Array<{ id: string; sku: string; nombre_variante: string; atributos: Record<string, any>; precio: number }>;
}

// ============================================================================
// HISTORIA KAN-20 / RF-04: LISTAS DE PRECIOS DIFERENCIADAS Y MONEDA DUAL
// ============================================================================
export type CanalVenta = 'web' | 'pos' | 'b2b';
export type TipoCliente = 'retail' | 'corporativo_b2b';

export interface ListaPrecio {
  id: string;
  nombre: string;
  canal: CanalVenta;
  tipo_cliente: TipoCliente;
  sucursal_id?: string | null;
  sucursal_nombre?: string | null;
  moneda: 'BOB' | 'USD';
  factor_ajuste?: number; // e.g. 0.85 for 15% discount in B2B
  activo: boolean;
  items_count?: number;
  total_items?: number;
  created_at?: string;
}

export interface PrecioResolucion {
  lista_precio_id?: string | null;
  lista_nombre: string;
  variante_id: string;
  precio: number;
  moneda: string;
  canal: string;
  tipo_cliente: string;
  sucursal_id?: string | null;
  fecha_inicio?: string;
  fecha_fin?: string | null;
}

export interface PrecioItem {
  id: string;
  lista_precio_id: string;
  variante_id: string;
  producto_id?: string;
  sku?: string;
  nombre?: string;
  precio: number;
  precio_usd?: number;
  fecha_inicio?: string;
  fecha_fin?: string;
}

// ============================================================================
// HISTORIA US-18 / RF-18: COMBOS Y PAQUETES COMERCIALES
// ============================================================================
export interface ComboItem {
  id?: string;
  combo_id?: string;
  variante_id: string;
  producto_id?: string;
  sku?: string;
  nombre_producto?: string;
  nombre_variante?: string;
  cantidad: number;
  precio_unitario: number;
  precio_subtotal: number;
  stock_disponible: number;
  imagen_url?: string;
}

export interface Combo {
  id: string;
  sku?: string;
  nombre: string;
  descripcion?: string;
  precio_combo: number;
  precio_original: number;
  ahorro_monto: number;
  ahorro_porcentaje: number;
  imagen_url?: string;
  activo: boolean;
  created_at?: string;
  items: ComboItem[];
  stock_disponible: number;
  disponible: boolean;
  item_cuello_botella?: string | null;
}

export interface ComboItemCreatePayload {
  variante_id: string;
  cantidad: number;
}

export interface ComboCreatePayload {
  nombre: string;
  descripcion?: string;
  sku?: string;
  precio_combo: number;
  imagen_url?: string;
  activo?: boolean;
  items: ComboItemCreatePayload[];
}

export interface ComboDisponibilidad {
  combo_id: string;
  nombre: string;
  stock_disponible: number;
  disponible: boolean;
  item_cuello_botella?: string | null;
  desglose_items: ComboItem[];
}

// ============================================================================
// HISTORIA RF-09: APERTURA, CONTROL Y CIERRE DE CAJA POR TURNO (POS)
// ============================================================================
export interface CajaTurno {
  id: string;
  sucursal_id: string;
  cajero_id: string;
  fondo_inicial: number;
  total_efectivo: number;
  total_tarjeta: number;
  total_qr: number;
  estado: 'abierta' | 'en_arqueo' | 'cerrada';
  diferencia?: number | null;
  observaciones?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
}

export interface MovimientoCaja {
  id: string;
  caja_turno_id: string;
  tipo: 'ingreso' | 'egreso';
  monto: number;
  descripcion: string;
  created_at?: string | null;
}

export interface ArqueoCajaResultado {
  caja_turno_id: string;
  cajero_id: string;
  sucursal_id: string;
  fondo_inicial: number;
  total_efectivo: number;
  total_tarjeta: number;
  total_qr: number;
  total_ingresos_manuales: number;
  total_egresos_manuales: number;
  total_esperado: number;
  monto_cierre_real: number;
  diferencia: number;
  estado: string;
  observaciones?: string | null;
  closed_at?: string | null;
}

export interface AbrirCajaPayload {
  sucursal_id: string;
  cajero_id?: string;
  fondo_inicial: number;
}

export interface MovimientoCajaPayload {
  tipo: 'ingreso' | 'egreso';
  monto: number;
  descripcion: string;
}

export interface CerrarCajaPayload {
  monto_cierre_real: number;
  observaciones?: string;
}


export interface ResolucionPrecioResponse {
  sku: string;
  nombre: string;
  precio_bob: number;
  precio_usd: number;
  tipo_cambio: number;
  lista_aplicada: {
    id: string;
    nombre: string;
    canal: CanalVenta;
    tipo_cliente: TipoCliente;
  };
  regla_aplicada: string;
  descuento_aplicado?: number;
}

// ============================================================================
// HISTORIA KAN-29: CONSULTA DE STOCK MULTI-SUCURSAL (F3)
// ============================================================================
export interface SucursalStockInfo {
  sucursal_id: string;
  sucursal_nombre: string;
  ciudad: string;
  direccion: string;
  stock: number;
  estado: 'disponible' | 'bajo' | 'agotado';
  ultima_actualizacion: string;
}

export interface ProductoStockMultiSucursal {
  sku: string;
  nombre: string;
  stock_total: number;
  sucursales: SucursalStockInfo[];
}

// ============================================================================
// HISTORIA KAN-10 / KAN-27: RETIRO EN SUCURSAL CLICK & COLLECT (RF-11)
// SUBTAREAS: KAN-107, KAN-108, KAN-324, KAN-325, KAN-326, KAN-327
// ============================================================================
export interface ItemPedidoRetiro {
  id?: string;
  sku: string;
  nombre_producto: string;
  cantidad: number;
  precio_unitario: number;
  total_linea: number;
}

export interface AuditoriaDespacho {
  fecha_entrega: string;
  cajero_id: string;
  cajero_nombre: string;
  sucursal_id: string;
  sucursal_nombre: string;
  receptor_nombre: string;
  receptor_documento: string;
  receptor_tipo: 'titular' | 'tercero_autorizado';
  receptor_telefono?: string;
  observaciones?: string;
  numero_acta?: string;
}

export interface PedidoClickAndCollect {
  orden_id: string;
  codigo_orden: string;
  codigo_retiro: string;
  codigo_qr?: string;
  estado: 'pendiente' | 'confirmada' | 'en_preparacion' | 'despachada' | 'pendiente_retiro' | 'entregada' | 'cancelada';
  es_entregable: boolean;
  motivo_rechazo?: string;
  sucursal_id?: string | null;
  sucursal_nombre: string;
  fecha_compra: string;
  cliente_nombre: string;
  cliente_documento: string;
  cliente_telefono?: string;
  cliente_email?: string;
  subtotal: number;
  descuento: number;
  total: number;
  metodo_pago?: string;
  cuf_factura?: string;
  numero_factura?: number;
  items: ItemPedidoRetiro[];
  despacho?: AuditoriaDespacho | null;
}

export interface ConfirmarEntregaPayload {
  orden_id: string;
  codigo_retiro: string;
  receptor_nombre: string;
  receptor_documento: string;
  receptor_tipo: 'titular' | 'tercero_autorizado';
  receptor_telefono?: string;
  observaciones?: string;
  cajero_id?: string;
  cajero_nombre?: string;
  sucursal_id?: string;
  sucursal_nombre?: string;
}

// ============================================================================
// HISTORIA KAN-11 / KAN-35: RECOMENDACIONES (RF-19)
// SUBTAREAS: KAN-139, KAN-140, KAN-141, KAN-142
// ============================================================================
export interface ProductoBaseRecomendacion {
  id: string;
  sku: string;
  nombre: string;
  categoria: string;
  precio: number;
  imagen?: string | null;
  variante_id?: string | null;
}

export interface RecomendacionItem {
  id: string;
  sku: string;
  nombre: string;
  categoria: string;
  precio: number;
  imagen?: string | null;
  tipo_recomendacion: 'cross_sell' | 'up_sell' | 'base';
  motivo: string;
  score_afinidad: number;
  badge?: string | null;
  variante_id?: string | null;
}

export interface BundleFrecuente {
  productos: RecomendacionItem[];
  precio_total_individual: number;
  precio_combo_sugerido: number;
  ahorro_monto: number;
  ahorro_porcentaje: number;
  mensaje_ahorro: string;
}

export interface RecomendacionesResponse {
  producto_base: ProductoBaseRecomendacion;
  recomendaciones: RecomendacionItem[];
  frecuentemente_comprados_juntos?: BundleFrecuente | null;
  total_recomendaciones: number;
}

// ============================================================================
// HISTORIA KAN-11 / KAN-31: SELECCIÓN DE ENTREGA (RF-15 / US-15)
// SUBTAREAS:
// - [BE] Algoritmo de cálculo de costo de flete según zona y dirección de entrega
// - [BE] Endpoint de consulta de sucursales habilitadas con stock para retiro
// - [FE] Paso 1 del Checkout con selector interactivo Domicilio vs Retiro
// - [FE] Selector de sucursal con visualización de mapa o lista de tiendas
// ============================================================================

export type TipoDespacho = 'domicilio' | 'retiro_sucursal';

export interface CalculoFleteRequest {
  ciudad: string;
  zona: string;
  direccion?: string;
  direccion_id?: string;
  subtotal_productos: number;
  peso_estimado_kg?: number;
  tipo_envio?: 'estandar' | 'express_mismo_dia';
}

export interface DesgloseFlete {
  tarifa_base_zona: number;
  recargo_peso: number;
  recargo_express: number;
  descuento_promocion: number;
  distancia_estimada_km: number;
  subtotal_evaluado: number;
}

export interface CalculoFleteResponse {
  ciudad: string;
  zona: string;
  costo_flete: number;
  costo_original: number;
  flete_gratis: boolean;
  umbral_flete_gratis: number;
  tiempo_estimado: string;
  tipo_envio: string;
  mensaje: string;
  desglose: DesgloseFlete;
}

export interface CoordenadasSucursal {
  lat: number;
  lng: number;
}

export interface SucursalRetiro {
  id: string;
  nombre: string;
  ciudad: string;
  departamento: string;
  direccion: string;
  telefono: string;
  horario_atencion: string;
  coordenadas: CoordenadasSucursal;
  stock_disponible: boolean;
  tiempo_preparacion: string;
  costo_retiro: number;
  referencia?: string;
  es_habilitada: boolean;
}

export interface SeleccionEntregaData {
  tipo_despacho: TipoDespacho;
  // Para Domicilio:
  ciudad: string;
  zona: string;
  direccion_exacta: string;
  referencia_entrega: string;
  tipo_envio: 'estandar' | 'express_mismo_dia';
  costo_flete: number;
  flete_gratis: boolean;
  tiempo_estimado: string;
  // Para Retiro en Sucursal:
  sucursal_seleccionada: SucursalRetiro | null;
}


// ---------------------------------------------------------------------------
// Pago dividido en caja (varios métodos de pago en una misma venta)
// ---------------------------------------------------------------------------
export type MetodoPagoPos = 'efectivo' | 'tarjeta' | 'qr';

export interface TramoPagoPos {
  id: string;
  metodo: MetodoPagoPos;
  monto: number | null;
  /** Tarjeta: últimos 4 dígitos / voucher. */
  referencia: string;
  /** Efectivo: billete entregado por el cliente (para calcular el cambio). */
  recibido: number | null;
}

export interface PagoProcesadoPos {
  metodo: MetodoPagoPos | string;
  monto: number;
  transaccion_id?: string | null;
  referencia?: string | null;
  cambio?: number;
}
