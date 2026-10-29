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

export interface WishlistItem {
  id: string;
  cliente_id: string;
  variante_id: string;
  created_at: string;
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
  codigo_qr: string;
  leyenda_fiscal: string;
  items: Array<{
    sku: string;
    nombre: string;
    cantidad: number;
    precio_unitario: number;
    subtotal: number;
  }>;
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
  sucursal_id?: string;
  sucursal_nombre?: string;
  moneda: 'BOB' | 'USD';
  factor_ajuste?: number; // e.g. 0.85 for 15% discount in B2B
  activo: boolean;
  items_count?: number;
  created_at?: string;
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
  id: string;
  codigo_orden: string;
  codigo_retiro: string;
  codigo_qr?: string;
  canal: string;
  tipo_despacho: string;
  estado: 'pendiente' | 'confirmada' | 'en_preparacion' | 'despachada' | 'pendiente_retiro' | 'entregada' | 'cancelada';
  es_entregable: boolean;
  motivo_rechazo?: string;
  sucursal_id: string;
  sucursal_nombre: string;
  created_at: string;
  cliente_id?: string;
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
