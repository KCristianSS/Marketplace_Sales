"""
Capa de servicios de negocio para el módulo POS — Gestión de Caja por Turno (RF-09).

Encapsula toda la lógica transaccional de apertura, control y cierre de caja,
delegando la persistencia a Supabase (tabla ``caja_turnos``) y al almacén en
memoria como fallback de desarrollo.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

# Cash-shift writes are server-side and RBAC-guarded at the gateway; the anon key is blocked by RLS on caja_turnos.
from backend.shared.database import get_supabase_admin_client as get_supabase_client

logger = logging.getLogger("maxiconecta.pos.services")

# ---------------------------------------------------------------------------
# Fallback en memoria para desarrollo local sin Supabase
# ---------------------------------------------------------------------------
_CAJAS_EN_MEMORIA: Dict[str, Dict[str, Any]] = {}
_MOVIMIENTOS_EN_MEMORIA: Dict[str, List[Dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal:
    """Convierte a Decimal de forma segura."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


# =====================================================================
# APERTURA DE CAJA
# =====================================================================

async def abrir_turno(
    sucursal_id: str,
    cajero_id: str,
    fondo_inicial: Decimal,
) -> Dict[str, Any]:
    """
    Abre un nuevo turno de caja.

    Reglas de negocio:
    - Un cajero no puede tener dos cajas abiertas al mismo tiempo.
    - El fondo inicial debe ser >= 0.

    Returns:
        Diccionario con los datos de la caja recién creada.

    Raises:
        ValueError si el cajero ya tiene una caja abierta.
    """
    supabase = get_supabase_client()

    if supabase:
        # Verificar caja abierta existente del cajero
        existing = (
            supabase.table("caja_turnos")
            .select("id")
            .eq("cajero_id", cajero_id)
            .eq("estado", "abierta")
            .execute()
        )
        if existing.data:
            raise ValueError(
                f"El cajero ya tiene una caja abierta (ID: {existing.data[0]['id']}). "
                "Debe cerrarla antes de aperturar una nueva."
            )

        caja_id = str(uuid.uuid4())
        row = {
            "id": caja_id,
            "sucursal_id": sucursal_id,
            "cajero_id": cajero_id,
            "fondo_inicial": float(fondo_inicial),
            "total_efectivo": 0,
            "total_tarjeta": 0,
            "total_qr": 0,
            "estado": "abierta",
        }
        result = supabase.table("caja_turnos").insert(row).execute()
        return result.data[0]
    else:
        # Fallback en memoria
        for caja in _CAJAS_EN_MEMORIA.values():
            if caja["cajero_id"] == cajero_id and caja["estado"] == "abierta":
                raise ValueError(
                    f"El cajero ya tiene una caja abierta (ID: {caja['id']}). "
                    "Debe cerrarla antes de aperturar una nueva."
                )

        caja_id = str(uuid.uuid4())
        caja = {
            "id": caja_id,
            "sucursal_id": sucursal_id,
            "cajero_id": cajero_id,
            "fondo_inicial": float(fondo_inicial),
            "total_efectivo": 0,
            "total_tarjeta": 0,
            "total_qr": 0,
            "estado": "abierta",
            "monto_cierre_real": None,
            "diferencia": None,
            "observaciones": None,
            "opened_at": _now_iso(),
            "closed_at": None,
        }
        _CAJAS_EN_MEMORIA[caja_id] = caja
        _MOVIMIENTOS_EN_MEMORIA[caja_id] = []
        return caja


# =====================================================================
# OBTENER CAJA
# =====================================================================

async def obtener_caja(caja_id: str) -> Optional[Dict[str, Any]]:
    """Retorna la caja por su ID, o None si no existe."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("id", caja_id)
            .execute()
        )
        return result.data[0] if result.data else None
    else:
        return _CAJAS_EN_MEMORIA.get(caja_id)


async def obtener_caja_activa(cajero_id: str) -> Optional[Dict[str, Any]]:
    """Retorna la caja abierta del cajero, o None si no tiene."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("cajero_id", cajero_id)
            .eq("estado", "abierta")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    else:
        for caja in _CAJAS_EN_MEMORIA.values():
            if caja["cajero_id"] == cajero_id and caja["estado"] == "abierta":
                return caja
        return None


# =====================================================================
# ACUMULAR TOTALES POR MÉTODO DE PAGO
# =====================================================================

async def acumular_venta(caja_id: str, metodo_pago: str, monto: Decimal) -> None:
    """
    Incrementa el acumulado del método de pago correspondiente en la caja.
    Llamado después de procesar cada venta POS.
    """
    campo_map = {
        "efectivo": "total_efectivo",
        "tarjeta": "total_tarjeta",
        "qr": "total_qr",
    }
    campo = campo_map.get(metodo_pago, "total_qr")

    supabase = get_supabase_client()
    if supabase:
        caja = await obtener_caja(caja_id)
        if not caja:
            return
        nuevo_total = _decimal(caja[campo]) + monto
        supabase.table("caja_turnos").update(
            {campo: float(nuevo_total)}
        ).eq("id", caja_id).execute()
    else:
        caja = _CAJAS_EN_MEMORIA.get(caja_id)
        if caja:
            caja[campo] = float(_decimal(caja[campo]) + monto)


# =====================================================================
# MOVIMIENTOS MANUALES (INGRESO / EGRESO)
# =====================================================================

async def registrar_movimiento(
    caja_id: str,
    tipo: str,
    monto: Decimal,
    descripcion: str,
) -> Dict[str, Any]:
    """
    Registra un ingreso o egreso manual en la caja (ej. retiro de efectivo,
    ingreso de cambio). Persiste en la tabla ``movimientos_caja``.
    """
    supabase = get_supabase_client()
    mov_id = str(uuid.uuid4())

    if supabase:
        row = {
            "id": mov_id,
            "caja_turno_id": caja_id,
            "tipo": tipo,
            "monto": float(monto),
            "descripcion": descripcion,
        }
        result = supabase.table("movimientos_caja").insert(row).execute()
        return result.data[0]
    else:
        mov = {
            "id": mov_id,
            "caja_turno_id": caja_id,
            "tipo": tipo,
            "monto": float(monto),
            "descripcion": descripcion,
            "created_at": _now_iso(),
        }
        _MOVIMIENTOS_EN_MEMORIA.setdefault(caja_id, []).append(mov)
        return mov


async def listar_movimientos(caja_id: str) -> List[Dict[str, Any]]:
    """Retorna todos los movimientos manuales de una caja."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("movimientos_caja")
            .select("*")
            .eq("caja_turno_id", caja_id)
            .order("created_at")
            .execute()
        )
        return result.data
    else:
        return _MOVIMIENTOS_EN_MEMORIA.get(caja_id, [])


# =====================================================================
# CIERRE DE CAJA Y ARQUEO
# =====================================================================

async def cerrar_turno(
    caja_id: str,
    monto_cierre_real: Decimal,
    observaciones: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cierra el turno de caja y calcula la diferencia del arqueo.

    Fórmula:
        total_esperado = fondo_inicial + total_efectivo + ingresos_manuales - egresos_manuales
        diferencia     = monto_cierre_real - total_esperado

    Returns:
        Diccionario con el resumen completo del arqueo.

    Raises:
        ValueError si la caja no existe o no está abierta.
    """
    caja = await obtener_caja(caja_id)
    if not caja:
        raise ValueError("Caja no encontrada")
    if caja["estado"] != "abierta":
        raise ValueError(
            f"La caja no está abierta (estado actual: {caja['estado']}). "
            "Solo se puede cerrar una caja en estado 'abierta'."
        )

    # Calcular totales de movimientos manuales
    movimientos = await listar_movimientos(caja_id)
    total_ingresos = sum(_decimal(m["monto"]) for m in movimientos if m["tipo"] == "ingreso")
    total_egresos = sum(_decimal(m["monto"]) for m in movimientos if m["tipo"] == "egreso")

    total_esperado = (
        _decimal(caja["fondo_inicial"])
        + _decimal(caja["total_efectivo"])
        + total_ingresos
        - total_egresos
    )
    diferencia = monto_cierre_real - total_esperado
    closed_at = _now_iso()

    supabase = get_supabase_client()
    if supabase:
        supabase.table("caja_turnos").update({
            "estado": "cerrada",
            "monto_cierre_real": float(monto_cierre_real),
            "diferencia": float(diferencia),
            "observaciones": observaciones,
            "closed_at": closed_at,
        }).eq("id", caja_id).execute()
    else:
        caja_mem = _CAJAS_EN_MEMORIA.get(caja_id)
        if caja_mem:
            caja_mem["estado"] = "cerrada"
            caja_mem["monto_cierre_real"] = float(monto_cierre_real)
            caja_mem["diferencia"] = float(diferencia)
            caja_mem["observaciones"] = observaciones
            caja_mem["closed_at"] = closed_at

    return {
        "caja_turno_id": caja_id,
        "cajero_id": caja["cajero_id"],
        "sucursal_id": caja["sucursal_id"],
        "fondo_inicial": caja["fondo_inicial"],
        "total_efectivo": caja["total_efectivo"],
        "total_tarjeta": caja["total_tarjeta"],
        "total_qr": caja["total_qr"],
        "total_ingresos_manuales": float(total_ingresos),
        "total_egresos_manuales": float(total_egresos),
        "total_esperado": float(total_esperado),
        "monto_cierre_real": float(monto_cierre_real),
        "diferencia": float(diferencia),
        "estado": "cerrada",
        "observaciones": observaciones,
        "opened_at": caja.get("opened_at"),
        "closed_at": closed_at,
    }


# =====================================================================
# HISTORIAL DE CAJAS
# =====================================================================

async def obtener_historial(
    cajero_id: str,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Retorna el historial de cajas de un cajero, ordenado por fecha desc."""
    supabase = get_supabase_client()

    if supabase:
        result = (
            supabase.table("caja_turnos")
            .select("*")
            .eq("cajero_id", cajero_id)
            .order("opened_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data
    else:
        cajas = [
            c for c in _CAJAS_EN_MEMORIA.values()
            if c["cajero_id"] == cajero_id
        ]
        cajas.sort(key=lambda c: c.get("opened_at", ""), reverse=True)
        return cajas[offset:offset + limit]
