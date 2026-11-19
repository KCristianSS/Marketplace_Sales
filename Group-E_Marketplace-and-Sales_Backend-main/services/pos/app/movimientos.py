"""
KAN-342 — MovimientoEfectivoService: entradas extraordinarias y retiros parciales a bóveda.

Reglas:
  * Motivo obligatorio.
  * Retiro mayor al efectivo disponible en la gaveta  -> se rechaza (422).
  * Retiro mayor al límite de seguridad (def. Bs. 2.000) -> exige confirmación de un supervisor (428).
  * Todo movimiento genera comprobante imprimible y queda en audit_logs.
  * El efectivo esperado del turno = fondo + ventas efectivo + entradas − retiros (ver ``movimientos_netos``).
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

try:
    from app.services import (
        _decimal,
        calcular_movimientos_netos,
        listar_movimientos,
        movimientos_netos,
        registrar_movimiento,
    )
except (ModuleNotFoundError, ImportError):
    from backend.services.pos.app.services import (
        _decimal,
        calcular_movimientos_netos,
        listar_movimientos,
        movimientos_netos,
        registrar_movimiento,
    )

from backend.shared.audit import registrar_audit
from backend.shared.config import settings
from backend.shared.security import decode_access_token

logger = logging.getLogger("maxiconecta.pos.movimientos")

ROLES_SUPERVISOR = frozenset({"administrador", "supervisor"})


def limite_seguridad() -> Decimal:
    return Decimal(str(settings.CAJA_LIMITE_SEGURIDAD_RETIRO)).quantize(Decimal("0.01"))


def efectivo_disponible(caja: Dict[str, Any], netos: Dict[str, Decimal]) -> Decimal:
    """Efectivo físico que debería haber en la gaveta ahora mismo."""
    return _decimal(caja["fondo_inicial"]) + _decimal(caja["total_efectivo"]) + netos["neto"]


def resolver_supervisor(current_user: Dict[str, Any], supervisor_token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Supervisor que confirma: el propio usuario (si lo es) o el dueño de ``supervisor_token``."""
    if str(current_user.get("role", "")).lower() in ROLES_SUPERVISOR:
        return {"user_id": str(current_user.get("user_id")), "email": current_user.get("email")}
    if not supervisor_token:
        return None
    payload = decode_access_token(supervisor_token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La confirmación del supervisor no es válida o expiró.")
    meta = {**(payload.get("user_metadata") or {}), **(payload.get("app_metadata") or {})}
    rol = str(payload.get("role") or meta.get("role") or "").lower()
    if rol not in ROLES_SUPERVISOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El usuario que confirma no tiene rol de supervisor.")
    return {"user_id": str(payload["sub"]), "email": payload.get("email")}


def construir_comprobante(mov: Dict[str, Any], caja: Dict[str, Any], supervisor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ahora = datetime.now(timezone.utc)
    numero = f"MOV-{ahora.strftime('%Y%m%d')}-{str(mov['id']).replace('-', '')[:6].upper()}"
    return {
        "numero": numero,
        "tipo": mov["tipo"],
        "monto": str(_decimal(mov["monto"]).quantize(Decimal("0.01"))),
        "motivo": mov["motivo"],
        "caja_turno_id": str(caja["id"]),
        "sucursal_id": str(caja.get("sucursal_id")),
        "cajero_id": str(caja.get("cajero_id")),
        "supervisor_id": supervisor["user_id"] if supervisor else None,
        "supervisor_email": supervisor.get("email") if supervisor else None,
        "fecha": ahora.isoformat(),
    }


async def registrar_movimiento_efectivo(
    caja: Dict[str, Any],
    tipo: str,
    monto: Decimal,
    motivo: str,
    current_user: Dict[str, Any],
    supervisor_token: Optional[str] = None,
) -> Dict[str, Any]:
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise HTTPException(status_code=422, detail="El motivo del movimiento es obligatorio.")
    if caja["estado"] != "abierta":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La caja no está abierta.")
    monto = monto.quantize(Decimal("0.01"))

    es_admin = str(current_user.get("role", "")).lower() == "administrador"
    if not es_admin and str(caja["cajero_id"]) != str(current_user.get("user_id")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La caja pertenece a otro cajero.")

    supervisor: Optional[Dict[str, Any]] = None
    requiere_supervisor = False
    if tipo == "retiro":
        netos = await movimientos_netos(str(caja["id"]))
        disponible = efectivo_disponible(caja, netos)
        if monto > disponible:
            raise HTTPException(
                status_code=422,
                detail=f"Retiro rechazado: Bs. {monto} supera el efectivo disponible en la gaveta (Bs. {disponible}).",
            )
        if monto > limite_seguridad():
            requiere_supervisor = True
            supervisor = resolver_supervisor(current_user, supervisor_token)
            if not supervisor:
                raise HTTPException(
                    status_code=428,
                    detail={
                        "codigo": "SUPERVISOR_REQUERIDO",
                        "mensaje": f"Retiros mayores a Bs. {limite_seguridad()} requieren confirmación de un supervisor.",
                        "limite": str(limite_seguridad()),
                    },
                )
            if supervisor["user_id"] == str(caja["cajero_id"]):
                raise HTTPException(status_code=403, detail="El supervisor que confirma no puede ser el mismo cajero del turno.")

    mov = await registrar_movimiento(
        str(caja["id"]),
        tipo,
        monto,
        motivo,
        extra={
            "requiere_supervisor": requiere_supervisor,
            "supervisor_id": supervisor["user_id"] if supervisor else None,
            "registrado_por": str(current_user.get("user_id")),
        },
    )
    comprobante = construir_comprobante(mov, caja, supervisor)
    mov["numero_comprobante"] = comprobante["numero"]
    mov["comprobante"] = comprobante
    mov.setdefault("requiere_supervisor", requiere_supervisor)
    mov.setdefault("supervisor_id", supervisor["user_id"] if supervisor else None)
    # Persistir el número del comprobante en la fila (memoria: ya es la misma referencia).
    try:
        from backend.shared.database import get_supabase_admin_client

        sb = get_supabase_admin_client()
        if sb:
            sb.table("caja_movimientos").update({"numero_comprobante": comprobante["numero"], "comprobante": comprobante}).eq("id", mov["id"]).execute()
    except Exception:
        logger.exception("No se pudo guardar el número de comprobante %s", comprobante["numero"])

    await registrar_audit(
        "MOVIMIENTO_EFECTIVO_" + tipo.upper(),
        "caja_movimientos",
        mov["id"],
        current_user,
        after={**comprobante, "requiere_supervisor": requiere_supervisor},
    )
    return mov


async def listar_movimientos_efectivo(caja: Dict[str, Any]):
    movs = await listar_movimientos(str(caja["id"]))
    salida = []
    for m in movs:
        m = dict(m)
        if not m.get("comprobante"):
            sup = {"user_id": m["supervisor_id"], "email": None} if m.get("supervisor_id") else None
            m["comprobante"] = construir_comprobante(m, caja, sup)
            m["comprobante"]["numero"] = m.get("numero_comprobante") or m["comprobante"]["numero"]
            m["comprobante"]["fecha"] = str(m.get("created_at") or m["comprobante"]["fecha"])
        m["numero_comprobante"] = m.get("numero_comprobante") or m["comprobante"]["numero"]
        salida.append(m)
    return salida
