"""
Pago dividido (varios métodos de pago en una misma venta) y evento
``OrderPaidEvent`` hacia Contabilidad con el desglose por forma de pago.

Lo usan el POS (cobro en caja), la facturación POS y la creación de órdenes web,
de modo que la validación y el formato del evento sean idénticos en todos.
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.shared.erp_clients.contabilidad import contabilidad_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.saga import SagaOrchestrator

logger = logging.getLogger("maxiconecta.pagos")

# Subconjunto de metodo_pago_enum (db/schema.sql) habilitado para cobrar.
METODOS_PAGO_VALIDOS = ("efectivo", "tarjeta", "qr", "transferencia", "pasarela")
METODOS_DIGITALES = frozenset({"tarjeta", "qr", "transferencia", "pasarela"})  # requieren autorización externa
MAX_TRANSACCIONES_POR_VENTA = 6
_CENTAVO = Decimal("0.01")


def redondear(monto: Any) -> Decimal:
    return Decimal(str(monto)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


class PagoParcial(BaseModel):
    """Una transacción de pago dentro de una venta (un 'tramo' del pago dividido)."""
    metodo: str = Field(..., description="efectivo | tarjeta | qr | transferencia | pasarela")
    monto: Decimal = Field(..., gt=0)
    referencia: Optional[str] = Field(default=None, max_length=60, description="Últimos 4 dígitos, nº de voucher, etc.")
    monto_recibido: Optional[Decimal] = Field(
        default=None, gt=0, description="Solo efectivo: billete entregado por el cliente (para calcular el cambio)"
    )

    @field_validator("metodo")
    @classmethod
    def _metodo_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in METODOS_PAGO_VALIDOS:
            raise ValueError(f"Método de pago no soportado: {v}. Use: {', '.join(METODOS_PAGO_VALIDOS)}")
        return v


class PagoProcesado(BaseModel):
    """Resultado de procesar un tramo de pago."""
    metodo: str
    monto: Decimal
    estado: str = "aprobado"
    transaccion_id: Optional[str] = None
    referencia: Optional[str] = None
    cambio: Decimal = Decimal("0.00")


class PagoInvalidoError(ValueError):
    """La lista de pagos no es coherente con el total de la venta."""


def normalizar_pagos(
    pagos: Optional[List[PagoParcial]],
    metodo_pago_unico: str,
    total: Decimal,
) -> List[PagoParcial]:
    """
    Devuelve la lista definitiva de pagos de la venta.

    * Sin ``pagos``: compatibilidad hacia atrás, un único tramo por el total con ``metodo_pago_unico``.
    * Con ``pagos``: la suma debe igualar exactamente el total (a 2 decimales).
    """
    total = redondear(total)
    if not pagos:
        metodo = (metodo_pago_unico or "efectivo").strip().lower()
        if metodo not in METODOS_PAGO_VALIDOS:
            metodo = "efectivo"
        return [PagoParcial(metodo=metodo, monto=total)] if total > 0 else []

    if len(pagos) > MAX_TRANSACCIONES_POR_VENTA:
        raise PagoInvalidoError(f"Una venta admite como máximo {MAX_TRANSACCIONES_POR_VENTA} transacciones de pago.")

    normalizados: List[PagoParcial] = []
    for pago in pagos:
        monto = redondear(pago.monto)
        if monto <= 0:
            raise PagoInvalidoError("Cada transacción de pago debe tener un monto mayor a cero.")
        recibido = redondear(pago.monto_recibido) if pago.monto_recibido is not None else None
        if pago.metodo == "efectivo" and recibido is not None and recibido < monto:
            raise PagoInvalidoError(
                f"El efectivo recibido (Bs. {recibido}) es menor al monto asignado a efectivo (Bs. {monto})."
            )
        normalizados.append(PagoParcial(
            metodo=pago.metodo,
            monto=monto,
            referencia=pago.referencia,
            monto_recibido=recibido if pago.metodo == "efectivo" else None,
        ))

    suma = sum((p.monto for p in normalizados), Decimal("0.00"))
    if suma != total:
        diferencia = redondear(total - suma)
        if diferencia > 0:
            raise PagoInvalidoError(
                f"El pago está incompleto: faltan Bs. {diferencia} (pagos Bs. {suma} de un total de Bs. {total})."
            )
        raise PagoInvalidoError(
            f"Los pagos exceden el total: sobran Bs. {abs(diferencia)} (pagos Bs. {suma} de un total de Bs. {total})."
        )
    return normalizados


def desglose_por_metodo(pagos: List[Any]) -> Dict[str, Decimal]:
    """Suma los montos agrupados por método (acepta PagoParcial o PagoProcesado)."""
    resumen: Dict[str, Decimal] = {}
    for pago in pagos:
        resumen[pago.metodo] = redondear(resumen.get(pago.metodo, Decimal("0")) + pago.monto)
    return resumen


def metodo_resumen(pagos: List[Any]) -> str:
    """'efectivo' si hay un solo método; 'mixto' si se combinaron varios."""
    metodos = {p.metodo for p in pagos}
    return next(iter(metodos)) if len(metodos) == 1 else "mixto"


def construir_order_paid_event(
    *,
    orden_id: str,
    canal: str,
    total: Decimal,
    pagos: List[PagoProcesado],
    codigo_orden: Optional[str] = None,
    sucursal_id: Optional[str] = None,
    cuf: Optional[str] = None,
    numero_factura: Optional[int] = None,
    moneda: str = "BOB",
) -> Dict[str, Any]:
    """
    Evento ``OrderPaidEvent`` para Contabilidad (RIO-CON-01). Conserva los campos
    históricos (``orden_id``, ``monto_total``, ``canal``) y agrega el desglose
    de formas de pago para que el asiento se separe por cuenta (caja, banco, QR).
    """
    return {
        "evento": "OrderPaidEvent",
        "evento_id": f"evt-{uuid.uuid4().hex[:12]}",
        "ocurrido_en": datetime.now(timezone.utc).isoformat(),
        "orden_id": str(orden_id),
        "codigo_orden": codigo_orden,
        "canal": canal,
        "sucursal_id": str(sucursal_id) if sucursal_id else None,
        "moneda": moneda,
        "monto_total": float(redondear(total)),
        "cuf_factura": cuf,
        "numero_factura": numero_factura,
        "pago_mixto": len({p.metodo for p in pagos}) > 1,
        "desglose_pagos": [
            {
                "metodo": p.metodo,
                "monto": float(redondear(p.monto)),
                "transaccion_id": p.transaccion_id,
                "referencia": p.referencia,
                "estado": p.estado,
            }
            for p in pagos
        ],
        "totales_por_metodo": {m: float(v) for m, v in desglose_por_metodo(pagos).items()},
    }


async def publicar_order_paid_event(evento: Dict[str, Any]) -> Dict[str, Any]:
    """
    Envía el evento a Contabilidad (integración simulada). Nunca interrumpe la
    venta ya cobrada: si Contabilidad falla, se registra para reintento.
    """
    try:
        respuesta = await contabilidad_client.registrar_asiento_venta(evento)
        logger.info("OrderPaidEvent %s publicado a Contabilidad: %s", evento.get("evento_id"), respuesta)
        return {"publicado": True, "respuesta": respuesta}
    except Exception as exc:  # noqa: BLE001
        logger.error("No se pudo publicar OrderPaidEvent %s: %s (pendiente de reintento)", evento.get("evento_id"), exc)
        return {"publicado": False, "error": str(exc), "estado": "pendiente_reintento"}


def agregar_pasos_de_cobro(
    saga: SagaOrchestrator,
    pagos: List[PagoParcial],
    procesados: List[PagoProcesado],
    moneda: str = "BOB",
) -> None:
    """
    Agrega a la saga un paso por cada tramo de pago. Los tramos digitales
    (tarjeta, QR, transferencia, pasarela) se autorizan en el ERP de Pagos
    (RIO-PAG-01) y se reversan (RIO-PAG-03) si un paso posterior falla; el
    efectivo se registra localmente (no hay autorización externa). Primero se
    autorizan los digitales y al final se registra el efectivo, para no recibir
    billetes de una venta cuyo pago con tarjeta/QR luego sería rechazado.

    Cada tramo aprobado se agrega a ``procesados`` (con su transaccion_id).
    """
    ordenados = sorted(pagos, key=lambda p: 0 if p.metodo in METODOS_DIGITALES else 1)
    for indice, pago in enumerate(ordenados, start=1):
        nombre = f"cobro_{indice}_{pago.metodo}"

        def _crear_accion(tramo: PagoParcial):
            async def accion() -> Dict[str, Any]:
                if tramo.metodo in METODOS_DIGITALES:
                    res = await pagos_client.procesar_cobro(float(tramo.monto), tramo.metodo, moneda)
                else:
                    res = {"transaccion_id": f"EF-{uuid.uuid4().hex[:10]}", "estado": "aprobado"}
                estado = str(res.get("estado") or res.get("status") or "aprobado").lower()
                if estado in ("aprobado", "aprobada", "ok", "approved"):
                    cambio = Decimal("0.00")
                    if tramo.metodo == "efectivo" and tramo.monto_recibido is not None:
                        cambio = redondear(tramo.monto_recibido - tramo.monto)
                    procesados.append(PagoProcesado(
                        metodo=tramo.metodo,
                        monto=tramo.monto,
                        estado="aprobado",
                        transaccion_id=res.get("transaccion_id"),
                        referencia=tramo.referencia,
                        cambio=cambio,
                    ))
                    return {**res, "estado": "aprobado", "monto": float(tramo.monto), "metodo": tramo.metodo}
                return {**res, "estado": "rechazado", "mensaje": res.get("mensaje") or f"Pago {tramo.metodo} rechazado"}
            return accion

        def _crear_compensacion(tramo: PagoParcial):
            async def compensacion(resultado: Dict[str, Any]) -> None:
                # El tramo ya no forma parte de la venta: se quita de los procesados y se reversa en el ERP.
                procesados[:] = [p for p in procesados if p.transaccion_id != resultado.get("transaccion_id")]
                if tramo.metodo in METODOS_DIGITALES:
                    await pagos_client.reversar_cobro(str(resultado.get("transaccion_id")), float(tramo.monto))
            return compensacion

        saga.paso(nombre, _crear_accion(pago), _crear_compensacion(pago))
