"""
Repositorio de pagos, historial de pagos y reembolsos (KAN-54 / KAN-55).

Con Supabase usa las tablas ``ordenes``, ``pagos``, ``orden_pagos_historial`` y ``reembolsos``.
Sin Supabase (desarrollo/pruebas) usa almacenes en memoria; las órdenes en memoria son las del
router de órdenes (``_ORDENES_DB``).
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from backend.shared.database import get_supabase_admin_client

try:
    from app.routers import _ORDENES_DB
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.routers import _ORDENES_DB

logger = logging.getLogger("maxiconecta.pagos.repo")

_PAGOS: Dict[str, Dict[str, Any]] = {}
_HISTORIAL: List[Dict[str, Any]] = []
_REEMBOLSOS: Dict[str, Dict[str, Any]] = {}

CENT = Decimal("0.01")


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def dec(v: Any) -> Decimal:
    return Decimal(str(v if v is not None else 0)).quantize(CENT)


def _norm_pago(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    row["monto"] = dec(row.get("monto"))
    row["monto_reembolsado"] = dec(row.get("monto_reembolsado"))
    row.setdefault("intento", 1)
    row["intento"] = row.get("intento") or 1
    return row


def _norm_reembolso(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    row["monto"] = dec(row.get("monto"))
    return row


def _json(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


class PagosRepo:
    # ------------------------------------------------------------------ órdenes
    def get_orden(self, orden_id: str) -> Optional[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            data = sb.table("ordenes").select("id,codigo_orden,cliente_id,total,estado,canal").eq("id", orden_id).limit(1).execute().data
            if not data:
                return None
            o = data[0]
            return {**o, "total": dec(o["total"])}
        o = _ORDENES_DB.get(orden_id)
        if not o:
            return None
        return {"id": str(o.id), "codigo_orden": o.codigo_orden, "cliente_id": str(o.cliente_id), "total": dec(o.total), "estado": o.estado, "canal": o.canal}

    def set_orden_estado(self, orden_id: str, anterior: str, nuevo: str, usuario_id: Optional[str]) -> bool:
        sb = get_supabase_admin_client()
        if sb:
            cambios = {"estado": nuevo, "updated_at": ahora()}
            try:
                uuid.UUID(str(usuario_id))
                cambios["estado_actualizado_por"] = str(usuario_id)
            except (ValueError, TypeError):
                pass
            try:
                res = sb.table("ordenes").update(cambios).eq("id", orden_id).eq("estado", anterior).execute()
            except Exception as exc:  # BD sin la migración de auditoría de estados
                if "estado_actualizado_por" not in str(exc):
                    raise
                cambios.pop("estado_actualizado_por", None)
                res = sb.table("ordenes").update(cambios).eq("id", orden_id).eq("estado", anterior).execute()
            return bool(res.data)
        o = _ORDENES_DB.get(orden_id)
        if not o or o.estado != anterior:
            return False
        o.estado = nuevo
        o.historial_estados.append(
            {"estado_anterior": anterior, "estado_nuevo": nuevo, "usuario_id": usuario_id, "rol": "sistema:pagos", "cambiado_en": ahora()}
        )
        return True

    # ------------------------------------------------------------------ pagos
    def listar_pagos(self, orden_id: str) -> List[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            rows = sb.table("pagos").select("*").eq("orden_id", orden_id).order("created_at").execute().data or []
        else:
            rows = sorted((p for p in _PAGOS.values() if p["orden_id"] == orden_id), key=lambda p: p["created_at"])
        return [_norm_pago(r) for r in rows]

    def get_pago(self, pago_id: str) -> Optional[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            data = sb.table("pagos").select("*").eq("id", pago_id).limit(1).execute().data
            return _norm_pago(data[0]) if data else None
        return _norm_pago(_PAGOS[pago_id]) if pago_id in _PAGOS else None

    def get_pago_por_tx(self, transaccion_id: str) -> Optional[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            data = sb.table("pagos").select("*").eq("transaccion_id", transaccion_id).limit(1).execute().data
            return _norm_pago(data[0]) if data else None
        for p in _PAGOS.values():
            if p["transaccion_id"] == transaccion_id:
                return _norm_pago(p)
        return None

    def insertar_pago(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "created_at": ahora(), "updated_at": ahora(), "monto_reembolsado": Decimal("0.00"), **row}
        sb = get_supabase_admin_client()
        if sb:
            fila = _json({k: v for k, v in row.items() if k != "created_at"})
            return _norm_pago(sb.table("pagos").insert(fila).execute().data[0])
        _PAGOS[row["id"]] = row
        return _norm_pago(row)

    def actualizar_pago(self, pago_id: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        cambios = {**cambios, "updated_at": ahora()}
        sb = get_supabase_admin_client()
        if sb:
            return _norm_pago(sb.table("pagos").update(_json(cambios)).eq("id", pago_id).execute().data[0])
        _PAGOS[pago_id].update(cambios)
        return _norm_pago(_PAGOS[pago_id])

    # ------------------------------------------------------------------ historial de pagos
    def agregar_historial(self, row: Dict[str, Any]) -> None:
        row = {"id": str(uuid.uuid4()), "created_at": ahora(), **row}
        sb = get_supabase_admin_client()
        if sb:
            try:
                sb.table("orden_pagos_historial").insert(_json({k: v for k, v in row.items() if k != "created_at"})).execute()
            except Exception:
                logger.exception("No se pudo guardar el historial de pago de la orden %s", row.get("orden_id"))
            return
        _HISTORIAL.append(row)

    def listar_historial(self, orden_id: str) -> List[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            rows = sb.table("orden_pagos_historial").select("*").eq("orden_id", orden_id).order("created_at").execute().data or []
        else:
            rows = [h for h in _HISTORIAL if h["orden_id"] == orden_id]
        return [{**r, "monto": dec(r["monto"]) if r.get("monto") is not None else None} for r in rows]

    # ------------------------------------------------------------------ reembolsos
    def insertar_reembolso(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "created_at": ahora(), "updated_at": ahora(), **row}
        sb = get_supabase_admin_client()
        if sb:
            fila = _json({k: v for k, v in row.items() if k != "created_at"})
            return _norm_reembolso(sb.table("reembolsos").insert(fila).execute().data[0])
        _REEMBOLSOS[row["id"]] = row
        return _norm_reembolso(row)

    def actualizar_reembolso(self, reembolso_id: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        cambios = {**cambios, "updated_at": ahora()}
        sb = get_supabase_admin_client()
        if sb:
            return _norm_reembolso(sb.table("reembolsos").update(_json(cambios)).eq("id", reembolso_id).execute().data[0])
        _REEMBOLSOS[reembolso_id].update(cambios)
        return _norm_reembolso(_REEMBOLSOS[reembolso_id])

    def get_reembolso(self, reembolso_id: str) -> Optional[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            data = sb.table("reembolsos").select("*").eq("id", reembolso_id).limit(1).execute().data
            return _norm_reembolso(data[0]) if data else None
        return _norm_reembolso(_REEMBOLSOS[reembolso_id]) if reembolso_id in _REEMBOLSOS else None

    def listar_reembolsos_de_pago(self, pago_id: str) -> List[Dict[str, Any]]:
        sb = get_supabase_admin_client()
        if sb:
            rows = sb.table("reembolsos").select("*").eq("pago_id", pago_id).execute().data or []
        else:
            rows = [r for r in _REEMBOLSOS.values() if r["pago_id"] == pago_id]
        return [_norm_reembolso(r) for r in rows]

    def listar_reembolsos(
        self, estado: Optional[str], orden_id: Optional[str], pago_id: Optional[str], limite: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        sb = get_supabase_admin_client()
        if sb:
            q = sb.table("reembolsos").select("*", count="exact")
            for col, val in (("estado", estado), ("orden_id", orden_id), ("pago_id", pago_id)):
                if val:
                    q = q.eq(col, val)
            res = q.order("created_at", desc=True).range(offset, offset + limite - 1).execute()
            return [_norm_reembolso(r) for r in res.data or []], res.count or 0
        rows = [
            r for r in _REEMBOLSOS.values()
            if (not estado or r["estado"] == estado) and (not orden_id or r["orden_id"] == orden_id) and (not pago_id or r["pago_id"] == pago_id)
        ]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [_norm_reembolso(r) for r in rows[offset: offset + limite]], len(rows)


repo = PagosRepo()
