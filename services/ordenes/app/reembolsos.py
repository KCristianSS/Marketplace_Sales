"""
KAN-55 — ReembolsoService: reembolsos totales o parciales de pagos aprobados.

Reglas:
  * Estados: solicitado -> procesando -> completado | fallido (el fallido puede reintentarse).
  * Un reembolso no puede exceder lo pagado menos los reembolsos previos (saldo reembolsable).
  * En pagos divididos el reembolso se aplica por tramo y por medio de pago (cada tramo es un ``pago``).
  * Reembolso completado: se notifica a Contabilidad (simulado) y se registra en audit_logs.
  * Reembolso de un pago en efectivo: genera comprobante de egreso de caja.
  * La reversión usa PagosClient (integración simulada).
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

try:
    from app.pagos_repo import dec, repo
    from app.pagos_validacion import _historial, lock_orden
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.pagos_repo import dec, repo
    from backend.services.ordenes.app.pagos_validacion import _historial, lock_orden

from backend.shared.audit import registrar_audit
from backend.shared.config import settings
from backend.shared.erp_clients.contabilidad import contabilidad_client
from backend.shared.erp_clients.pagos import pagos_client

logger = logging.getLogger("maxiconecta.reembolsos")

ESTADOS_QUE_CONSUMEN_SALDO = ("solicitado", "procesando", "completado")


def _uid(user: Dict[str, Any]) -> str:
    return str(user.get("user_id") or user.get("sub") or "")


def saldo_reembolsable(pago: Dict[str, Any]) -> Decimal:
    """Monto pagado menos los reembolsos vigentes (en curso o completados)."""
    if str(pago.get("metodo", "")).lower() == "vale":
        return Decimal("0.00")
    if pago["estado"] not in ("aprobado", "reembolsado"):
        return Decimal("0.00")
    usados = sum((r["monto"] for r in repo.listar_reembolsos_de_pago(pago["id"]) if r["estado"] in ESTADOS_QUE_CONSUMEN_SALDO), Decimal("0.00"))
    return max(pago["monto"] - usados, Decimal("0.00"))


def _comprobante_egreso(reembolso: Dict[str, Any], pago: Dict[str, Any], orden: Dict[str, Any], usuario: Dict[str, Any]) -> Dict[str, Any]:
    ahora = datetime.now(timezone.utc)
    return {
        "numero": f"CE-{ahora.strftime('%Y%m%d')}-{str(reembolso['id']).replace('-', '')[:6].upper()}",
        "tipo": "egreso_caja_reembolso",
        "monto": str(reembolso["monto"]),
        "metodo": "efectivo",
        "orden_id": str(orden["id"]),
        "codigo_orden": orden["codigo_orden"],
        "pago_id": pago["id"],
        "motivo": reembolso["motivo"],
        "autorizado_por": _uid(usuario),
        "fecha": ahora.isoformat(),
    }


async def _ejecutar(reembolso: Dict[str, Any], usuario: Dict[str, Any], simular_fallo: bool) -> Dict[str, Any]:
    """Procesa un reembolso 'solicitado'. Debe llamarse con el candado de la orden tomado."""
    pago = repo.get_pago(reembolso["pago_id"])
    orden = repo.get_orden(str(reembolso["orden_id"])) or {"id": reembolso["orden_id"], "codigo_orden": "-"}
    reembolso = repo.actualizar_reembolso(reembolso["id"], {"estado": "procesando"})
    _historial(reembolso["orden_id"], pago, "reembolso:solicitado", "reembolso:procesando", _uid(usuario), "administrador",
               f"Reembolso Bs. {reembolso['monto']}", tipo="reembolso")
    try:
        res = await pagos_client.reembolsar_cobro(
            pago["transaccion_id"], float(reembolso["monto"]), pago["metodo"], reembolso["motivo"],
            simular_fallo=simular_fallo and settings.ENVIRONMENT != "production",
        )
    except Exception as exc:  # error inesperado de la integración: queda 'fallido' y reintentable
        logger.exception("Reembolso %s: fallo inesperado de PagosClient", reembolso["id"])
        res = {"estado": "fallido", "motivo": f"Error de integración: {exc}"}

    if res.get("estado") != "completado":
        reembolso = repo.actualizar_reembolso(reembolso["id"], {"estado": "fallido", "error": res.get("motivo") or "Reembolso rechazado por la pasarela"})
        _historial(reembolso["orden_id"], pago, "reembolso:procesando", "reembolso:fallido", _uid(usuario), "administrador", reembolso["error"], tipo="reembolso")
        await registrar_audit("REEMBOLSO_FALLIDO", "reembolsos", reembolso["id"], usuario, after={"estado": "fallido", "error": reembolso["error"], "monto": reembolso["monto"]})
        return reembolso

    cambios: Dict[str, Any] = {
        "estado": "completado", "error": None, "completed_at": datetime.now(timezone.utc).isoformat(),
        "referencia_externa": res.get("reembolso_ref"), "nota_credito": res.get("nota_credito"),
    }
    if pago["metodo"] == "efectivo":
        comp = _comprobante_egreso(reembolso, pago, orden, usuario)
        cambios.update(comprobante=comp, numero_comprobante=comp["numero"])
    reembolso = repo.actualizar_reembolso(reembolso["id"], cambios)

    nuevo_total = pago["monto_reembolsado"] + reembolso["monto"]
    cambios_pago: Dict[str, Any] = {"monto_reembolsado": nuevo_total}
    if nuevo_total >= pago["monto"]:
        cambios_pago["estado"] = "reembolsado"
    repo.actualizar_pago(pago["id"], cambios_pago)
    _historial(reembolso["orden_id"], pago, "reembolso:procesando", "reembolso:completado", _uid(usuario), "administrador",
               "Pago reembolsado totalmente" if "estado" in cambios_pago else "Reembolso parcial", tipo="reembolso")

    try:
        notif = await contabilidad_client.registrar_reembolso({
            "reembolso_id": reembolso["id"], "orden_id": str(reembolso["orden_id"]), "pago_id": pago["id"],
            "metodo": pago["metodo"], "monto": str(reembolso["monto"]), "motivo": reembolso["motivo"],
            "nota_credito": reembolso.get("nota_credito"),
        })
    except Exception as exc:
        logger.exception("No se pudo notificar el reembolso %s a Contabilidad", reembolso["id"])
        notif = {"estado": "pendiente_reintento", "error": str(exc)}
    reembolso = repo.actualizar_reembolso(reembolso["id"], {"contabilidad": notif})
    await registrar_audit("REEMBOLSO_COMPLETADO", "reembolsos", reembolso["id"], usuario,
                          before={"monto_reembolsado": pago["monto_reembolsado"]},
                          after={"estado": "completado", "monto": reembolso["monto"], "metodo": pago["metodo"],
                                 "orden_id": str(reembolso["orden_id"]), "pago_id": pago["id"], "contabilidad": notif})
    return reembolso


def _crear_fila(pago: Dict[str, Any], monto: Decimal, motivo: str, usuario: Dict[str, Any]) -> Dict[str, Any]:
    return repo.insertar_reembolso({
        "pago_id": pago["id"], "orden_id": str(pago["orden_id"]), "metodo": pago["metodo"], "monto": monto,
        "motivo": motivo, "estado": "solicitado", "intento": 1, "solicitado_por": _uid(usuario),
    })


async def solicitar(
    pago_id: Optional[str], orden_id: Optional[str], monto: Optional[Decimal], motivo: str,
    usuario: Dict[str, Any], simular_fallo: bool = False,
) -> List[Dict[str, Any]]:
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise HTTPException(status_code=422, detail="El motivo del reembolso es obligatorio.")
    if bool(pago_id) == bool(orden_id):
        raise HTTPException(status_code=422, detail="Indica pago_id (un tramo) u orden_id (todos los tramos), no ambos.")
    if monto is not None and dec(monto) <= 0:
        raise HTTPException(status_code=422, detail="El monto debe ser mayor a 0.")

    if pago_id:
        pago = repo.get_pago(pago_id)
        if not pago:
            raise HTTPException(status_code=404, detail="Pago no encontrado.")
        orden_id = str(pago["orden_id"])
    elif not repo.get_orden(orden_id):
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    async with lock_orden(orden_id):
        if pago_id:
            pago = repo.get_pago(pago_id)
            if str(pago.get("metodo", "")).lower() == "vale":
                raise HTTPException(status_code=422, detail="Los reembolsos a vales no están disponibles.")
            if pago["estado"] not in ("aprobado", "reembolsado"):
                raise HTTPException(status_code=409, detail=f"Solo se reembolsan pagos aprobados (estado actual: {pago['estado']}).")
            saldo = saldo_reembolsable(pago)
            pedido = dec(monto) if monto is not None else saldo
            if pedido > saldo:
                raise HTTPException(status_code=422, detail=f"El reembolso (Bs. {pedido}) excede el saldo reembolsable del pago (Bs. {saldo}).")
            if pedido <= 0:
                raise HTTPException(status_code=422, detail="El pago ya no tiene saldo reembolsable.")
            asignaciones = [(pago, pedido)]
        else:
            # Pago dividido: se asigna por tramo, del último al primero, respetando el saldo de cada tramo/medio.
            tramos = [p for p in repo.listar_pagos(orden_id) if p["estado"] in ("aprobado", "reembolsado") and str(p.get("metodo", "")).lower() != "vale"]
            if not tramos:
                raise HTTPException(status_code=409, detail="La orden no tiene pagos aprobados para reembolsar.")
            tramos.sort(key=lambda p: p["created_at"], reverse=True)
            disponible = sum((saldo_reembolsable(p) for p in tramos), Decimal("0.00"))
            pedido = dec(monto) if monto is not None else disponible
            if pedido > disponible:
                raise HTTPException(status_code=422, detail=f"El reembolso (Bs. {pedido}) excede el saldo reembolsable de la orden (Bs. {disponible}).")
            if pedido <= 0:
                raise HTTPException(status_code=422, detail="La orden ya no tiene saldo reembolsable.")
            asignaciones, restante = [], pedido
            for t in tramos:
                if restante <= 0:
                    break
                parte = min(saldo_reembolsable(t), restante)
                if parte > 0:
                    asignaciones.append((t, parte))
                    restante -= parte

        filas = [_crear_fila(p, m, motivo, usuario) for p, m in asignaciones]
        for f, (p, _) in zip(filas, asignaciones):
            _historial(orden_id, p, None, "reembolso:solicitado", _uid(usuario), "administrador", motivo, tipo="reembolso")
        return [await _ejecutar(f, usuario, simular_fallo) for f in filas]


async def reintentar(reembolso_id: str, usuario: Dict[str, Any], simular_fallo: bool = False) -> Dict[str, Any]:
    r = repo.get_reembolso(reembolso_id)
    if not r:
        raise HTTPException(status_code=404, detail="Reembolso no encontrado.")
    async with lock_orden(str(r["orden_id"])):
        r = repo.get_reembolso(reembolso_id)
        if r["estado"] != "fallido":
            raise HTTPException(status_code=409, detail=f"Solo se reintentan reembolsos fallidos (estado actual: {r['estado']}).")
        pago = repo.get_pago(r["pago_id"])
        if str(pago.get("metodo", "")).lower() == "vale":
            raise HTTPException(status_code=422, detail="Los reembolsos a vales no están disponibles.")
        if r["monto"] > saldo_reembolsable(pago):
            raise HTTPException(status_code=422, detail="El saldo reembolsable del pago cambió: ya no alcanza para este reembolso.")
        r = repo.actualizar_reembolso(reembolso_id, {"estado": "solicitado", "intento": r["intento"] + 1, "error": None})
        return await _ejecutar(r, usuario, simular_fallo)
