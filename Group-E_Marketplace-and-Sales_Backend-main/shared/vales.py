"""Vales prepagados: códigos secretos y operaciones monetarias atómicas vía RPC.

No se degrada a memoria si falta la BD: un vale representa dinero real.
"""
import hashlib
import hmac
import re
from typing import Any

from fastapi import HTTPException

from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client


def generar_codigo(identificador: str, version: str) -> str:
    secreto = settings.VALES_CODIGO_SECRET
    if not secreto or len(secreto) < 32:
        raise HTTPException(503, "Configura VALES_CODIGO_SECRET con al menos 32 caracteres antes de emitir vales.")
    digest = hmac.new(secreto.encode(), f"vale:{identificador}:{version}".encode(), hashlib.sha256).hexdigest()[:32].upper()
    return "MAXI-" + "-".join(digest[i:i + 8] for i in range(0, 32, 8))


def hash_codigo(codigo: str) -> str:
    limpio = re.sub(r"[\s-]", "", codigo).upper()
    if not re.fullmatch(r"MAXI[0-9A-F]{32}", limpio):
        raise HTTPException(422, "Código de tarjeta de regalo inválido.")
    return hashlib.sha256(limpio.encode()).hexdigest()


def cliente_bd():
    cliente = get_supabase_admin_client()
    if cliente is None:
        raise HTTPException(503, "El servicio de vales requiere Supabase y la migración de tarjetas de regalo.")
    return cliente


def operar(accion: str, actor: str, **datos: Any) -> dict:
    client = cliente_bd()
    audit_actions = {"emitir", "reservar", "liberar", "consumir", "estado", "regenerar", "reintegrar", "revertir_reintegro", "compensar"}
    before = None
    identifier = datos.get("id") or datos.get("reserva_id")
    table = "tarjetas_regalo" if accion in {"emitir", "estado", "regenerar"} else "reservas_vale"
    if accion in audit_actions and identifier:
        try:
            rows = client.table(table).select("*").eq("id", str(identifier)).limit(1).execute().data or []
            before = rows[0] if rows else None
        except Exception:
            before = {"_auditoria": "Valor anterior no disponible."}
    try:
        resultado = client.rpc("operar_vale", {
            "p_accion": accion, "p_actor": actor, "p_datos": datos,
        }).execute().data
    except HTTPException:
        raise
    except Exception:
        # No filtrar hashes, códigos ni mensajes SQL al consumidor.
        raise HTTPException(503, "No se pudo completar la operación del vale. Verifica la conexión y la migración.")
    if not isinstance(resultado, dict):
        raise HTTPException(503, "La base de datos no confirmó la operación del vale.")
    if resultado.get("error"):
        raise HTTPException(int(resultado.get("status", 409)), resultado["error"])
    if accion in audit_actions:
        from backend.shared.audit import registrar_auditoria
        registrar_auditoria(client, current_user={"user_id": actor, "role": "sistema"},
            accion="VALE_" + accion.upper(), entidad=table,
            entidad_id=resultado.get("id") or identifier, antes=before, despues=publico(resultado))
    return resultado


def publico(fila: dict) -> dict:
    return {k: v for k, v in fila.items() if k not in {"codigo_hash", "codigo_version"}}


def reintegrar(transaccion_id: str) -> dict:
    return operar("reintegrar", "sistema", reserva_id=transaccion_id.removeprefix("VALE-"))
