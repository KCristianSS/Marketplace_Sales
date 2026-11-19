"""
Almacén de turnos de caja compartido entre microservicios (POS y Órdenes).

* Con Supabase configurado, la fuente de verdad es la tabla ``caja_turnos``.
* Sin Supabase (desarrollo local / pruebas) se usa un almacén en memoria del proceso. Es el mismo
  objeto para POS y Órdenes cuando corren en un único proceso (pruebas), de modo que el pago en
  efectivo registrado desde Órdenes (KAN-54) suma al efectivo esperado del turno (KAN-341).
"""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from backend.shared.database import get_supabase_admin_client

logger = logging.getLogger("maxiconecta.caja_store")

CAJAS_EN_MEMORIA: Dict[str, Dict[str, Any]] = {}
MOVIMIENTOS_EN_MEMORIA: Dict[str, List[Dict[str, Any]]] = {}
ARQUEOS_EN_MEMORIA: Dict[str, Dict[str, Any]] = {}  # clave: caja_turno_id


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0.00")


async def obtener_caja_abierta(cajero_id: str, caja_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Devuelve la caja ``abierta`` del cajero (y, si se indica, solo si coincide con ``caja_id``)."""
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            query = supabase.table("caja_turnos").select("*").eq("cajero_id", cajero_id).eq("estado", "abierta")
            if caja_id:
                query = query.eq("id", caja_id)
            data = query.limit(1).execute().data
            return data[0] if data else None
        except Exception:
            logger.exception("No se pudo consultar la caja abierta del cajero %s", cajero_id)
            return None
    for caja in CAJAS_EN_MEMORIA.values():
        if caja["cajero_id"] == cajero_id and caja["estado"] == "abierta" and (not caja_id or caja["id"] == caja_id):
            return caja
    return None


async def acumular_efectivo(caja_id: str, monto: Decimal) -> None:
    """Suma (o resta, si ``monto`` es negativo) ventas en efectivo al turno de caja."""
    supabase = get_supabase_admin_client()
    if supabase:
        actual = supabase.table("caja_turnos").select("total_efectivo").eq("id", caja_id).limit(1).execute().data
        if not actual:
            return
        nuevo = _dec(actual[0]["total_efectivo"]) + monto
        supabase.table("caja_turnos").update({"total_efectivo": float(nuevo)}).eq("id", caja_id).execute()
        return
    caja = CAJAS_EN_MEMORIA.get(caja_id)
    if caja:
        caja["total_efectivo"] = float(_dec(caja["total_efectivo"]) + monto)
