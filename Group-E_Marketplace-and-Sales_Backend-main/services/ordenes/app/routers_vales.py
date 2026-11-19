"""Compra, consulta y administración de tarjetas de regalo digitales."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.shared import vales
from backend.shared.security import get_current_user, require_role

router = APIRouter(prefix="/api/v1/ordenes/vales", tags=["Tarjetas de regalo"])
admin = require_role(["administrador", "gerente_comercial"])


class ValeResponse(BaseModel):
    id: uuid.UUID
    comprador_id: uuid.UUID
    codigo_ultimos: str
    monto_inicial: Decimal
    saldo: Decimal
    moneda: str
    estado: str
    origen: str
    vence_en: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class EmisionResponse(ValeResponse):
    codigo: str


class CompraRequest(BaseModel):
    transaccion_id: str = Field(min_length=1, max_length=150)


class EmisionRequest(BaseModel):
    solicitud_id: uuid.UUID
    comprador_id: uuid.UUID
    monto: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=2)
    vence_en: Optional[datetime] = None
    motivo: str = Field(min_length=3, max_length=240)

    @field_validator("vence_en")
    @classmethod
    def fecha_futura(cls, value):
        if value is not None and (value.tzinfo is None or value <= datetime.now(timezone.utc)):
            raise ValueError("La fecha de vencimiento debe ser futura e incluir zona horaria.")
        return value

    @field_validator("motivo")
    @classmethod
    def motivo_valido(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Describe el motivo de la operación.")
        return value.strip()


class GestionRequest(BaseModel):
    motivo: str = Field(min_length=3, max_length=240)
    _motivo = field_validator("motivo")(EmisionRequest.motivo_valido.__func__)


class EstadoRequest(GestionRequest):
    estado: Literal["activa", "bloqueada", "anulada"]


class CodigoRequest(BaseModel):
    codigo: str = Field(min_length=10, max_length=80)


class ConsultaResponse(BaseModel):
    saldo: Decimal
    moneda: str
    codigo_ultimos: str
    vence_en: Optional[datetime] = None


class ReservaRequest(CodigoRequest):
    checkout_id: str = Field(min_length=1, max_length=150)
    total: Decimal = Field(gt=0, le=1000000, max_digits=14, decimal_places=2)


class ReservaResponse(BaseModel):
    id: uuid.UUID
    tarjeta_id: uuid.UUID
    cliente_id: uuid.UUID
    checkout_id: str
    monto: Decimal
    total: Decimal
    estado: str
    expira_en: datetime
    orden_id: Optional[uuid.UUID] = None


class MovimientoResponse(BaseModel):
    id: uuid.UUID
    tarjeta_id: uuid.UUID
    reserva_id: Optional[uuid.UUID] = None
    tipo: str
    monto: Decimal
    actor: str
    motivo: str
    created_at: datetime


def _actor(user: dict) -> str:
    return str(user["user_id"])


def _emitir(identificador: str, comprador: str, monto: Decimal, actor: str, **extra):
    codigo = vales.generar_codigo(identificador, "inicial")
    fila = vales.operar("emitir", actor, id=identificador, comprador_id=comprador, monto=str(monto),
                        codigo_hash=vales.hash_codigo(codigo), codigo_version="inicial",
                        codigo_ultimos=codigo[-8:], **extra)
    # Un reintento tras regenerar el código devuelve el código vigente.
    return {**vales.publico(fila), "codigo": vales.generar_codigo(fila["id"], fila["codigo_version"])}


@router.post("/comprar", response_model=EmisionResponse, status_code=201, summary="Emitir un vale tras confirmar su pago")
async def comprar(payload: CompraRequest, user: dict = Depends(get_current_user)):
    from . import routers_pagos
    await routers_pagos.obtener_estado_transaccion(payload.transaccion_id)
    pago = routers_pagos._transacciones_cache[payload.transaccion_id]
    if (pago.get("cliente_id") != _actor(user) or pago.get("proposito") != "vale"
            or pago.get("estado") != "aprobado" or pago.get("moneda") != "BOB"
            or pago.get("orden_id")):
        raise HTTPException(409, "Se requiere un pago aprobado para comprar esta tarjeta de regalo.")
    monto = Decimal(str(pago["monto"]))
    if not 0 < monto <= 10000:
        raise HTTPException(422, "El importe debe estar entre Bs 0.01 y Bs 10000.")
    identificador = str(uuid.uuid5(uuid.NAMESPACE_URL, "maxiconecta:vale:compra:" + payload.transaccion_id))
    return _emitir(identificador, _actor(user), monto, _actor(user), origen="compra",
                   transaccion_compra=payload.transaccion_id, motivo="Compra de saldo prepagado")


@router.get("/", response_model=list[ValeResponse], summary="Listar mis tarjetas de regalo")
async def mis_vales(user: dict = Depends(get_current_user)):
    return vales.operar("listar", _actor(user))["items"]


@router.post("/consultar", response_model=ConsultaResponse, summary="Consultar saldo disponible mediante código")
async def consultar(payload: CodigoRequest, user: dict = Depends(get_current_user)):
    return vales.operar("consultar", _actor(user), codigo_hash=vales.hash_codigo(payload.codigo))


@router.post("/reservas", response_model=ReservaResponse, status_code=201, summary="Reservar saldo para un checkout")
async def reservar(payload: ReservaRequest, user: dict = Depends(get_current_user)):
    return vales.operar("reservar", _actor(user), codigo_hash=vales.hash_codigo(payload.codigo),
                        checkout_id=payload.checkout_id, total=str(payload.total), reserva_id=str(uuid.uuid4()))


@router.delete("/reservas/{id}", response_model=ReservaResponse, summary="Liberar una reserva de saldo propia")
async def liberar(id: uuid.UUID, user: dict = Depends(get_current_user)):
    return vales.operar("liberar", _actor(user), reserva_id=str(id))


@router.get("/admin", response_model=list[ValeResponse], summary="Filtrar tarjetas de regalo emitidas")
async def listar_admin(estado: Optional[Literal["activa", "bloqueada", "anulada"]] = None,
                       comprador_id: Optional[uuid.UUID] = None, ultimos: Optional[str] = Query(None, pattern="^[A-Fa-f0-9]{8}$"),
                       offset: int = Query(0, ge=0), user: dict = Depends(admin)):
    return vales.operar("listar", _actor(user), administracion=True, estado=estado,
                        comprador_id=str(comprador_id) if comprador_id else None,
                        ultimos=ultimos.upper() if ultimos else None, offset=offset)["items"]


@router.post("/admin", response_model=EmisionResponse, status_code=201, summary="Emitir un vale administrativo con motivo auditable")
async def emitir_admin(payload: EmisionRequest, user: dict = Depends(admin)):
    identificador = str(uuid.uuid5(uuid.NAMESPACE_URL, f"maxiconecta:vale:admin:{payload.solicitud_id}"))
    return _emitir(identificador, str(payload.comprador_id), payload.monto, _actor(user), origen="administracion",
                   motivo=payload.motivo, vence_en=payload.vence_en.isoformat() if payload.vence_en else None)


@router.patch("/admin/{id}/estado", response_model=ValeResponse, summary="Bloquear, reactivar o anular una tarjeta")
async def estado_admin(id: uuid.UUID, payload: EstadoRequest, user: dict = Depends(admin)):
    return vales.operar("estado", _actor(user), id=str(id), **payload.model_dump())


@router.post("/admin/{id}/regenerar", response_model=EmisionResponse, summary="Invalidar el código anterior y emitir uno nuevo")
async def regenerar(id: uuid.UUID, payload: GestionRequest, user: dict = Depends(admin)):
    version = str(uuid.uuid4())
    codigo = vales.generar_codigo(str(id), version)
    fila = vales.operar("regenerar", _actor(user), id=str(id), codigo_hash=vales.hash_codigo(codigo),
                        codigo_version=version, codigo_ultimos=codigo[-8:], motivo=payload.motivo)
    return {**vales.publico(fila), "codigo": codigo}


def _propia_o_admin(id: uuid.UUID, user: dict):
    filas = vales.cliente_bd().table("tarjetas_regalo").select("*").eq("id", str(id)).limit(1).execute().data or []
    if not filas or (filas[0]["comprador_id"] != _actor(user) and user["role"] not in {"administrador", "gerente_comercial"}):
        raise HTTPException(404, "Tarjeta no encontrada.")
    return filas[0]


@router.get("/{id}/movimientos", response_model=list[MovimientoResponse], summary="Consultar el historial auditable de una tarjeta")
async def movimientos(id: uuid.UUID, offset: int = Query(0, ge=0), user: dict = Depends(get_current_user)):
    _propia_o_admin(id, user)
    return vales.cliente_bd().table("movimientos_vale").select("*").eq("tarjeta_id", str(id)).order("created_at", desc=True).range(offset, offset + 99).execute().data or []


@router.get("/{id}/codigo", response_model=EmisionResponse, summary="Recuperar el código de una tarjeta propia")
async def ver_codigo(id: uuid.UUID, user: dict = Depends(get_current_user)):
    fila = _propia_o_admin(id, user)
    return {**vales.publico(fila), "codigo": vales.generar_codigo(fila["id"], fila["codigo_version"])}
