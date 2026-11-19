"""API de consulta y reenvío de notificaciones transaccionales (KAN-218)."""
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from backend.shared.security import get_current_user
try:
    from app.notificaciones import obtener_notificacion, procesar_notificacion, reencolar_notificacion
except ModuleNotFoundError:
    from backend.services.ordenes.app.notificaciones import obtener_notificacion, procesar_notificacion, reencolar_notificacion

logger = logging.getLogger("maxiconecta.notificaciones.api")
router = APIRouter(prefix="/api/v1/notificaciones", tags=["Notificaciones"])
ROLES_ADMIN = {"administrador", "gerente_comercial"}


def _exigir_administrador(current_user: Dict[str, Any]) -> None:
    if str(current_user.get("role", "")).lower() not in ROLES_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administración puede consultar la bitácora.")


@router.get("")
async def listar_notificaciones(
    estado: Optional[str] = Query(None, pattern="^(pendiente|procesando|enviada|fallida)$"),
    correo: Optional[str] = Query(None, max_length=255),
    orden_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_administrador(current_user)
    from backend.shared.database import get_supabase_admin_client

    client = get_supabase_admin_client()
    if not client:
        raise HTTPException(status_code=503, detail="La bitácora de notificaciones no está disponible.")
    query = client.table("notificaciones_log").select("*", count="exact")
    if estado:
        query = query.eq("estado", estado)
    if correo and correo.strip():
        query = query.ilike("correo_destino", f"%{correo.strip()}%")
    if orden_id:
        try:
            query = query.eq("orden_id", str(uuid.UUID(orden_id)))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="El ID de orden no es válido.") from exc
    query = query.order("creado_at", desc=True).range((page - 1) * limit, page * limit - 1)
    try:
        result = query.execute()
        rows = result.data or []
        # El cuerpo HTML se mantiene en el servidor; no se expone en la bitácora administrativa.
        for row in rows:
            row.pop("contenido", None)
        total = int(result.count or 0)
        return {"items": rows, "total": total, "pagina": page, "limite": limit, "total_paginas": max(1, (total + limit - 1) // limit)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo consultar la bitácora de notificaciones")
        raise HTTPException(status_code=500, detail="No se pudo consultar la bitácora.") from exc


@router.post("/{notificacion_id}/reenviar", status_code=status.HTTP_202_ACCEPTED)
async def reenviar_notificacion(
    notificacion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    _exigir_administrador(current_user)
    try:
        row = await obtener_notificacion(str(notificacion_id))
        if not row:
            raise HTTPException(status_code=404, detail="La notificación no existe.")
        if row.get("estado") != "fallida":
            raise HTTPException(status_code=409, detail="Solo se pueden reenviar notificaciones fallidas.")
        queued = await reencolar_notificacion(str(notificacion_id))
        if not queued:
            raise HTTPException(status_code=409, detail="La notificación cambió de estado; actualiza la bitácora.")
        background_tasks.add_task(procesar_notificacion, str(notificacion_id))
        queued.pop("contenido", None)
        return queued
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("No se pudo reenviar notificación %s", notificacion_id)
        raise HTTPException(status_code=500, detail="No se pudo programar el reenvío.") from exc
