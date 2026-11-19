from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from backend.shared import despachos
from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_current_user

router = APIRouter(prefix="/api/v1/ordenes", tags=["Despachos ERP · Pub/Sub"])


class EventoDespacho(BaseModel):
    id: UUID
    tipo_evento: str
    estado: str
    intentos: int
    message_id: Optional[str] = None
    ultimo_error: Optional[str] = None
    created_at: datetime
    actor: str


class DespachoResponse(BaseModel):
    id: UUID
    orden_id: UUID
    estado: str
    guia: Optional[str] = None
    transportista: Optional[str] = None
    ruta: Optional[str] = None
    ubicacion_actual: Optional[str] = None
    motivo: Optional[str] = None
    fecha_estimada: Optional[datetime] = None
    version: int
    actualizado_en: datetime
    eventos: list[EventoDespacho]


class TrazaEnvio(BaseModel):
    id: str
    event_id: str
    tipo_evento: str
    direccion: str
    estado: str
    orden_id: Optional[UUID] = None
    correlation_id: Optional[str] = None
    simulacion: bool
    topic: Optional[str] = None
    message_id: Optional[str] = None
    intentos: int
    ultimo_error: Optional[str] = None
    estado_logistico: Optional[str] = None
    mensaje: dict[str, Any]
    atributos: dict[str, Any]
    created_at: datetime
    registro: str


class TrazabilidadResponse(BaseModel):
    items: list[TrazaEnvio]
    total: int
    pagina: int
    total_paginas: int


@router.get("/despachos/trazabilidad", response_model=TrazabilidadResponse,
            summary="Historial administrativo de mensajes, cotizaciones y estados de Entregas")
def trazabilidad(response: Response, orden_id: Optional[UUID] = None,
                 estado: Optional[str] = Query(None, max_length=50),
                 tipo_evento: Optional[str] = Query(None, max_length=100),
                 direccion: Optional[Literal["entrada", "salida"]] = None,
                 simulacion: Optional[bool] = None,
                 estado_logistico: Optional[str] = Query(None, max_length=50),
                 page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                 user: dict = Depends(get_current_user)):
    claims = user.get("payload", {})
    role = claims.get("app_metadata", {}).get("role") or claims.get("role")
    if role not in {"administrador", "gerente_comercial"}:
        raise HTTPException(403, "Solo administración puede consultar la trazabilidad de envíos.")
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, "No está disponible la trazabilidad de envíos.")
    response.headers["Cache-Control"] = "no-store"
    try:
        query = client.table("envios_trazabilidad").select("*", count="exact")
        for campo, valor in dict(orden_id=str(orden_id) if orden_id else None, estado=estado,
                                tipo_evento=tipo_evento, direccion=direccion, simulacion=simulacion,
                                estado_logistico=estado_logistico).items():
            if valor is not None:
                query = query.eq(campo, valor)
        res = query.order("created_at", desc=True).order("id", desc=True).range((page-1)*limit, page*limit-1).execute()
        total = res.count or 0
        return dict(items=res.data or [], total=total, pagina=page, total_paginas=max(1, (total+limit-1)//limit))
    except Exception as exc:
        raise HTTPException(503, "No se pudo cargar la trazabilidad. Verifica la migración de envíos.") from exc


def autorizar(orden_id: UUID, user: dict, solo_admin=False):
    claims = user.get("payload", {})
    role = claims.get("app_metadata", {}).get("role") or claims.get("role", "cliente")
    es_admin = role in {"administrador", "gerente_comercial"}
    if solo_admin and not es_admin:
        raise HTTPException(403, "Solo administración puede reintentar un despacho.")
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, "Se requiere persistencia para consultar despachos.")
    try:
        rows = client.table("ordenes").select("cliente_id").eq("id", str(orden_id)).limit(1).execute().data or []
    except Exception:
        raise HTTPException(503, "No se pudo consultar la orden.")
    if not rows or (not es_admin and str(rows[0]["cliente_id"]) != user["user_id"]):
        raise HTTPException(404, "Orden no encontrada.")


@router.get("/{id}/despacho", response_model=DespachoResponse, summary="Leer el seguimiento local del despacho")
def obtener(id: UUID, user: dict = Depends(get_current_user)):
    autorizar(id, user)
    return despachos.operar("obtener", orden_id=str(id))


@router.post("/{id}/despacho/consultar", response_model=DespachoResponse, status_code=202,
             summary="Enviar automáticamente una consulta de estado al ERP por Pub/Sub")
def consultar(id: UUID, user: dict = Depends(get_current_user)):
    autorizar(id, user)
    return despachos.operar("consultar", orden_id=str(id), actor=user["user_id"])


@router.post("/{id}/despacho/reintentar", response_model=DespachoResponse, status_code=202,
             summary="Reintentar la solicitud existente sin generar un despacho duplicado")
def reintentar(id: UUID, user: dict = Depends(get_current_user)):
    autorizar(id, user, solo_admin=True)
    return despachos.operar("reintentar", orden_id=str(id), actor=user["user_id"])
