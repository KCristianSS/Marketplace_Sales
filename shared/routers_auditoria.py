from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from backend.shared.audit import _safe_snapshot
from backend.shared.audit_context import trusted_role
from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_current_user

router = APIRouter(prefix="/api/v1/admin/auditoria", tags=["Auditoría de operaciones críticas"])


class AuditEntry(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    actor_id: Optional[str] = None
    user_role: Optional[str] = None
    ip_address: Optional[str] = None
    action: str
    entity: str
    entity_id: Optional[UUID] = None
    payload_before: Any = None
    payload_after: Any = None
    created_at: datetime
    request_id: Optional[UUID] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    user_agent: Optional[str] = None
    source: str = "legacy"


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    pagina: int
    total_paginas: int
    pendientes_locales: Optional[int] = None


@router.get("", response_model=AuditPage, summary="Consultar quién, qué, cuándo, origen y valores antes/después")
@router.get("/", response_model=AuditPage, include_in_schema=False)
def consultar_auditoria(response: Response,
    accion: Optional[str] = Query(None, max_length=100),
    entidad: Optional[str] = Query(None, max_length=100),
    actor: Optional[UUID] = None,
    rol: Optional[str] = Query(None, max_length=50),
    solicitud: Optional[UUID] = None,
    desde: Optional[datetime] = None, hasta: Optional[datetime] = None,
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    # No confiar en roles provenientes de user_metadata, editable por el usuario.
    if trusted_role(current_user.get("payload") or {}) != "administrador":
        raise HTTPException(403, "Solo el administrador puede consultar la auditoría.")
    desde = desde.replace(tzinfo=timezone.utc) if desde and not desde.tzinfo else desde
    hasta = hasta.replace(tzinfo=timezone.utc) if hasta and not hasta.tzinfo else hasta
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la fecha final.")
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, "La consulta de auditoría requiere conexión con la base de datos.")
    try:
        query = client.table("audit_logs").select("*", count="exact")
        for field, value in (("action", accion), ("entity", entidad), ("user_role", rol), ("request_id", str(solicitud) if solicitud else None)):
            if value: query = query.eq(field, value)
        if actor:
            query = query.or_(f"user_id.eq.{actor},actor_id.eq.{actor}")
        if desde: query = query.gte("created_at", desde.isoformat())
        if hasta: query = query.lte("created_at", hasta.isoformat())
        result = query.order("created_at", desc=True).order("id", desc=True).range((page-1)*limit, page*limit-1).execute()
        rows = result.data or []
        total = result.count or 0
    except Exception as exc:
        raise HTTPException(503, "No se pudo consultar la auditoría. Intenta nuevamente.") from exc
    for row in rows:
        row["actor_id"] = row.get("actor_id") or row.get("user_id")
        row["payload_before"] = _safe_snapshot(row.get("payload_before"))
        row["payload_after"] = _safe_snapshot(row.get("payload_after"))
    try:
        from backend.shared.audit_spool import summary
        pending = summary()["pendientes"]
    except Exception:
        pending = None
    response.headers["Cache-Control"] = "no-store"
    return dict(items=rows, total=total, pagina=page, total_paginas=max(1,(total+limit-1)//limit), pendientes_locales=pending)
