"""Registro en ``audit_logs`` (RF-49/RF-50) con respaldo en memoria para desarrollo y pruebas."""
import logging
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Request
from pydantic import BaseModel
from backend.shared.config import settings
from backend.shared.audit_context import audit_context
from typing import Any, Dict, List, Optional

from fastapi.encoders import jsonable_encoder

from backend.shared.database import get_supabase_admin_client

logger = logging.getLogger("uvicorn.error.audit")

AUDIT_LOGS_EN_MEMORIA: List[Dict[str, Any]] = []


def _uuid_o_none(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


async def registrar_audit(
    action: str,
    entity: str,
    entity_id: Any,
    current_user: Optional[Dict[str, Any]] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Guarda una fila de auditoría. Nunca lanza: una falla de auditoría no debe tumbar la operación."""
    return registrar_auditoria(get_supabase_admin_client(), current_user=current_user or {},
        accion=action, entidad=entity, entidad_id=entity_id, antes=before, despues=after)


_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization", "access_token", "refresh_token", "token", "pin", "password",
    "contrasena", "secret", "service_role_key", "private_key", "credential",
    "codigo_hash", "codigo_cifrado", "codigo_encriptado", "codigo_version",
}
_MAX_DEPTH = 8


def _safe_snapshot(value: Any, depth: int = 0) -> Any:
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value[:2000] if isinstance(value, str) and len(value) > 2000 else value
    if isinstance(value, (uuid.UUID, datetime, date, Decimal)):
        return str(value) if not isinstance(value, datetime) else value.isoformat()
    if isinstance(value, BaseModel):
        return _safe_snapshot(value.model_dump(mode="json"), depth + 1)
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            name = str(key)
            normalized = name.lower().replace("-", "_")
            sensitive = any(term in normalized for term in _SENSITIVE_KEYS)
            cleaned[name] = _REDACTED if sensitive and item not in (None, "", False) else _safe_snapshot(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_safe_snapshot(item, depth + 1) for item in list(value)[:100]]
    return str(value)


def _uuid_or_none(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except (TypeError, ValueError, AttributeError):
        return None


def registrar_auditoria(
    client: Any,
    *,
    current_user: Dict[str, Any],
    accion: str,
    entidad: str,
    entidad_id: Any = None,
    antes: Any = None,
    despues: Any = None,
    request: Optional[Request] = None,
) -> Dict[str, Any]:
    """Guarda contexto uniforme y reintenta fallos de Supabase desde una cola durable."""
    context = audit_context.get()
    authenticated = context.get("actor_id") and context.get("actor_id") != "anonimo"
    user_id = str(context.get("actor_id") if authenticated else
                  current_user.get("user_id") or current_user.get("sub") or current_user.get("role") or context.get("actor_id") or "sistema")
    peer = context.get("ip_address") or (request.client.host if request and request.client else None)
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": _uuid_or_none(user_id),
        "actor_id": user_id,
        "user_role": str(context.get("role") if authenticated else current_user.get("role") or context.get("role") or "sistema")[:50],
        "ip_address": peer,
        "action": str(accion)[:100],
        "entity": str(entidad)[:100],
        "entity_id": _uuid_or_none(entidad_id),
        "payload_before": _safe_snapshot(antes),
        "payload_after": _safe_snapshot(despues),
        "created_at": now,
        "request_id": context.get("request_id"),
        "request_method": context.get("request_method") or (request.method if request else None),
        "request_path": context.get("request_path") or (request.url.path if request else None),
        "user_agent": context.get("user_agent") or (request.headers.get("user-agent") if request else None),
        "source": "application",
    }
    structured = {
        **row,
        "timestamp": now.replace("+00:00", "Z"),
    }

    if settings.ENVIRONMENT == "testing" and client is None:
        AUDIT_LOGS_EN_MEMORIA.append(structured)
        logger.info("AUDIT %s", json.dumps(structured, ensure_ascii=False, sort_keys=True))
        return structured

    try:
        if settings.ENVIRONMENT == "testing":
            client.table("audit_logs").insert(row).execute()
            structured["persistencia"] = "supabase"
        else:
            from backend.shared import audit_spool
            audit_spool.enqueue(row)
            structured["persistencia"] = "supabase" if audit_spool.deliver(client, row["id"]) else "pendiente"
        logger.info("AUDIT %s", json.dumps(structured, ensure_ascii=False, sort_keys=True))
    except Exception:
        structured["persistencia"] = "log_emergencia"
        logger.error("AUDIT_EMERGENCIA %s", json.dumps(structured, ensure_ascii=False, sort_keys=True))
    return structured
