from typing import List, Optional, Any, Dict, Literal
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field
from backend.shared.pagos_divididos import PagoParcial, PagoProcesado

class ItemOrdenCreate(BaseModel):
    variante_id: UUID
    sku: str
    nombre_producto: str
    cantidad: int = Field(..., gt=0)
    precio_unitario: Decimal = Field(..., ge=0)

class ItemOrdenResponse(ItemOrdenCreate):
    id: UUID
    total_linea: Decimal

class DatosFiscalesPayload(BaseModel):
    modalidad: Optional[str] = "con_factura"
    tipo_documento: Optional[str] = "NIT"
    nit_ci: Optional[str] = "0"
    razon_social: Optional[str] = "CONSUMIDOR FINAL"
    email_facturacion: Optional[str] = None
    guardar_perfil: Optional[bool] = True


class PubSubPruebaRequest(BaseModel):
    responsable: str = Field(default="Equipo Grupo E", min_length=2, max_length=120)
    detalle: Optional[str] = Field(default=None, max_length=500)


class PubSubItemRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    cantidad: int = Field(..., gt=0, le=10000)
    nombre: Optional[str] = Field(default=None, max_length=255)


class PubSubMovimientoRequest(BaseModel):
    orden_id: str = Field(..., min_length=1, max_length=100)
    items: List[PubSubItemRequest] = Field(..., min_length=1, max_length=100)
    origen: Literal["marketplace", "pos"] = "marketplace"
    sucursal_id: Optional[str] = Field(default=None, max_length=100)
    reserva_id: Optional[str] = Field(default=None, max_length=100)
    motivo: Optional[str] = Field(default=None, min_length=3, max_length=240)

class OrdenCreate(BaseModel):
    cliente_id: Any
    sucursal_id: Optional[Any] = None
    canal: str = "web"
    tipo_despacho: str = "domicilio" # domicilio | retiro_sucursal
    direccion_entrega_id: Optional[Any] = None
    subtotal: Decimal
    descuento: Decimal = Decimal("0.0")
    puntos_canjeados: int = Field(default=0, ge=0)
    costo_envio: Decimal = Decimal("0.0")
    total: Decimal
    metodo_pago: str = "tarjeta"  # método único (compatibilidad); se ignora si se envía `pagos`
    pagos: Optional[List[PagoParcial]] = None  # pago dividido: varias transacciones que suman el total
    items: List[ItemOrdenCreate]
    reserva_id: Optional[str] = None
    datos_fiscales: Optional[DatosFiscalesPayload] = None
    transaccion_id: Optional[str] = None

class OrdenResponse(BaseModel):
    id: UUID
    codigo_orden: str
    cliente_id: Any
    canal: str
    tipo_despacho: str
    subtotal: Decimal
    descuento: Decimal = Decimal("0.0")
    costo_envio: Decimal = Decimal("0.0")
    total: Decimal
    estado: str # pendiente, confirmada, en_preparacion, despachada, entregada, cancelada
    tracking_number: Optional[str] = None
    reserva_id: Optional[str] = None
    cuf_factura: Optional[str] = None
    numero_factura: Optional[int] = None
    factura: Optional[dict] = None
    created_at: datetime
    items: List[ItemOrdenResponse] = []
    pagos: List[PagoProcesado] = []  # transacciones de pago aprobadas (más de una si se dividió el pago)
    reversion: Optional[Dict[str, Any]] = None  # resultado de la saga de reversión (RF-33), si hubo cancelación
    motivo_cancelacion: Optional[str] = None
    historial_estados: List[Dict[str, Any]] = []  # RF-28: auditoría de transiciones (usuario y fecha)

class HistorialOrdenesResponse(BaseModel):
    items: List[OrdenResponse]
    total: int
    pagina: int
    limite: int
    total_paginas: int

class TransicionEstadoRequest(BaseModel):
    nuevo_estado: str

class ResenaCreate(BaseModel):
    producto_id: UUID
    orden_id: UUID
    calificacion: int = Field(..., ge=1, le=5)
    comentario: str = Field(..., min_length=8, max_length=1500)

class ResenaElegibleResponse(BaseModel):
    orden_id: UUID
    codigo_orden: str
    entregada_el: datetime

class ResenaResponse(BaseModel):
    id: UUID
    producto_id: UUID
    producto_nombre: Optional[str] = None
    producto_sku: Optional[str] = None
    cliente_id: UUID
    orden_id: Optional[UUID] = None
    codigo_orden: Optional[str] = None
    nombre_cliente: Optional[str] = None
    calificacion: int
    comentario: str
    estado_moderacion: Literal["pendiente", "aprobada", "rechazada"]
    motivo_rechazo: Optional[str] = None
    created_at: datetime

class ModeracionResenaRequest(BaseModel):
    accion: Literal["aprobar", "rechazar"]
    motivo: Optional[str] = Field(None, max_length=500)

class CotizacionB2BCreate(BaseModel):
    cliente_id: UUID
    vigencia_hasta: date
    items: List[ItemOrdenCreate]
    descuento_porcentaje: Decimal = Decimal("0.0")

class CotizacionB2BResponse(BaseModel):
    id: UUID
    codigo_orden: str = Field(alias="codigo_cotizacion", default="")
    cliente_id: UUID
    total: Decimal
    vigencia_hasta: date
    estado: str # borrador, pendiente_aprobacion, aprobada, rechazada, convertida
    items: List[ItemOrdenCreate] = []

# ==============================================================================
# RF-15 / US-15 / KAN-31: SELECCIÓN DE ENTREGA (DOMICILIO CON FLETE VS RETIRO)
# SUBTAREAS:
# - Algoritmo de cálculo de costo de flete según zona y dirección de entrega
# - Endpoint de consulta de sucursales habilitadas con stock para retiro
# ==============================================================================

class CalculoFleteRequest(BaseModel):
    ciudad: str
    zona: str
    direccion: Optional[str] = None
    direccion_id: Optional[str] = None
    subtotal_productos: Decimal = Decimal("0.0")
    peso_estimado_kg: Decimal = Decimal("1.0")
    tipo_envio: str = "estandar" # 'estandar' | 'express_mismo_dia'

class CalculoFleteResponse(BaseModel):
    ciudad: str
    zona: str
    costo_flete: Decimal
    costo_original: Decimal
    flete_gratis: bool
    umbral_flete_gratis: Decimal
    tiempo_estimado: str
    tipo_envio: str
    mensaje: str
    desglose: Dict[str, Any]

class CoordenadasSucursal(BaseModel):
    lat: float
    lng: float

class SucursalRetiroResponse(BaseModel):
    id: str
    nombre: str
    ciudad: str
    departamento: str
    direccion: str
    telefono: str
    horario_atencion: str
    coordenadas: CoordenadasSucursal
    stock_disponible: bool
    tiempo_preparacion: str
    costo_retiro: Decimal = Decimal("0.0")
    referencia: Optional[str] = None
    es_habilitada: bool = True

