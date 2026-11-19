"""Auditoría explícita de endpoints administrativos, sin hooks globales ni bloqueos."""
import inspect
from functools import wraps

from backend.shared.audit import registrar_auditoria
from backend.shared.database import get_supabase_admin_client


def audit_operation(action: str, entity: str, *, id_arg: str | None = None, key: str = "id"):
    """Registra un endpoint concreto. Los errores auxiliares no afectan su resultado."""
    def decorate(function):
        signature = inspect.signature(function)
        def snapshot(client, identifier):
            if client is None or identifier is None:
                return None
            try:
                rows = client.table(entity).select("*").eq(key, str(identifier)).limit(1).execute().data or []
                return rows[0] if rows else None
            except Exception:
                return {"_auditoria": "No se pudo obtener el valor persistido."}

        @wraps(function)
        async def wrapped(*args, **kwargs):
            arguments = signature.bind_partial(*args, **kwargs).arguments
            identifier = arguments.get(id_arg) if id_arg else None
            if key == "codigo" and identifier is not None:
                identifier = str(identifier).upper()
            client = get_supabase_admin_client()
            before = snapshot(client, identifier)
            result = await function(*args, **kwargs)
            after = snapshot(client, identifier) if id_arg and client else result
            if identifier is None:
                identifier = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
            registrar_auditoria(client, current_user=arguments.get("current_user") or {},
                accion=action, entidad=entity, entidad_id=identifier, antes=before, despues=after)
            return result
        return wrapped
    return decorate
