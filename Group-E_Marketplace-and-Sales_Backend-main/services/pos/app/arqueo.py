"""
KAN-341 — ArqueoService: arqueo ciego al cierre del turno.

El cajero declara el desglose de billetes y monedas SIN ver el saldo teórico. Al confirmar, el sistema:
  1. congela lo declarado (las filas ``arqueo_caja``/``arqueo_detalle`` son inmutables),
  2. calcula esperado = fondo inicial + ventas en efectivo + movimientos netos (KAN-342, 0 si no existen),
  3. calcula la diferencia (declarado − esperado: positiva = sobrante, negativa = faltante),
  4. cierra el turno, registra audit_logs y, si hay diferencia, notifica a Contabilidad (simulado).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

try:
    from app import services as pos_services
except (ModuleNotFoundError, ImportError):
    from backend.services.pos.app import services as pos_services

from backend.shared.audit import registrar_audit
from backend.shared.caja_store import ARQUEOS_EN_MEMORIA
from backend.shared.database import get_supabase_admin_client
from backend.shared.erp_clients.contabilidad import contabilidad_client

logger = logging.getLogger("maxiconecta.pos.arqueo")

CENT = Decimal("0.01")
BILLETES = (Decimal("200"), Decimal("100"), Decimal("50"), Decimal("20"), Decimal("10"))
MONEDAS = (Decimal("5"), Decimal("2"), Decimal("1"), Decimal("0.50"), Decimal("0.20"), Decimal("0.10"))
DENOMINACIONES_VALIDAS = frozenset(BILLETES + MONEDAS)

_locks: Dict[str, asyncio.Lock] = {}


def _lock(caja_id: str) -> asyncio.Lock:
    return _locks.setdefault(caja_id, asyncio.Lock())


def _dec(v: Any) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0.00")


def _tipo(valor: Decimal) -> str:
    return "billete" if valor in BILLETES else "moneda"


async def _movimientos_netos(caja_id: str) -> Dict[str, Decimal]:
    """Obtiene los movimientos necesarios para calcular el efectivo esperado."""
    try:
        return await pos_services.movimientos_netos(caja_id)
    except Exception as exc:
        logger.exception("No se pudieron consultar los movimientos para el arqueo")
        raise HTTPException(status_code=503, detail="No se pudieron consultar los movimientos de caja. Intenta nuevamente.") from exc


def normalizar_desglose(desglose: List[Any]) -> List[Dict[str, Any]]:
    """Valida denominaciones (válidas y sin repetir) y calcula subtotales."""
    vistos = set()
    filas = []
    for d in desglose:
        valor = Decimal(str(d.denominacion)).quantize(CENT)
        if valor not in DENOMINACIONES_VALIDAS:
            raise HTTPException(status_code=422, detail=f"Denominación no válida: Bs. {valor}.")
        if valor in vistos:
            raise HTTPException(status_code=422, detail=f"Denominación repetida: Bs. {valor}.")
        vistos.add(valor)
        filas.append(
            {
                "tipo": _tipo(valor),
                "denominacion": valor,
                "cantidad": int(d.cantidad),
                "subtotal": (valor * int(d.cantidad)).quantize(CENT),
            }
        )
    filas.sort(key=lambda f: f["denominacion"], reverse=True)
    return filas


def _resultado(diferencia: Decimal) -> str:
    return "cuadrado" if diferencia == 0 else ("sobrante" if diferencia > 0 else "faltante")


async def ejecutar_arqueo_ciego(
    caja_id: str,
    desglose: List[Any],
    observaciones: Optional[str],
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    caja = await pos_services.obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    es_admin = str(current_user.get("role", "")).lower() == "administrador"
    if not es_admin and str(caja["cajero_id"]) != str(current_user.get("user_id")):
        raise HTTPException(status_code=403, detail="Solo el cajero del turno puede realizar su arqueo.")
    filas = normalizar_desglose(desglose)

    async with _lock(caja_id):
        # Relee dentro del candado: dos cierres simultáneos no pueden arquear el mismo turno.
        caja = await pos_services.obtener_caja(caja_id)
        if caja["estado"] != "abierta":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El turno ya fue cerrado y no puede arquearse de nuevo.")

        netos = await _movimientos_netos(caja_id)
        fondo, ventas = _dec(caja["fondo_inicial"]), _dec(caja["total_efectivo"])
        esperado = (fondo + ventas + netos["neto"]).quantize(CENT)
        declarado = sum((f["subtotal"] for f in filas), Decimal("0.00")).quantize(CENT)
        diferencia = (declarado - esperado).quantize(CENT)
        resultado = _resultado(diferencia)
        ahora = datetime.now(timezone.utc).isoformat()
        arqueo_id = str(uuid.uuid4())
        arqueo = {
            "id": arqueo_id,
            "numero_reporte": f"ARQ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{arqueo_id.replace('-', '')[:6].upper()}",
            "caja_turno_id": caja_id,
            "cajero_id": str(caja["cajero_id"]),
            "sucursal_id": str(caja["sucursal_id"]),
            "fondo_inicial": fondo,
            "ventas_efectivo": ventas,
            "entradas_extraordinarias": netos["entradas"],
            "retiros_boveda": netos["retiros"],
            "total_esperado": esperado,
            "total_declarado": declarado,
            "diferencia": diferencia,
            "resultado": resultado,
            "con_diferencia": diferencia != 0,
            "observaciones": (observaciones or "").strip() or None,
            "total_tarjeta": _dec(caja.get("total_tarjeta")),
            "total_qr": _dec(caja.get("total_qr")),
            "notificacion_contabilidad": None,
            "created_at": ahora,
        }

        sb = get_supabase_admin_client()
        if sb:
            fila = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in arqueo.items() if k not in {"resultado"}}
            fila["estado_cuadre"] = resultado
            detalle = [{"tipo": f["tipo"], "denominacion": float(f["denominacion"]),
                        "cantidad": f["cantidad"], "subtotal": float(f["subtotal"])} for f in filas]
            cierre = sb.rpc("confirmar_arqueo_ciego", {"p_arqueo": fila, "p_detalle": detalle}).execute()
            if cierre.data is not True:
                raise HTTPException(status_code=409, detail="El turno ya fue cerrado y no puede arquearse de nuevo.")
        else:
            caja.update(
                estado="cerrada", monto_cierre_real=float(declarado), diferencia=float(diferencia),
                con_diferencia=diferencia != 0, observaciones=arqueo["observaciones"], closed_at=ahora,
            )

        arqueo["desglose"] = filas
        arqueo["estado_turno"] = "cerrada"
        arqueo["opened_at"] = caja.get("opened_at")
        arqueo["closed_at"] = ahora

    # Efectos posteriores al cierre (no deben deshacerlo si fallan).
    if diferencia != 0:
        try:
            arqueo["notificacion_contabilidad"] = await contabilidad_client.notificar_arqueo_con_diferencia(
                {
                    "arqueo_id": arqueo_id,
                    "numero_reporte": arqueo["numero_reporte"],
                    "caja_turno_id": caja_id,
                    "sucursal_id": arqueo["sucursal_id"],
                    "cajero_id": arqueo["cajero_id"],
                    "resultado": resultado,
                    "diferencia": str(diferencia),
                    "total_esperado": str(esperado),
                    "total_declarado": str(declarado),
                }
            )
        except Exception as exc:
            logger.exception("Falló la notificación a Contabilidad del arqueo %s", arqueo_id)
            arqueo["notificacion_contabilidad"] = {"estado": "pendiente_reintento", "error": str(exc)}
        if sb:
            try:
                sb.table("arqueo_caja").update({"notificacion_contabilidad": arqueo["notificacion_contabilidad"]}).eq("id", arqueo_id).execute()
            except Exception:
                logger.exception("No se pudo guardar el estado de la notificación del arqueo %s", arqueo_id)

    if not sb:
        ARQUEOS_EN_MEMORIA[caja_id] = arqueo

    await registrar_audit(
        "ARQUEO_CIEGO_CIERRE",
        "arqueo_caja",
        arqueo_id,
        current_user,
        before={"estado": "abierta"},
        after={
            "estado": "cerrada",
            "con_diferencia": arqueo["con_diferencia"],
            "resultado": resultado,
            "total_declarado": declarado,
            "total_esperado": esperado,
            "diferencia": diferencia,
            "desglose": filas,
        },
    )
    return arqueo


async def obtener_reporte_arqueo(caja_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """Reporte de un arqueo ya confirmado. Mientras el turno siga abierto no existe: no se filtra ningún total."""
    caja = await pos_services.obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    es_admin = str(current_user.get("role", "")).lower() == "administrador"
    if not es_admin and str(caja["cajero_id"]) != str(current_user.get("user_id")):
        raise HTTPException(status_code=403, detail="El arqueo pertenece a otro cajero.")

    sb = get_supabase_admin_client()
    if sb:
        rows = sb.table("arqueo_caja").select("*").eq("caja_turno_id", caja_id).limit(1).execute().data
        if not rows:
            raise HTTPException(status_code=404, detail="El turno aún no tiene arqueo.")
        arqueo = rows[0]
        arqueo["resultado"] = arqueo.pop("estado_cuadre", _resultado(_dec(arqueo["diferencia"])))
        det = sb.table("arqueo_detalle").select("*").eq("arqueo_id", arqueo["id"]).execute().data or []
        arqueo["desglose"] = sorted(det, key=lambda f: _dec(f["denominacion"]), reverse=True)
        arqueo["estado_turno"] = caja["estado"]
        arqueo["opened_at"] = caja.get("opened_at")
        arqueo["closed_at"] = caja.get("closed_at")
        return arqueo
    arqueo = ARQUEOS_EN_MEMORIA.get(caja_id)
    if not arqueo:
        raise HTTPException(status_code=404, detail="El turno aún no tiene arqueo.")
    return arqueo
