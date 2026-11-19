"""
KAN-54 — PagoValidationService: registrar y validar el pago de una orden contra el medio utilizado.

Reglas:
  * Cada pago pasa por ``pendiente`` -> ``aprobado`` | ``rechazado``.
  * Al completar el pago, las órdenes POS pasan a entregadas; los demás canales pasan a confirmadas.
  * Las confirmaciones (webhook) son idempotentes por ``transaccion_id``.
  * Un pago rechazado no hace avanzar la orden y permite reintentar con otro medio.
  * El efectivo solo lo registra un cajero con caja abierta (y suma al efectivo esperado del turno).
  * Cada cambio de estado de pago queda en el historial de la orden (``orden_pagos_historial``).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

try:
    from app.maquina_estados import MaquinaEstados
    from app.pagos_repo import dec, repo
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.maquina_estados import MaquinaEstados
    from backend.services.ordenes.app.pagos_repo import dec, repo

from backend.shared.audit import registrar_audit
from backend.shared.caja_store import acumular_efectivo, obtener_caja_abierta
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.pagos_divididos import METODOS_PAGO_VALIDOS

logger = logging.getLogger("maxiconecta.pagos.validacion")

ESTADOS_FINALES = frozenset({"aprobado", "rechazado", "reembolsado"})
ROLES_STAFF = frozenset({"cajero", "administrador", "gerente_comercial"})
EVENTOS = {
    "pago.aprobado": "aprobado",
    "pago.rechazado": "rechazado",
    "pago.expirado": "rechazado",
}

_locks: Dict[str, asyncio.Lock] = {}


def lock_orden(orden_id: str) -> asyncio.Lock:
    return _locks.setdefault(str(orden_id), asyncio.Lock())


def _uid(user: Dict[str, Any]) -> str:
    return str(user.get("user_id") or user.get("sub") or "")


def _rol(user: Dict[str, Any]) -> str:
    return str(user.get("role", "")).lower()


def cargar_orden_o_404(orden_id: str) -> Dict[str, Any]:
    orden = repo.get_orden(str(orden_id))
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    return orden


def verificar_acceso_orden(orden: Dict[str, Any], user: Dict[str, Any]) -> None:
    """Personal autorizado, o el cliente dueño de la orden."""
    if _rol(user) in ROLES_STAFF:
        return
    if _rol(user) == "cliente" and str(orden["cliente_id"]) == _uid(user):
        return
    raise HTTPException(status_code=403, detail="No tienes acceso a los pagos de esta orden.")


def _totales(orden: Dict[str, Any], pagos: List[Dict[str, Any]]) -> Dict[str, Decimal]:
    aprobado = sum((p["monto"] for p in pagos if p["estado"] in ("aprobado", "reembolsado")), Decimal("0.00"))
    pendiente = sum((p["monto"] for p in pagos if p["estado"] == "pendiente"), Decimal("0.00"))
    return {
        "total": orden["total"],
        "aprobado": aprobado,
        "pendiente": pendiente,
        "saldo": (orden["total"] - aprobado).quantize(Decimal("0.01")),
        "por_cubrir": (orden["total"] - aprobado - pendiente).quantize(Decimal("0.01")),
    }


def resumen(orden_id: str) -> Dict[str, Any]:
    orden = cargar_orden_o_404(orden_id)
    pagos = repo.listar_pagos(str(orden_id))
    t = _totales(orden, pagos)
    return {
        "orden_id": orden["id"],
        "codigo_orden": orden["codigo_orden"],
        "estado_orden": orden["estado"],
        "total": t["total"],
        "total_aprobado": t["aprobado"],
        "total_pendiente": t["pendiente"],
        "saldo_pendiente": t["saldo"],
        "apta_para_preparacion": orden["estado"] in ("confirmada", "en_preparacion", "despachada", "entregada") and t["saldo"] <= 0,
        "pagos": pagos,
        "historial": repo.listar_historial(str(orden_id)),
    }


def _historial(orden_id: str, pago: Optional[Dict[str, Any]], anterior: Optional[str], nuevo: str, usuario_id: str,
               origen: str, motivo: Optional[str] = None, tipo: str = "pago") -> None:
    repo.agregar_historial(
        {
            "orden_id": str(orden_id),
            "pago_id": pago["id"] if pago else None,
            "transaccion_id": pago["transaccion_id"] if pago else None,
            "tipo": tipo,
            "metodo": pago["metodo"] if pago else None,
            "monto": pago["monto"] if pago else None,
            "estado_anterior": anterior,
            "estado_nuevo": nuevo,
            "origen": origen,
            "motivo": motivo,
            "usuario_id": usuario_id or None,
        }
    )


async def _reevaluar_orden(orden_id: str, usuario_id: str) -> Dict[str, Any]:
    """Confirma la orden si los pagos aprobados igualan su total. Debe llamarse con el candado de la orden."""
    orden = cargar_orden_o_404(orden_id)
    t = _totales(orden, repo.listar_pagos(str(orden_id)))
    if orden["estado"] == "pendiente" and t["aprobado"] == orden["total"] and orden["total"] > 0:
        # En caja, el pago completo finaliza la venta presencial. Los demás
        # canales conservan la preparación y el despacho posteriores al pago.
        nuevo_estado = "entregada" if orden.get("canal") == "pos" else "confirmada"
        if nuevo_estado == "confirmada":
            MaquinaEstados.validar("pendiente", nuevo_estado)
        if not repo.set_orden_estado(str(orden_id), "pendiente", nuevo_estado, usuario_id):
            raise HTTPException(status_code=409, detail="La orden cambió de estado mientras se validaba el pago. Reintenta.")
        _historial(orden_id, None, "pendiente", nuevo_estado, usuario_id, "sistema", "Pagos aprobados igualan el total", tipo="orden")
        await registrar_audit("ORDEN_ENTREGADA_POR_PAGO" if nuevo_estado == "entregada" else "ORDEN_CONFIRMADA_POR_PAGO", "ordenes", orden_id, {"user_id": usuario_id, "role": "sistema"},
                              before={"estado": "pendiente"}, after={"estado": nuevo_estado, "total": orden["total"]})
        orden["estado"] = nuevo_estado
    return orden


async def registrar_pago(
    orden_id: str,
    metodo: str,
    monto: Decimal,
    usuario: Dict[str, Any],
    referencia: Optional[str] = None,
    monto_recibido: Optional[Decimal] = None,
    transaccion_id: Optional[str] = None,
    reintento_de: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool, Dict[str, Any]]:
    """Devuelve (pago, duplicado, extra) donde ``extra`` trae token/QR/URL de pasarela y el cambio en efectivo."""
    metodo = (metodo or "").strip().lower()
    if metodo not in METODOS_PAGO_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Método de pago no soportado: {metodo}.")
    monto = dec(monto)
    if monto <= 0:
        raise HTTPException(status_code=422, detail="El monto debe ser mayor a 0.")

    orden = cargar_orden_o_404(orden_id)
    rol = _rol(usuario)
    if rol == "cliente":
        if str(orden["cliente_id"]) != _uid(usuario):
            raise HTTPException(status_code=403, detail="La orden pertenece a otro cliente.")
        if metodo == "efectivo":
            raise HTTPException(status_code=403, detail="El pago en efectivo solo puede registrarlo un cajero.")
    elif rol not in ROLES_STAFF:
        raise HTTPException(status_code=403, detail="Rol sin permiso para registrar pagos.")

    extra: Dict[str, Any] = {"cambio": Decimal("0.00")}
    async with lock_orden(orden_id):
        orden = cargar_orden_o_404(orden_id)
        if transaccion_id:
            previo = repo.get_pago_por_tx(transaccion_id)
            if previo:
                if str(previo["orden_id"]) == str(orden_id) and previo["metodo"] == metodo and previo["monto"] == monto:
                    return previo, True, extra
                raise HTTPException(status_code=409, detail="El transaccion_id ya fue usado en otro pago.")
        if orden["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail=f"La orden está '{orden['estado']}': solo las órdenes pendientes aceptan pagos.")

        pagos = repo.listar_pagos(str(orden_id))
        t = _totales(orden, pagos)
        if monto > t["por_cubrir"]:
            raise HTTPException(
                status_code=422,
                detail=f"El monto Bs. {monto} excede lo que falta cubrir de la orden (Bs. {max(t['por_cubrir'], Decimal('0.00'))}).",
            )

        intento = 1
        if reintento_de:
            previo = repo.get_pago(reintento_de)
            if not previo or str(previo["orden_id"]) != str(orden_id) or previo["estado"] != "rechazado":
                raise HTTPException(status_code=422, detail="Solo se puede reintentar un pago rechazado de la misma orden.")
            intento = previo["intento"] + 1

        tx = transaccion_id or f"TX-PAG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        fila: Dict[str, Any] = {
            "orden_id": str(orden_id), "transaccion_id": tx, "metodo": metodo, "monto": monto, "moneda": "BOB",
            "referencia": referencia, "registrado_por": _uid(usuario), "intento": intento,
            "raw_payload": {"reintento_de": reintento_de, "origen": "caja" if metodo == "efectivo" else "pasarela"},
        }
        caja = None
        if metodo == "efectivo":
            caja = await obtener_caja_abierta(_uid(usuario))
            if not caja:
                raise HTTPException(status_code=403, detail="El pago en efectivo solo puede registrarse con una caja abierta.")
            if monto_recibido is not None:
                if dec(monto_recibido) < monto:
                    raise HTTPException(status_code=422, detail="El monto recibido es menor al monto del pago.")
                extra["cambio"] = dec(monto_recibido) - monto
            fila.update(estado="aprobado", caja_turno_id=str(caja["id"]), codigo_autorizacion=f"CAJA-{uuid.uuid4().hex[:6].upper()}")
        else:
            erp = await pagos_client.procesar_cobro(
                monto=float(monto), metodo=metodo, transaccion_id=tx, metadata={"orden_id": str(orden_id), "origen": "kan-54"}
            )
            fila.update(estado="pendiente", token_pago=erp.get("token_pago"))
            fila["raw_payload"].update(qr_payload=erp.get("qr_payload"), redirect_url=erp.get("redirect_url"))
            extra.update(token_pago=erp.get("token_pago"), qr_payload=erp.get("qr_payload"), redirect_url=erp.get("redirect_url"))

        pago = repo.insertar_pago(fila)
        _historial(orden_id, pago, None, pago["estado"], _uid(usuario), "cajero" if rol != "cliente" else "cliente",
                   "Reintento de pago" if reintento_de else "Pago registrado")
        if metodo == "efectivo" and caja:
            await acumular_efectivo(str(caja["id"]), monto)
        await registrar_audit("PAGO_REGISTRADO", "pagos", pago["id"], usuario, after={k: pago[k] for k in ("orden_id", "metodo", "monto", "estado", "transaccion_id")})
        await _reevaluar_orden(orden_id, _uid(usuario))
    return repo.get_pago(pago["id"]), False, extra


async def procesar_webhook(
    pago: Dict[str, Any],
    evento: str,
    monto: Optional[Decimal],
    codigo_autorizacion: Optional[str],
    motivo_rechazo: Optional[str],
) -> Dict[str, Any]:
    """Aplica una confirmación de la pasarela. Idempotente: repetir el aviso no duplica ni cambia nada."""
    nuevo = EVENTOS.get((evento or "").lower().strip())
    orden_id = str(pago["orden_id"])
    if nuevo is None:
        return {"recibido": True, "transaccion_id": pago["transaccion_id"], "duplicado": False, "ignorado": True,
                "estado_pago": pago["estado"], "mensaje": "Evento sin cambio de estado."}
    async with lock_orden(orden_id):
        actual = repo.get_pago(pago["id"])
        if actual["estado"] in ESTADOS_FINALES:
            logger.info("Webhook repetido/tardío para %s (estado %s): sin cambios", actual["transaccion_id"], actual["estado"])
            return {
                "recibido": True, "transaccion_id": actual["transaccion_id"], "duplicado": True,
                "conflicto": actual["estado"] != nuevo and not (actual["estado"] == "reembolsado" and nuevo == "aprobado"),
                "estado_pago": actual["estado"], "mensaje": "Confirmación ya procesada; no se modificó el pago.",
            }
        if monto is not None and dec(monto) != actual["monto"]:
            raise HTTPException(status_code=422, detail="El monto del aviso no coincide con el monto del pago.")
        cambios: Dict[str, Any] = {"estado": nuevo}
        if nuevo == "aprobado":
            cambios["codigo_autorizacion"] = codigo_autorizacion or f"AUTH-{uuid.uuid4().hex[:6].upper()}"
        else:
            cambios["motivo_rechazo"] = motivo_rechazo or "Rechazado por la pasarela"
        actualizado = repo.actualizar_pago(actual["id"], cambios)
        _historial(orden_id, actualizado, "pendiente", nuevo, "", "webhook", cambios.get("motivo_rechazo"))
        await registrar_audit("PAGO_" + nuevo.upper(), "pagos", actual["id"], {"role": "pasarela"},
                              before={"estado": "pendiente"}, after={"estado": nuevo, "orden_id": orden_id})
        orden = await _reevaluar_orden(orden_id, "")
    return {
        "recibido": True, "transaccion_id": actual["transaccion_id"], "duplicado": False, "estado_pago": nuevo,
        "estado_orden": orden["estado"], "mensaje": f"Pago {nuevo}.",
    }
