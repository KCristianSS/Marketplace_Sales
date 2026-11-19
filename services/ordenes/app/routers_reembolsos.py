"""KAN-55 — Endpoints de reembolsos (solo administrador)."""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

try:
    from app import reembolsos as svc
    from app.pagos_repo import repo
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app import reembolsos as svc
    from backend.services.ordenes.app.pagos_repo import repo

from backend.shared.security import get_current_user, require_jwt_claims

router = APIRouter(prefix="/api/v1/reembolsos", tags=["Reembolsos (KAN-55)"])


class SolicitarReembolsoRequest(BaseModel):
    pago_id: Optional[UUID] = Field(default=None, description="Reembolsa un tramo/pago concreto")
    orden_id: Optional[UUID] = Field(default=None, description="Reembolsa sobre una orden: se reparte por tramo")
    monto: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2, description="Omitir = reembolso total del saldo")
    motivo: str = Field(..., min_length=3, max_length=255)
    simular_fallo: bool = Field(default=False, description="Solo QA/demo: la pasarela simulada rechaza el reembolso")

    @model_validator(mode="after")
    def _uno_solo(self):
        if bool(self.pago_id) == bool(self.orden_id):
            raise ValueError("Indica pago_id u orden_id (exactamente uno).")
        return self


class ReintentarRequest(BaseModel):
    simular_fallo: bool = False


class ReembolsoResponse(BaseModel):
    id: UUID
    pago_id: UUID
    orden_id: UUID
    codigo_orden: Optional[str] = None
    metodo: str
    monto: Decimal
    motivo: str
    estado: str
    intento: int = 1
    error: Optional[str] = None
    referencia_externa: Optional[str] = None
    nota_credito: Optional[str] = None
    numero_comprobante: Optional[str] = None
    comprobante: Optional[Dict[str, Any]] = None
    contabilidad: Optional[Dict[str, Any]] = None
    solicitado_por: Optional[str] = None
    saldo_reembolsable_pago: Decimal = Decimal("0.00")
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    completed_at: Optional[Any] = None


class ReembolsosCreadosResponse(BaseModel):
    reembolsos: List[ReembolsoResponse]
    monto_total: Decimal
    completados: int
    fallidos: int


class ListaReembolsosResponse(BaseModel):
    items: List[ReembolsoResponse]
    total: int
    pagina: int
    limite: int


def _out(r: Dict[str, Any]) -> ReembolsoResponse:
    pago = repo.get_pago(str(r["pago_id"]))
    orden = repo.get_orden(str(r["orden_id"]))
    return ReembolsoResponse(
        **{**r, "codigo_orden": orden["codigo_orden"] if orden else None,
           "saldo_reembolsable_pago": svc.saldo_reembolsable(pago) if pago else Decimal("0.00")}
    )


@router.post("", response_model=ReembolsosCreadosResponse, status_code=status.HTTP_201_CREATED, summary="Solicitar un reembolso total o parcial")
@router.post("/", response_model=ReembolsosCreadosResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@require_jwt_claims("sub", allowed_roles={"administrador"})
async def solicitar_reembolso(payload: SolicitarReembolsoRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    creados = await svc.solicitar(
        str(payload.pago_id) if payload.pago_id else None, str(payload.orden_id) if payload.orden_id else None,
        payload.monto, payload.motivo, current_user, payload.simular_fallo,
    )
    return ReembolsosCreadosResponse(
        reembolsos=[_out(r) for r in creados],
        monto_total=sum((r["monto"] for r in creados), Decimal("0.00")),
        completados=sum(1 for r in creados if r["estado"] == "completado"),
        fallidos=sum(1 for r in creados if r["estado"] == "fallido"),
    )


@router.post("/{reembolso_id}/reintentar", response_model=ReembolsoResponse, summary="Reintentar un reembolso fallido")
@require_jwt_claims("sub", allowed_roles={"administrador"})
async def reintentar_reembolso(reembolso_id: UUID, payload: Optional[ReintentarRequest] = None,
                               current_user: Dict[str, Any] = Depends(get_current_user)):
    r = await svc.reintentar(str(reembolso_id), current_user, bool(payload and payload.simular_fallo))
    return _out(r)


@router.get("", response_model=ListaReembolsosResponse, summary="Listar reembolsos")
@router.get("/", response_model=ListaReembolsosResponse, include_in_schema=False)
@require_jwt_claims("sub", allowed_roles={"administrador"})
async def listar_reembolsos(
    estado: Optional[str] = Query(default=None, pattern="^(solicitado|procesando|completado|fallido|simulado)$"),
    orden_id: Optional[UUID] = None,
    pago_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    filas, total = repo.listar_reembolsos(estado, str(orden_id) if orden_id else None, str(pago_id) if pago_id else None, limit, (page - 1) * limit)
    return ListaReembolsosResponse(items=[_out(r) for r in filas], total=total, pagina=page, limite=limit)


@router.get("/{reembolso_id}", response_model=ReembolsoResponse, summary="Detalle de un reembolso")
@require_jwt_claims("sub", allowed_roles={"administrador"})
async def obtener_reembolso(reembolso_id: UUID, current_user: Dict[str, Any] = Depends(get_current_user)):
    r = repo.get_reembolso(str(reembolso_id))
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado.")
    return _out(r)
