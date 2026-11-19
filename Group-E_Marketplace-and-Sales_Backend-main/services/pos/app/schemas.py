from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from decimal import Decimal
from backend.shared.pagos_divididos import PagoParcial, PagoProcesado
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Apertura / Cierre de caja
# ---------------------------------------------------------------------------

class AbrirCajaRequest(BaseModel):
    sucursal_id: UUID
    cajero_id: Optional[UUID] = None
    fondo_inicial: Decimal = Field(..., ge=0)


class CerrarCajaRequest(BaseModel):
    monto_cierre_real: Decimal = Field(..., ge=0, description="Monto contado físicamente por el cajero")
    observaciones: Optional[str] = Field(None, max_length=500, description="Notas del cajero al cierre")


class CajaResponse(BaseModel):
    id: UUID
    sucursal_id: UUID
    cajero_id: UUID
    fondo_inicial: Decimal
    total_efectivo: Decimal = Decimal("0.00")
    total_tarjeta: Decimal = Decimal("0.00")
    total_qr: Decimal = Decimal("0.00")
    estado: str
    diferencia: Optional[Decimal] = None
    observaciones: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class ArqueoCajaResponse(BaseModel):
    """Resumen detallado del arqueo de caja al cierre."""
    caja_turno_id: UUID
    cajero_id: UUID
    sucursal_id: UUID
    fondo_inicial: Decimal
    total_efectivo: Decimal
    total_tarjeta: Decimal
    total_qr: Decimal
    total_ingresos_manuales: Decimal = Decimal("0.00")
    total_egresos_manuales: Decimal = Decimal("0.00")
    total_esperado: Decimal = Field(
        ..., description="fondo_inicial + total_efectivo + ingresos - egresos"
    )
    monto_cierre_real: Decimal
    diferencia: Decimal = Field(
        ..., description="monto_cierre_real - total_esperado (positivo = sobrante, negativo = faltante)"
    )
    estado: str
    observaciones: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Movimientos manuales de caja (ingreso / egreso)
# ---------------------------------------------------------------------------

class MovimientoCajaRequest(BaseModel):
    tipo: str = Field(..., pattern="^(ingreso|egreso)$", description="'ingreso' o 'egreso'")
    monto: Decimal = Field(..., gt=0)
    descripcion: str = Field(..., min_length=1, max_length=255)


class MovimientoCajaResponse(BaseModel):
    id: UUID
    caja_turno_id: UUID
    tipo: str
    monto: Decimal
    descripcion: str
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Venta POS & Descuentos Manuales con Autorización de Supervisor (KAN-345)
# ---------------------------------------------------------------------------

class AutorizarDescuentoManualRequest(BaseModel):
    supervisor_username: str = Field(..., min_length=2, max_length=100)
    pin: str = Field(..., min_length=4, max_length=10)
    tipo: Literal["item", "total"] = "item"
    porcentaje: Decimal = Field(..., gt=0, description="Porcentaje de descuento (máximo 30% por política)")
    monto_base: Decimal = Field(..., ge=0, description="Monto base sobre el que aplica el descuento")
    motivo: str = Field(..., min_length=3, max_length=500, description="Motivo obligatorio del descuento (ej: empaque dañado)")
    item_sku: Optional[str] = None
    cajero_id: Optional[UUID] = None
    cajero_nombre: Optional[str] = None
    sucursal_id: Optional[UUID] = None


class AutorizacionDescuentoResponse(BaseModel):
    autorizacion_id: str
    autorizado: bool = True
    supervisor_id: UUID
    supervisor_nombre: str
    tipo: str
    item_sku: Optional[str] = None
    porcentaje: Decimal
    monto_base: Decimal
    monto_descuento: Decimal
    motivo: str
    expires_at: datetime
    mensaje: str


class ItemVentaPOS(BaseModel):
    variante_id: UUID
    sku: str
    nombre: str
    cantidad: int = Field(..., gt=0)
    precio_unitario: Decimal = Field(..., ge=0)
    descuento_unitario: Decimal = Decimal("0.00")
    autorizacion_descuento_id: Optional[str] = None


class ItemTicketPOS(BaseModel):
    sku: str
    nombre: str
    cantidad: int
    precio_unitario: Decimal
    descuento_unitario: Decimal = Decimal("0.00")
    autorizacion_descuento_id: Optional[str] = None
    total_linea: Decimal


class VentaPOSRequest(BaseModel):
    caja_id: UUID
    sucursal_id: UUID
    cliente_nit_ci: Optional[str] = "0"
    cliente_razon_social: Optional[str] = "Sin Nombre"
    modalidad: Literal["con_factura", "sin_factura"] = "con_factura"
    tipo_documento: Literal["NIT", "CI", "CEX", "PAS"] = "NIT"
    email_facturacion: Optional[str] = Field(None, max_length=254)
    guardar_perfil: bool = True
    items: List[ItemVentaPOS]
    metodo_pago: str = "efectivo" # efectivo | tarjeta | qr (compatibilidad; se ignora si se envía `pagos`)
    pagos: Optional[List[PagoParcial]] = None # pago dividido: varias transacciones que suman el total
    autorizacion_descuento_total_id: Optional[str] = None # Descuento manual sobre el total del ticket autorizado
    descuento_total_motivo: Optional[str] = None

class VentaPOSResponse(BaseModel):
    orden_id: UUID
    codigo_orden: str
    subtotal_neto: Decimal
    monto_iva: Decimal
    total: Decimal
    descuento_total: Decimal = Decimal("0.00")
    descuentos_manuales: List[Dict[str, Any]] = []
    metodo_pago: str # método único o "mixto" cuando se dividió el pago
    desglose_pagos: List[PagoProcesado] = []
    cambio_total: Decimal = Decimal("0.00")
    numero_factura: Optional[int] = None
    cuf: Optional[str] = None
    cufd: Optional[str] = None
    factura_estado: Literal["autorizada", "pendiente"]
    factura_mensaje: Optional[str] = None
    qr_url: Optional[str] = None
    qr_code: Optional[str] = None
    items: List[ItemTicketPOS] = []
    ticket_impresion: str
    estado_venta: Literal["completada", "anulando", "anulada", "anulacion_pendiente"] = "completada"
    motivo_anulacion: Optional[str] = None
    autorizada_por: Optional[str] = None
    nota_credito: Optional[str] = None


class VentaPOSReciente(BaseModel):
    orden_id: UUID
    codigo_orden: str
    total: Decimal
    numero_factura: Optional[int] = None
    created_at: Optional[datetime] = None
    estado_venta: Literal["completada", "anulando", "anulada", "anulacion_pendiente"] = "completada"
    motivo_anulacion: Optional[str] = None


class AnularVentaPOSRequest(BaseModel):
    caja_id: UUID
    motivo: str = Field(..., min_length=5, max_length=240)
    supervisor_username: str = Field(..., min_length=2, max_length=100)
    pin: str = Field(..., min_length=4, max_length=8)


class AnularVentaPOSResponse(BaseModel):
    success: bool
    orden_id: UUID
    codigo_orden: str
    estado_venta: Literal["anulada", "anulacion_pendiente"]
    motivo: str
    autorizada_por: str
    notas_credito: List[str] = Field(default_factory=list)
    reversion: dict[str, object] = Field(default_factory=dict)
    mensaje: str


class TicketReimpresionResponse(VentaPOSResponse):
    duplicado: bool = True


# ---------------------------------------------------------------------------
# Ventas suspendidas
# ---------------------------------------------------------------------------

class VentaSuspendida(BaseModel):
    id: str
    cliente_referencia: str
    items: List[ItemVentaPOS]
    subtotal: Decimal

# ============================================================================
# HISTORIA KAN-10 / KAN-27: RETIRO EN SUCURSAL CLICK & COLLECT (RF-11)
# SUBTAREAS KAN-324 Y KAN-325
# ============================================================================
class ValidarRetiroRequest(BaseModel):
    codigo: str = Field(..., description="Código seguro de retiro (RET-XXXX), código de orden (ORD-XXXX) o payload de código QR")
    sucursal_id: Optional[str] = None

class DetalleItemRetiro(BaseModel):
    sku: str
    nombre_producto: str
    cantidad: int
    precio_unitario: Decimal
    total_linea: Decimal

class AuditoriaDespachoInfo(BaseModel):
    fecha_entrega: str
    cajero_id: Optional[str] = None
    cajero_nombre: str
    sucursal_id: Optional[str] = None
    sucursal_nombre: str
    receptor_nombre: str
    receptor_documento: str
    receptor_tipo: str # titular | tercero_autorizado
    receptor_telefono: Optional[str] = None
    observaciones: Optional[str] = None
    numero_acta: Optional[str] = None

class PedidoRetiroResponse(BaseModel):
    orden_id: UUID
    codigo_orden: str
    codigo_retiro: str
    codigo_qr: Optional[str] = None
    estado: str
    es_entregable: bool
    motivo_rechazo: Optional[str] = None
    sucursal_id: Optional[str] = None
    sucursal_nombre: str
    fecha_compra: str
    cliente_nombre: str
    cliente_documento: str
    cliente_telefono: Optional[str] = None
    cliente_email: Optional[str] = None
    subtotal: Decimal
    descuento: Decimal = Decimal("0.0")
    total: Decimal
    metodo_pago: Optional[str] = "aprobado"
    cuf_factura: Optional[str] = None
    numero_factura: Optional[int] = None
    items: List[DetalleItemRetiro]
    despacho: Optional[AuditoriaDespachoInfo] = None

class ConfirmarEntregaRequest(BaseModel):
    orden_id: UUID
    codigo_retiro: str
    receptor_nombre: str = Field(..., min_length=2)
    receptor_documento: str = Field(..., min_length=4)
    receptor_tipo: str = "titular" # titular | tercero_autorizado
    receptor_telefono: Optional[str] = None
    observaciones: Optional[str] = None
    cajero_id: Optional[str] = None
    cajero_nombre: Optional[str] = "Cajero de Turno"
    sucursal_id: Optional[str] = None
    sucursal_nombre: Optional[str] = "Sucursal Central"

class ConfirmarEntregaResponse(BaseModel):
    success: bool
    orden_id: UUID
    codigo_orden: str
    codigo_retiro: str
    nuevo_estado: str
    fecha_entrega: str
    receptor_nombre: str
    receptor_documento: str
    receptor_tipo: str
    cajero_nombre: str
    comprobante_entrega: dict
    mensaje: str


# ============================================================================
# KAN-342: ENTRADAS EXTRAORDINARIAS Y RETIROS PARCIALES A BÓVEDA
# ============================================================================
class MovimientoEfectivoRequest(BaseModel):
    tipo: Literal["entrada", "retiro"]
    monto: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    motivo: str = Field(..., min_length=3, max_length=255, description="Obligatorio")
    supervisor_token: Optional[str] = Field(
        default=None,
        description="JWT de un supervisor (rol administrador/supervisor) que confirma retiros sobre el límite",
    )


class ComprobanteMovimiento(BaseModel):
    numero: str
    tipo: str
    monto: Decimal
    motivo: str
    caja_turno_id: UUID
    sucursal_id: Optional[str] = None
    cajero_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    supervisor_email: Optional[str] = None
    fecha: str


class MovimientoEfectivoResponse(BaseModel):
    id: UUID
    caja_turno_id: UUID
    tipo: str
    monto: Decimal
    motivo: str
    requiere_supervisor: bool = False
    supervisor_id: Optional[str] = None
    numero_comprobante: str
    comprobante: Optional[ComprobanteMovimiento] = None
    created_at: Optional[datetime] = None


class MovimientosNetosResponse(BaseModel):
    caja_turno_id: UUID
    entradas: Decimal
    retiros: Decimal
    neto: Decimal
    limite_seguridad: Decimal


# ============================================================================
# KAN-341: ARQUEO CIEGO
# ============================================================================
class DenominacionDeclarada(BaseModel):
    denominacion: Decimal = Field(..., description="Valor facial en Bs. (200, 100, 50, 20, 10, 5, 2, 1, 0.50, 0.20, 0.10)")
    cantidad: int = Field(..., ge=0, le=100000)


class ArqueoCiegoRequest(BaseModel):
    desglose: List[DenominacionDeclarada] = Field(..., min_length=1)
    observaciones: Optional[str] = Field(default=None, max_length=500)


class ArqueoDetalleResponse(BaseModel):
    tipo: Literal["billete", "moneda"]
    denominacion: Decimal
    cantidad: int
    subtotal: Decimal


class ArqueoReporteResponse(BaseModel):
    id: UUID
    numero_reporte: str
    caja_turno_id: UUID
    cajero_id: UUID
    sucursal_id: UUID
    estado_turno: str
    con_diferencia: bool
    resultado: Literal["cuadrado", "sobrante", "faltante"]
    fondo_inicial: Decimal
    ventas_efectivo: Decimal
    entradas_extraordinarias: Decimal = Decimal("0.00")
    retiros_boveda: Decimal = Decimal("0.00")
    total_esperado: Decimal
    total_declarado: Decimal
    diferencia: Decimal
    total_tarjeta: Decimal = Decimal("0.00")
    total_qr: Decimal = Decimal("0.00")
    desglose: List[ArqueoDetalleResponse]
    observaciones: Optional[str] = None
    notificacion_contabilidad: Optional[dict] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
