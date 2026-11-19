"""KAN-54 — Endpoints de registro y validación de pagos de una orden."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

try:
    from app import pagos_validacion as svc
    from app.pagos_repo import repo, dec
    from app.schemas import ItemOrdenCreate, ItemOrdenResponse, OrdenResponse
    from app.routers import _ORDENES_DB
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app import pagos_validacion as svc
    from backend.services.ordenes.app.pagos_repo import repo, dec
    from backend.services.ordenes.app.schemas import ItemOrdenCreate, ItemOrdenResponse, OrdenResponse
    from backend.services.ordenes.app.routers import _ORDENES_DB

from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_current_user, require_jwt_claims

router = APIRouter(tags=["Validación de pagos de órdenes (KAN-54)"])


class RegistrarPagoRequest(BaseModel):
    orden_id: UUID
    metodo: str = Field(..., description="efectivo | tarjeta | qr | transferencia | pasarela")
    monto: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    referencia: Optional[str] = Field(default=None, max_length=60)
    monto_recibido: Optional[Decimal] = Field(default=None, gt=0, description="Solo efectivo: para calcular el cambio")
    transaccion_id: Optional[str] = Field(default=None, max_length=100, description="Clave de idempotencia opcional")
    reintento_de: Optional[UUID] = Field(default=None, description="ID del pago rechazado que se reintenta")


class PagoOrdenResponse(BaseModel):
    id: UUID
    orden_id: UUID
    transaccion_id: Optional[str] = None
    metodo: str
    monto: Decimal
    estado: str
    intento: int = 1
    referencia: Optional[str] = None
    codigo_autorizacion: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    caja_turno_id: Optional[str] = None
    monto_reembolsado: Decimal = Decimal("0.00")
    saldo_reembolsable: Decimal = Decimal("0.00")
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None


class HistorialPagoItem(BaseModel):
    tipo: str = "pago"
    pago_id: Optional[str] = None
    transaccion_id: Optional[str] = None
    metodo: Optional[str] = None
    monto: Optional[Decimal] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: str
    origen: Optional[str] = None
    motivo: Optional[str] = None
    usuario_id: Optional[str] = None
    created_at: Optional[Any] = None


class PagosOrdenResponse(BaseModel):
    orden_id: UUID
    codigo_orden: str
    estado_orden: str
    total: Decimal
    total_aprobado: Decimal
    total_pendiente: Decimal
    saldo_pendiente: Decimal
    apta_para_preparacion: bool
    pagos: List[PagoOrdenResponse]
    historial: List[HistorialPagoItem]


class RegistrarPagoResponse(BaseModel):
    pago: PagoOrdenResponse
    duplicado: bool = False
    estado_orden: str
    saldo_pendiente: Decimal
    apta_para_preparacion: bool
    cambio: Decimal = Decimal("0.00")
    token_pago: Optional[str] = None
    qr_payload: Optional[str] = None
    redirect_url: Optional[str] = None


def _pago_out(p: Dict[str, Any]) -> PagoOrdenResponse:
    return PagoOrdenResponse(**{**p, "saldo_reembolsable": (p["monto"] - p["monto_reembolsado"]) if p["estado"] in ("aprobado",) else Decimal("0.00")})


def _resumen_out(r: Dict[str, Any]) -> PagosOrdenResponse:
    return PagosOrdenResponse(**{**r, "pagos": [_pago_out(p) for p in r["pagos"]], "historial": [HistorialPagoItem(**h) for h in r["historial"]]})


@router.post("/api/v1/pagos/registrar", response_model=RegistrarPagoResponse, status_code=status.HTTP_201_CREATED,
             summary="Registrar el pago (o un tramo del pago) de una orden")
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador", "gerente_comercial", "cliente"})
async def registrar_pago(payload: RegistrarPagoRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    pago, duplicado, extra = await svc.registrar_pago(
        str(payload.orden_id), payload.metodo, payload.monto, current_user, payload.referencia,
        payload.monto_recibido, payload.transaccion_id, str(payload.reintento_de) if payload.reintento_de else None,
    )
    r = svc.resumen(str(payload.orden_id))
    return RegistrarPagoResponse(
        pago=_pago_out(pago), duplicado=duplicado, estado_orden=r["estado_orden"], saldo_pendiente=r["saldo_pendiente"],
        apta_para_preparacion=r["apta_para_preparacion"], cambio=extra.get("cambio", Decimal("0.00")),
        token_pago=extra.get("token_pago"), qr_payload=extra.get("qr_payload"), redirect_url=extra.get("redirect_url"),
    )


@router.get("/api/v1/ordenes/{orden_id}/pagos", response_model=PagosOrdenResponse,
            summary="Pagos, saldo e historial de pagos de una orden")
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador", "gerente_comercial", "cliente"})
async def pagos_de_orden(orden_id: UUID, current_user: Dict[str, Any] = Depends(get_current_user)):
    orden = svc.cargar_orden_o_404(str(orden_id))
    svc.verificar_acceso_orden(orden, current_user)
    return _resumen_out(svc.resumen(str(orden_id)))


# ------------------------------------------------------------------ orden pendiente de pago
class OrdenPendienteRequest(BaseModel):
    cliente_id: Optional[UUID] = None
    canal: str = Field(default="pos", pattern="^(web|pos|b2b)$")
    items: List[ItemOrdenCreate] = Field(..., min_length=1)
    descuento: Decimal = Field(default=Decimal("0.00"), ge=0)


@router.post("/api/v1/ordenes/pendiente", response_model=OrdenResponse, status_code=status.HTTP_201_CREATED,
             summary="Crear una orden en estado pendiente (a la espera de pagos)")
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador", "cliente"})
async def crear_orden_pendiente(payload: OrdenPendienteRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Orden sin cobrar: queda ``pendiente`` hasta que los pagos aprobados igualen su total (KAN-54)."""
    rol = str(current_user.get("role", "")).lower()
    cliente_id = str(current_user.get("user_id")) if rol == "cliente" else (str(payload.cliente_id) if payload.cliente_id else None)
    if cliente_id is None and payload.canal != "pos":
        raise HTTPException(status_code=422, detail="Debes indicar el cliente de la orden.")
    subtotal = sum((i.precio_unitario * i.cantidad for i in payload.items), Decimal("0.00")).quantize(Decimal("0.01"))
    total = (subtotal - payload.descuento).quantize(Decimal("0.01"))
    if total <= 0:
        raise HTTPException(status_code=422, detail="El total de la orden debe ser mayor a 0.")
    oid = uuid.uuid4()
    items = [ItemOrdenResponse(id=uuid.uuid4(), total_linea=i.precio_unitario * i.cantidad, **i.model_dump()) for i in payload.items]
    orden = OrdenResponse(
        id=oid, codigo_orden=f"ORD-{datetime.now(timezone.utc).year}-{oid.hex[:12].upper()}", cliente_id=cliente_id,
        canal=payload.canal, tipo_despacho="retiro_sucursal" if payload.canal == "pos" else "domicilio",
        subtotal=subtotal, descuento=payload.descuento, total=total, estado="pendiente",
        created_at=datetime.now(timezone.utc), items=items,
    )
    sb = get_supabase_admin_client()
    if sb:
        try:
            sb.rpc("crear_orden_pendiente_atomica", {
                "p_orden": {
                    "id": str(oid), "codigo_orden": orden.codigo_orden, "cliente_id": cliente_id,
                    "canal": payload.canal, "tipo_despacho": orden.tipo_despacho,
                    "subtotal": str(subtotal), "descuento": str(payload.descuento), "total": str(total),
                },
                "p_items": [i.model_dump(mode="json") for i in items],
            }).execute()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo guardar la orden pendiente: {exc}") from exc
    else:
        _ORDENES_DB[str(oid)] = orden
    return orden
