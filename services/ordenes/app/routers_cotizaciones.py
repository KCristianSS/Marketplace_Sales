"""API de emisión, búsqueda y descarga de cotizaciones B2B (KAN-195)."""
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_current_user
from backend.shared.audit_context import trusted_role
from backend.shared.cotizaciones_config import (
    ActualizarConfiguracionB2B, RegistroConfiguracionB2B, obtener_configuracion_b2b, guardar_configuracion_b2b,
)
try:
    from app.cotizaciones import cotizaciones_a_respuestas, emitir_cotizacion, marcar_vencidas
    from app.pdf import generar_cotizacion_pdf
    from app.schemas import CotizacionVolumenCreate
except ModuleNotFoundError:
    from backend.services.ordenes.app.cotizaciones import cotizaciones_a_respuestas, emitir_cotizacion, marcar_vencidas
    from backend.services.ordenes.app.pdf import generar_cotizacion_pdf
    from backend.services.ordenes.app.schemas import CotizacionVolumenCreate

logger = logging.getLogger("maxiconecta.cotizaciones.api")
router = APIRouter(prefix="/api/v1/cotizaciones", tags=["Cotizaciones B2B"])
ROLES_COMERCIALES = {"gerente_comercial", "administrador"}


def _exigir_rol_comercial(user: Dict[str, Any]) -> None:
    if trusted_role(user.get("payload") or {}) not in ROLES_COMERCIALES:
        raise HTTPException(status_code=403, detail="Solo gerencia comercial puede gestionar cotizaciones B2B.")


def _cliente():
    client = get_supabase_admin_client()
    if not client:
        raise HTTPException(status_code=503, detail="El servicio de cotizaciones no está disponible.")
    return client


@router.get("/configuracion",response_model=RegistroConfiguracionB2B,summary="Consultar escalas de descuento por volumen")
def consultar_reglas(response: Response,current_user: dict=Depends(get_current_user)):
    _exigir_rol_comercial(current_user)
    response.headers["Cache-Control"]="no-store"
    return obtener_configuracion_b2b(_cliente())


@router.put("/configuracion",response_model=RegistroConfiguracionB2B,summary="Guardar escalas de descuento para nuevas cotizaciones")
def actualizar_reglas(payload: ActualizarConfiguracionB2B,current_user: dict=Depends(get_current_user)):
    _exigir_rol_comercial(current_user)
    return guardar_configuracion_b2b(_cliente(),payload,current_user)


@router.get("/clientes")
async def buscar_clientes_corporativos(
    q: Optional[str] = Query(None, max_length=50),
    limit: int = Query(30, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_rol_comercial(current_user)
    client = _cliente()
    query = client.table("perfiles_clientes").select("id,nombre_completo,razon_social,nit_ci,email").eq("tipo_cliente", "corporativo_b2b")
    if q and q.strip():
        term = q.strip().replace("%", "").replace("_", "")
        query = query.ilike("nit_ci", f"%{term}%")
    try:
        rows = query.order("razon_social").limit(limit).execute().data or []
        return rows
    except Exception as exc:
        logger.exception("No se pudieron buscar clientes corporativos")
        raise HTTPException(status_code=503, detail="No se pudieron cargar los clientes corporativos.") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def crear_cotizacion_b2b(
    payload: CotizacionVolumenCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_rol_comercial(current_user)
    manager_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    try:
        manager_id = str(UUID(manager_id))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="La sesión no tiene un identificador válido de gerente.") from exc
    client = _cliente()
    try:
        return emitir_cotizacion(client, payload, manager_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error inesperado al emitir cotización B2B")
        raise HTTPException(status_code=503, detail="No se pudo emitir la cotización.") from exc


@router.get("")
async def listar_cotizaciones_b2b(
    estado: Optional[str] = Query(None, pattern="^(emitida|pendiente_aprobacion|aprobada|rechazada|convertida|vencida)$"),
    cliente_id: Optional[UUID] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_rol_comercial(current_user)
    if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
        raise HTTPException(status_code=422, detail="La fecha final no puede ser anterior a la inicial.")
    client = _cliente()
    try:
        marcar_vencidas(client)
        query = client.table("cotizaciones_b2b").select("*", count="exact")
        if estado:
            query = query.eq("estado", estado)
        if cliente_id:
            query = query.eq("cliente_id", str(cliente_id))
        if fecha_desde:
            query = query.gte("created_at", datetime.combine(fecha_desde, time.min, tzinfo=timezone(timedelta(hours=-4))).isoformat())
        if fecha_hasta:
            query = query.lte("created_at", datetime.combine(fecha_hasta, time.max, tzinfo=timezone(timedelta(hours=-4))).isoformat())
        result = query.order("created_at", desc=True).range((page - 1) * limit, page * limit - 1).execute()
        rows = result.data or []
        total = int(result.count or 0)
        return {
            "items": cotizaciones_a_respuestas(client, rows),
            "total": total,
            "pagina": page,
            "limite": limit,
            "total_paginas": max(1, (total + limit - 1) // limit),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudieron consultar cotizaciones B2B")
        raise HTTPException(status_code=503, detail="No se pudo consultar el listado de cotizaciones.") from exc


@router.get("/{cotizacion_id}/pdf")
async def descargar_cotizacion_pdf(
    cotizacion_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_rol_comercial(current_user)
    client = _cliente()
    try:
        rows = client.table("cotizaciones_b2b").select("*").eq("id", str(cotizacion_id)).limit(1).execute().data or []
        if not rows:
            raise HTTPException(status_code=404, detail="No se encontró la cotización.")
        quote = cotizaciones_a_respuestas(client, rows)[0]
        return Response(
            content=generar_cotizacion_pdf(quote),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{quote.codigo_cotizacion}.pdf"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo generar PDF de cotización %s", cotizacion_id)
        raise HTTPException(status_code=500, detail="No se pudo generar el PDF de la cotización.") from exc
