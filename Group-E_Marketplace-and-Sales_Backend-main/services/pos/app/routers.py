"""
Endpoints REST del microservicio POS — Puntos de Venta Físicos (RF-09 a RF-12).

Gestión de caja por turno: apertura, control de movimientos, cierre con
arqueo y procesamiento de ventas presenciales.
"""

import base64
import io
import logging
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import qrcode
from qrcode.image.svg import SvgPathImage
from fastapi import APIRouter, Depends, HTTPException, Query, status

try:
    from app.schemas import (
        AbrirCajaRequest,
        ArqueoCajaResponse,
        CajaResponse,
        CerrarCajaRequest,
        ItemTicketPOS,
        MovimientoCajaRequest,
        MovimientoCajaResponse,
        VentaPOSRequest,
        VentaPOSResponse,
        VentaPOSReciente,
        TicketReimpresionResponse,
        VentaSuspendida,
        ValidarRetiroRequest,
        DetalleItemRetiro,
        AuditoriaDespachoInfo,
        PedidoRetiroResponse,
        ConfirmarEntregaRequest,
        ConfirmarEntregaResponse,
    )
    from app.services import (
        abrir_turno,
        acumular_venta,
        cerrar_turno,
        listar_movimientos,
        obtener_caja,
        obtener_caja_activa,
        obtener_historial,
        registrar_movimiento,
    )
except (ModuleNotFoundError, ImportError):
    from backend.services.pos.app.schemas import (
        AbrirCajaRequest,
        ArqueoCajaResponse,
        CajaResponse,
        CerrarCajaRequest,
        ItemTicketPOS,
        MovimientoCajaRequest,
        MovimientoCajaResponse,
        VentaPOSRequest,
        VentaPOSResponse,
        VentaPOSReciente,
        TicketReimpresionResponse,
        VentaSuspendida,
        ValidarRetiroRequest,
        DetalleItemRetiro,
        AuditoriaDespachoInfo,
        PedidoRetiroResponse,
        ConfirmarEntregaRequest,
        ConfirmarEntregaResponse,
    )
    from backend.services.pos.app.services import (
        abrir_turno,
        acumular_venta,
        cerrar_turno,
        listar_movimientos,
        obtener_caja,
        obtener_caja_activa,
        obtener_historial,
        registrar_movimiento,
    )

from backend.shared.database import get_supabase_admin_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.erp_clients.inventarios import inventarios_client
from backend.shared.pagos_divididos import (
    PagoInvalidoError, PagoProcesado, normalizar_pagos, metodo_resumen,
    agregar_pasos_de_cobro, construir_order_paid_event, publicar_order_paid_event,
)
from backend.shared.saga import SagaOrchestrator
from backend.shared.security import get_current_user, require_jwt_claims
from backend.shared.redis_client import (
    save_suspended_sale,
    get_suspended_sale,
    list_suspended_sales,
    delete_suspended_sale,
)

router = APIRouter(prefix="/api/v1/pos", tags=["Punto de Venta"])
logger = logging.getLogger("maxiconecta.pos.reimpresion")
_VENTAS_POS_EN_MEMORIA: Dict[str, Dict[str, Any]] = {}
_AUDITORIA_REIMPRESIONES_EN_MEMORIA: List[Dict[str, Any]] = []

logger = logging.getLogger("maxiconecta.pos")
_IVA_RATE = Decimal("0.13")


def _qr_data_url(payload: str) -> str:
    image = qrcode.make(payload, image_factory=SvgPathImage, box_size=5, border=3)
    output = io.BytesIO()
    image.save(output)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _es_administrador(current_user: Dict[str, Any]) -> bool:
    return str(current_user.get("role", "")).lower() == "administrador"


def _validar_acceso_venta(caja: Dict[str, Any], current_user: Dict[str, Any]) -> None:
    if not _es_administrador(current_user) and str(caja.get("cajero_id")) != str(current_user.get("user_id")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La venta pertenece a otro cajero.")


async def _guardar_ticket_pos(
    ticket: VentaPOSResponse,
    caja_id: str,
    cajero_id: str,
    sucursal_id: str,
) -> None:
    row = {
        "orden_id": str(ticket.orden_id),
        "codigo_orden": ticket.codigo_orden,
        "caja_turno_id": caja_id,
        "cajero_id": cajero_id,
        "sucursal_id": sucursal_id,
        "total": float(ticket.total),
        "ticket": ticket.model_dump(mode="json"),
    }
    _VENTAS_POS_EN_MEMORIA[row["orden_id"]] = {**row, "created_at": datetime.now().astimezone().isoformat()}
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            supabase.table("pos_ventas").insert(row).execute()
        except Exception:
            logger.exception("No se pudo persistir el ticket POS %s para reimpresión", row["orden_id"])


async def _listar_ventas_pos(caja_id: str, limit: int) -> List[Dict[str, Any]]:
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            result = (
                supabase.table("pos_ventas")
                .select("orden_id,codigo_orden,caja_turno_id,cajero_id,sucursal_id,total,ticket,created_at")
                .eq("caja_turno_id", caja_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            logger.exception("No se pudieron consultar los tickets POS del turno %s", caja_id)
    rows = [row for row in _VENTAS_POS_EN_MEMORIA.values() if row["caja_turno_id"] == caja_id]
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)[:limit]


async def _registrar_reimpresion(venta: Dict[str, Any], cajero_id: str) -> None:
    row = {
        "orden_id": venta["orden_id"],
        "caja_turno_id": venta["caja_turno_id"],
        "cajero_id": cajero_id,
    }
    _AUDITORIA_REIMPRESIONES_EN_MEMORIA.append({**row, "created_at": datetime.now().astimezone().isoformat()})
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            supabase.table("pos_ticket_reimpresiones").insert(row).execute()
        except Exception:
            logger.exception("No se pudo registrar la reimpresión del ticket POS %s", venta["orden_id"])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo registrar la auditoría. Intenta reimprimir nuevamente.",
            )


# =====================================================================
# RF-09 — APERTURA DE CAJA
# =====================================================================

@router.post(
    "/caja/abrir",
    response_model=CajaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aperturar turno de caja",
    description="Abre un nuevo turno de caja con fondo inicial. "
                "Un cajero no puede tener dos cajas abiertas simultáneamente.",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def abrir_caja(
    payload: AbrirCajaRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    cajero_id = str(payload.cajero_id or current_user.get("user_id"))
    try:
        caja = await abrir_turno(
            sucursal_id=str(payload.sucursal_id),
            cajero_id=cajero_id,
            fondo_inicial=payload.fondo_inicial,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return CajaResponse(
        id=caja["id"],
        sucursal_id=caja["sucursal_id"],
        cajero_id=caja["cajero_id"],
        fondo_inicial=caja["fondo_inicial"],
        total_efectivo=caja.get("total_efectivo", 0),
        total_tarjeta=caja.get("total_tarjeta", 0),
        total_qr=caja.get("total_qr", 0),
        estado=caja["estado"],
        opened_at=caja.get("opened_at"),
    )


# =====================================================================
# RF-09 — CONSULTAR CAJA ACTIVA DEL CAJERO
# =====================================================================

@router.get(
    "/caja/activa",
    response_model=CajaResponse,
    summary="Obtener la caja activa del cajero",
    description="Retorna la caja abierta del cajero autenticado.",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def obtener_mi_caja_activa(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-09: Consultar caja activa del usuario autenticado."""
    cajero_id = current_user.get("user_id")
    caja = await obtener_caja_activa(cajero_id)
    if not caja:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tiene una caja abierta en este momento.",
        )
    return CajaResponse(**{k: caja[k] for k in CajaResponse.model_fields if k in caja})


# =====================================================================
# RF-09 — CONSULTAR CAJA POR ID
# =====================================================================

@router.get(
    "/caja/{caja_id}",
    response_model=CajaResponse,
    summary="Obtener detalle de una caja por ID",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def obtener_detalle_caja(
    caja_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-09: Detalle de una caja por su identificador."""
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Caja no encontrada.",
        )
    return CajaResponse(**{k: caja[k] for k in CajaResponse.model_fields if k in caja})


# =====================================================================
# RF-09 — REGISTRAR MOVIMIENTO MANUAL (INGRESO / EGRESO)
# =====================================================================

@router.post(
    "/caja/{caja_id}/movimiento",
    response_model=MovimientoCajaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar movimiento manual de caja",
    description="Registra un ingreso o egreso manual (ej. retiro de efectivo, "
                "ingreso de cambio). Solo en cajas abiertas.",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def crear_movimiento_caja(
    caja_id: str,
    payload: MovimientoCajaRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-09: Ingreso/egreso manual en la caja abierta."""
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    if caja["estado"] != "abierta":
        raise HTTPException(status_code=403, detail="La caja no está abierta.")

    mov = await registrar_movimiento(
        caja_id=caja_id,
        tipo=payload.tipo,
        monto=payload.monto,
        descripcion=payload.descripcion,
    )
    return MovimientoCajaResponse(**mov)


# =====================================================================
# RF-09 — LISTAR MOVIMIENTOS DE UNA CAJA
# =====================================================================

@router.get(
    "/caja/{caja_id}/movimientos",
    response_model=List[MovimientoCajaResponse],
    summary="Listar movimientos manuales de una caja",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def listar_movimientos_caja(
    caja_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-09: Lista de ingresos/egresos manuales registrados en la caja."""
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    movimientos = await listar_movimientos(caja_id)
    return [MovimientoCajaResponse(**m) for m in movimientos]


# =====================================================================
# RF-09 — CIERRE DE CAJA Y ARQUEO
# =====================================================================

@router.post(
    "/caja/{caja_id}/cerrar",
    response_model=ArqueoCajaResponse,
    summary="Cerrar turno de caja con arqueo",
    description="Cierra la caja calculando diferencia entre el monto contado "
                "físicamente y el total esperado del sistema.",
)
async def cerrar_caja(
    caja_id: str,
    payload: CerrarCajaRequest,
):
    """RF-09: Cierre y arqueo de caja por turno."""
    try:
        arqueo = await cerrar_turno(
            caja_id=caja_id,
            monto_cierre_real=payload.monto_cierre_real,
            observaciones=payload.observaciones,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return ArqueoCajaResponse(**arqueo)


# =====================================================================
# RF-09 — HISTORIAL DE CAJAS DEL CAJERO
# =====================================================================

@router.get(
    "/caja/historial",
    response_model=List[CajaResponse],
    summary="Historial de cajas del cajero",
    description="Retorna las cajas (abiertas y cerradas) del cajero autenticado.",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def historial_cajas(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-09: Historial de turnos de caja del cajero."""
    cajero_id = current_user.get("user_id")
    cajas = await obtener_historial(cajero_id, limit=limit, offset=offset)
    return [
        CajaResponse(**{k: c[k] for k in CajaResponse.model_fields if k in c})
        for c in cajas
    ]


# =====================================================================
# RF-10 — VENTA PRESENCIAL POS
# =====================================================================

@router.post(
    "/ventas/cobrar",
    response_model=VentaPOSResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Procesar venta presencial",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def procesar_venta_pos(
    payload: VentaPOSRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-10: Venta presencial rápida y emisión de ticket/factura."""
    caja = await obtener_caja(str(payload.caja_id))
    if not caja or caja["estado"] != "abierta":
        raise HTTPException(
            status_code=403,
            detail="La caja no está abierta para procesar ventas.",
        )

    lineas = [
        ItemTicketPOS(
            sku=item.sku,
            nombre=item.nombre,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            total_linea=(item.precio_unitario * item.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        for item in payload.items
    ]
    total = sum((linea.total_linea for linea in lineas), Decimal("0.00")).quantize(Decimal("0.01"))
    monto_iva = (total * _IVA_RATE / (Decimal("1.00") + _IVA_RATE)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subtotal_neto = total - monto_iva
    orden_id = uuid.uuid4()
    codigo_orden = f"POS-{uuid.uuid4().hex[:6].upper()}"
    es_consumidor_final = (
        payload.modalidad == "sin_factura"
        or (payload.cliente_nit_ci or "").strip() in ("0", "99001")
        or (payload.cliente_razon_social or "").strip().upper() == "CONSUMIDOR FINAL"
    )
    nit_cliente = "0" if es_consumidor_final else (payload.cliente_nit_ci or "").strip()
    razon_social = "CONSUMIDOR FINAL" if es_consumidor_final else (payload.cliente_razon_social or "").strip().upper()
    modalidad_fiscal = "sin_factura" if es_consumidor_final else "con_factura"
    tipo_documento = "CI" if es_consumidor_final else payload.tipo_documento
    if not es_consumidor_final and (not nit_cliente or not razon_social):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Para emitir una factura nominada se requiere NIT/CI y razón social.",
        )

    # Pago dividido: la suma de las transacciones debe igualar el total de la venta.
    try:
        pagos = normalizar_pagos(payload.pagos, payload.metodo_pago, total)
    except PagoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Descuento de inventario (RIO-INV-03) + autorización de cada tramo de pago (RIO-PAG-01) como una
    # saga: si un tramo es rechazado se reversan los cobros ya aprobados y se reingresa el stock.
    items_stock = [{"sku": i.sku, "cantidad": i.cantidad} for i in payload.items]
    pagos_procesados: List[PagoProcesado] = []
    saga = SagaOrchestrator("venta_pos")
    saga.paso(
        "descuento_stock",
        lambda: inventarios_client.descuento_directo(items_stock, orden_id=str(orden_id)),
        lambda _res: inventarios_client.reingreso_por_devolucion(str(orden_id), items_stock),
    )
    agregar_pasos_de_cobro(saga, pagos, pagos_procesados)
    resultado_saga = await saga.ejecutar()
    if not resultado_saga.exitosa:
        detalle = (resultado_saga.error or "No se pudo completar la venta.").split(": ", 1)[-1]
        if resultado_saga.compensados:
            detalle = f"{detalle} Se revirtieron los pasos ya realizados: {', '.join(resultado_saga.compensados)}."
        codigo = status.HTTP_409_CONFLICT if resultado_saga.paso_fallido == "descuento_stock" else status.HTTP_402_PAYMENT_REQUIRED
        raise HTTPException(status_code=codigo, detail=detalle)

    # Acumular en caja cada tramo en su bucket (transferencia/pasarela se agrupan con QR).
    for pago in pagos_procesados:
        metodo_bucket = pago.metodo if pago.metodo in ("efectivo", "tarjeta", "qr") else "qr"
        if isinstance(caja, dict):
            await acumular_venta(str(payload.caja_id), metodo_bucket, pago.monto)
        else:
            if pago.metodo == "efectivo":
                caja.total_efectivo += pago.monto
            elif pago.metodo == "tarjeta":
                caja.total_tarjeta += pago.monto
            else:
                caja.total_qr += pago.monto

    # The sale is already paid and stock is committed; an ERP outage must not
    # fabricate a legal invoice or make the cashier retry and charge twice.
    try:
        factura_data = await pagos_client.emitir_factura({
            "orden_id": str(orden_id),
            "codigo_orden": codigo_orden,
            "sucursal_id": str(payload.sucursal_id),
            "modalidad": modalidad_fiscal,
            "tipo_documento": tipo_documento,
            "nit_ci": nit_cliente,
            "razon_social": razon_social,
            "email_facturacion": payload.email_facturacion,
            "guardar_perfil": payload.guardar_perfil,
            "subtotal_neto": float(subtotal_neto),
            "monto_iva": float(monto_iva),
            "monto_total": float(total),
            "metodo_pago": metodo_resumen(pagos_procesados),
            "pagos": [
                {
                    "metodo": pago.metodo,
                    "monto": float(pago.monto),
                    "transaccion_id": pago.transaccion_id,
                    "referencia": pago.referencia,
                }
                for pago in pagos_procesados
            ],
            "items": [
                {
                    "variante_id": str(item.variante_id),
                    "sku": item.sku,
                    "nombre": item.nombre,
                    "cantidad": item.cantidad,
                    "precio_unitario": float(item.precio_unitario),
                    "total_linea": float(linea.total_linea),
                }
                for item, linea in zip(payload.items, lineas)
            ],
        })
    except Exception:
        logger.exception("No se pudo solicitar la autorización fiscal para la venta %s", codigo_orden)
        factura_data = {
            "estado": "pendiente",
            "modo": "fallback",
            "mensaje": "La venta fue cobrada; no se obtuvo autorización fiscal. El comprobante no es una factura.",
        }

    factura_data = factura_data if isinstance(factura_data, dict) else {}
    factura_documento = factura_data.get("factura")
    if isinstance(factura_documento, dict):
        factura_documento = {**factura_data, **factura_documento}
    else:
        factura_documento = factura_data

    modo_fiscal = str(factura_data.get("modo") or factura_documento.get("modo") or "").lower()
    estado_fiscal_erp = str(
        factura_documento.get("estado")
        or factura_data.get("estado")
        or factura_documento.get("status")
        or factura_data.get("status")
        or ""
    ).lower()
    numero_raw = factura_documento.get("numero_factura")
    try:
        numero_factura = int(numero_raw) if numero_raw is not None else None
    except (TypeError, ValueError):
        numero_factura = None
    cuf = factura_documento.get("cuf")
    if isinstance(cuf, str):
        cuf = cuf.strip() or None
    else:
        cuf = None

    respuesta_fallback = (
        modo_fiscal in {"fallback", "mock", "mock_fallback", "test", "testing", "simulacion", "simulado"}
        or estado_fiscal_erp in {"pendiente", "rechazado", "rechazada", "rejected", "error", "failed", "fallback"}
        or str(factura_data.get("status", "")).lower() == "fallback"
    )
    estado_autorizado = estado_fiscal_erp in {
        "timbrada", "autorizada", "emitida", "authorized", "accepted", "aprobada", "aprobado"
    } or factura_documento.get("autorizada") is True
    factura_autorizada = bool(
        estado_autorizado and numero_factura and numero_factura > 0 and cuf and not respuesta_fallback
    )
    if not factura_autorizada:
        numero_factura = None
        cuf = None

    cufd = factura_documento.get("cufd") if factura_autorizada else None
    qr_value = (
        factura_documento.get("qr_url") or factura_documento.get("codigo_qr")
        if factura_autorizada else None
    )
    qr_url = qr_value.strip() if isinstance(qr_value, str) and qr_value.strip() else None
    qr_code = _qr_data_url(qr_url) if qr_url else None
    factura_estado = "autorizada" if factura_autorizada else "pendiente"
    factura_mensaje = (
        "Factura autorizada por el servicio fiscal."
        if factura_autorizada
        else "Venta cobrada. Factura pendiente de autorización; este comprobante no tiene validez de factura fiscal."
    )

    ancho = 42
    separador = "-" * ancho
    detalle_items = "\n".join(
        f"{linea.cantidad} x {linea.nombre[:20]}\n  SKU {linea.sku[:18]} @ BOB {linea.precio_unitario:.2f}  BOB {linea.total_linea:.2f}"
        for linea in lineas
    )
    detalle_pagos_ticket = "".join(
        f"      - {p.metodo.upper()}: BOB {p.monto:.2f}\n" for p in pagos_procesados
    ) if len(pagos_procesados) > 1 else ""

    lineas_fiscales = (
        f"Factura No: {numero_factura}\n    CUF: {cuf}\n"
        if factura_autorizada
        else "FACTURA ELECTRÓNICA: PENDIENTE DE AUTORIZACIÓN\n"
    )
    linea_qr = f"QR tributario: {qr_url}\n" if qr_url else ""
    ticket = f"""
    ========================================
             MAXICONECTA - SUCURSAL
    ========================================
    Orden: {codigo_orden}
    Fecha: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M')}
    NIT/CI: {nit_cliente}
    Cliente: {razon_social}
    {separador}
    DETALLE DE ÍTEMS
    {detalle_items}
    {separador}
    Subtotal neto: BOB {subtotal_neto:.2f}
    IVA (13% incluido): BOB {monto_iva:.2f}
    Total: BOB {total:.2f}
    Método: {metodo_resumen(pagos_procesados).upper()}
{detalle_pagos_ticket}{lineas_fiscales}    {linea_qr}
    ========================================
    """

    # OrderPaidEvent -> Contabilidad (RIO-CON-01) con el desglose por forma de pago.
    await publicar_order_paid_event(construir_order_paid_event(
        orden_id=str(orden_id),
        codigo_orden=codigo_orden,
        canal="pos",
        total=total,
        pagos=pagos_procesados,
        sucursal_id=str(payload.sucursal_id),
        cuf=cuf,
        numero_factura=numero_factura,
    ))

    ticket_response = VentaPOSResponse(
        orden_id=orden_id,
        codigo_orden=codigo_orden,
        subtotal_neto=subtotal_neto,
        monto_iva=monto_iva,
        total=total,
        metodo_pago=metodo_resumen(pagos_procesados),
        desglose_pagos=pagos_procesados,
        cambio_total=sum((p.cambio for p in pagos_procesados), Decimal("0.00")),
        numero_factura=numero_factura,
        cuf=cuf,
        cufd=cufd,
        factura_estado=factura_estado,
        factura_mensaje=factura_mensaje,
        qr_url=qr_url,
        qr_code=qr_code,
        items=lineas,
        ticket_impresion=ticket.strip()
    )
    await _guardar_ticket_pos(
        ticket=ticket_response,
        caja_id=str(payload.caja_id),
        cajero_id=str(caja["cajero_id"]),
        sucursal_id=str(payload.sucursal_id),
    )
    return ticket_response


# =====================================================================
# KAN-347 — CONSULTA Y REIMPRESIÓN DE TICKETS DEL TURNO
# =====================================================================

@router.get(
    "/orders/recientes",
    response_model=List[VentaPOSReciente],
    summary="Consultar las últimas ventas del turno POS",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def ultimas_ventas_pos(
    caja_id: str = Query(...),
    limit: int = Query(10, ge=1, le=10),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caja no encontrada.")
    _validar_acceso_venta(caja, current_user)

    ventas = await _listar_ventas_pos(caja_id, limit)
    return [
        VentaPOSReciente(
            orden_id=venta["orden_id"],
            codigo_orden=venta["codigo_orden"],
            total=venta["total"],
            numero_factura=(venta.get("ticket") or {}).get("numero_factura"),
            created_at=venta.get("created_at"),
        )
        for venta in ventas
    ]


@router.get(
    "/orders/{orden_id}/ticket",
    response_model=TicketReimpresionResponse,
    summary="Registrar y recuperar un ticket para reimpresión",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def reimprimir_ticket_pos(
    orden_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    supabase = get_supabase_admin_client()
    venta = None
    if supabase:
        try:
            result = (
                supabase.table("pos_ventas")
                .select("orden_id,codigo_orden,caja_turno_id,cajero_id,sucursal_id,total,ticket,created_at")
                .eq("orden_id", orden_id)
                .limit(1)
                .execute()
            )
            venta = result.data[0] if result.data else None
        except Exception:
            logger.exception("No se pudo consultar el ticket POS %s", orden_id)
    if venta is None:
        venta = _VENTAS_POS_EN_MEMORIA.get(orden_id)
    if not venta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el ticket de la venta.")

    caja = await obtener_caja(venta["caja_turno_id"])
    if not caja:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontró el turno de la venta.")
    _validar_acceso_venta(caja, current_user)
    await _registrar_reimpresion(venta, str(current_user.get("user_id")))

    ticket = dict(venta["ticket"])
    ticket["duplicado"] = True
    ticket["ticket_impresion"] = (
        "*************** DUPLICADO ***************\n"
        + ticket["ticket_impresion"]
        + "\n************* FIN DE DUPLICADO *************"
    )
    return ticket


# =====================================================================
# RF-12 — VENTAS SUSPENDIDAS (POR CAJA)
# =====================================================================

@router.post(
    "/ventas/{caja_id}/suspender",
    status_code=status.HTTP_201_CREATED,
    summary="Suspender venta en una caja",
)
async def suspender_venta(
    caja_id: str,
    payload: VentaSuspendida,
):
    """RF-12: Suspender transacción en una caja."""
    caja = await obtener_caja(caja_id)
    if not caja or caja["estado"] != "abierta":
        raise HTTPException(status_code=403, detail="La caja no está abierta.")

    await save_suspended_sale(caja_id, payload.id, payload.model_dump(mode="json"))
    return {"mensaje": "Venta pausada exitosamente", "id": payload.id}


@router.get(
    "/ventas/{caja_id}/suspendidas",
    response_model=List[VentaSuspendida],
    summary="Listar ventas suspendidas de una caja",
)
async def listar_ventas_suspendidas(caja_id: str):
    """RF-12: Recuperar lista de ventas en espera de una caja."""
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    ventas = await list_suspended_sales(caja_id)
    return [VentaSuspendida(**venta) for venta in ventas]


@router.delete(
    "/ventas/{caja_id}/suspendidas/{id}",
    summary="Reanudar venta suspendida de una caja",
)
async def reanudar_venta_suspendida(caja_id: str, id: str):
    """RF-12: Reanudar venta y quitarla de espera."""
    caja = await obtener_caja(caja_id)
    if not caja:
        raise HTTPException(status_code=404, detail="Caja no encontrada.")
    venta = await get_suspended_sale(caja_id, id)
    if not venta:
        raise HTTPException(status_code=404, detail="Venta suspendida no encontrada.")
    await delete_suspended_sale(caja_id, id)
    return venta


# =====================================================================
# RF-12 — VENTAS SUSPENDIDAS (GLOBALES)
# =====================================================================

@router.post(
    "/ventas/suspender",
    status_code=status.HTTP_201_CREATED,
    summary="Suspender venta (global)",
)
async def suspender_venta_global(payload: VentaSuspendida):
    """RF-12: Suspender transacción global/general."""
    await save_suspended_sale("general", payload.id, payload.model_dump(mode="json"))
    return {"mensaje": "Venta pausada exitosamente", "id": payload.id}


@router.get(
    "/ventas/suspendidas",
    response_model=List[VentaSuspendida],
    summary="Listar ventas suspendidas (todas)",
)
async def listar_ventas_suspendidas_todas():
    """RF-12: Recuperar lista global de ventas en espera."""
    ventas = await list_suspended_sales()
    return [VentaSuspendida(**venta) for venta in ventas]


@router.delete(
    "/ventas/suspendidas/{id}",
    summary="Reanudar venta suspendida (global)",
)
async def reanudar_venta_suspendida_global(id: str):
    """RF-12: Reanudar venta por su ID directo."""
    venta = await get_suspended_sale(id)
    if not venta:
        raise HTTPException(status_code=404, detail="Venta suspendida no encontrada.")
    await delete_suspended_sale(id)
    return venta


# ============================================================================
# HISTORIA KAN-10 / KAN-27: RETIRO EN SUCURSAL CLICK & COLLECT (RF-11)
# SUBTAREAS: KAN-107, KAN-108, KAN-324, KAN-325
# ============================================================================

def _get_supabase_safe() -> Optional[Any]:
    try:
        return get_supabase_admin_client()
    except Exception:
        return None

# Almacén de pedidos Click & Collect para validación rápida en mostrador
_CLICK_AND_COLLECT_DB: Dict[str, Dict[str, Any]] = {
    "RET-789214": {
        "orden_id": uuid.UUID("3b749d44-0db0-4e36-9694-84c1724490f1"),
        "codigo_orden": "ORD-2026-CC101",
        "codigo_retiro": "RET-789214",
        "codigo_qr": "MAXI-CC|ORD-2026-CC101|RET-789214|SUC-01",
        "estado": "confirmada",
        "sucursal_id": "SUC-01",
        "sucursal_nombre": "Sucursal Central - La Paz",
        "fecha_compra": "2026-10-10T09:30:00Z",
        "cliente_nombre": "Carlos Mendoza Patzi",
        "cliente_documento": "4829102",
        "cliente_telefono": "+591 71234567",
        "cliente_email": "carlos.mendoza@gmail.com",
        "subtotal": Decimal("15766.00"),
        "descuento": Decimal("0.0"),
        "total": Decimal("15766.00"),
        "metodo_pago": "QR Simple (Aprobado)",
        "cuf_factura": "CUF-1028374029-20261010-093011-8849",
        "numero_factura": 1421,
        "items": [
            {
                "sku": "LAP-DELL-XPS15",
                "nombre_producto": "Laptop Dell XPS 15 (OLED 4K, i7 13va Gen)",
                "cantidad": 1,
                "precio_unitario": Decimal("6767.00"),
                "total_linea": Decimal("6767.00")
            },
            {
                "sku": "MOU-LOG-MX3S",
                "nombre_producto": "Mouse Inalámbrico Logitech MX Master 3S",
                "cantidad": 1,
                "precio_unitario": Decimal("8999.00"),
                "total_linea": Decimal("8999.00")
            }
        ],
        "despacho": None
    },
    "RET-345091": {
        "orden_id": uuid.UUID("c56b06e9-bfe9-4e7a-9a99-8ee3ad192305"),
        "codigo_orden": "ORD-2026-CC102",
        "codigo_retiro": "RET-345091",
        "codigo_qr": "MAXI-CC|ORD-2026-CC102|RET-345091|SUC-01",
        "estado": "entregada",
        "sucursal_id": "SUC-01",
        "sucursal_nombre": "Sucursal Central - La Paz",
        "fecha_compra": "2026-10-09T16:20:00Z",
        "cliente_nombre": "Sofía Doria Medina",
        "cliente_documento": "6543210",
        "cliente_telefono": "+591 76543210",
        "cliente_email": "sofia.doria@gmail.com",
        "subtotal": Decimal("1850.00"),
        "descuento": Decimal("0.0"),
        "total": Decimal("1850.00"),
        "metodo_pago": "Tarjeta Visa Débito",
        "cuf_factura": "CUF-1028374029-20261009-162100-3321",
        "numero_factura": 1419,
        "items": [
            {
                "sku": "KEY-RGB-01",
                "nombre_producto": "Teclado Mecánico RGB Switches Brown",
                "cantidad": 2,
                "precio_unitario": Decimal("925.00"),
                "total_linea": Decimal("1850.00")
            }
        ],
        "despacho": {
            "fecha_entrega": "2026-10-10T10:15:00Z",
            "cajero_id": "c0000000-0000-0000-0000-000000000002",
            "cajero_nombre": "Oscar Menacho",
            "sucursal_id": "SUC-01",
            "sucursal_nombre": "Sucursal Central - La Paz",
            "receptor_nombre": "Roberto Doria Medina",
            "receptor_documento": "6543211",
            "receptor_tipo": "tercero_autorizado",
            "receptor_telefono": "+591 76543299",
            "observaciones": "Retiro autorizado con fotocopia de CI y carta poder simple.",
            "numero_acta": "ACTA-CC-2026-0041"
        }
    },
    "RET-992381": {
        "orden_id": uuid.UUID("4422e861-55ff-4ab0-b19b-c6b6103e911f"),
        "codigo_orden": "ORD-2026-CC103",
        "codigo_retiro": "RET-992381",
        "codigo_qr": "MAXI-CC|ORD-2026-CC103|RET-992381|SUC-01",
        "estado": "cancelada",
        "sucursal_id": "SUC-01",
        "sucursal_nombre": "Sucursal Central - La Paz",
        "fecha_compra": "2026-10-08T11:00:00Z",
        "cliente_nombre": "Juan Pérez García",
        "cliente_documento": "11223344",
        "cliente_telefono": "+591 79988776",
        "cliente_email": "juan.perez@empresa.bo",
        "subtotal": Decimal("4500.00"),
        "descuento": Decimal("0.0"),
        "total": Decimal("4500.00"),
        "metodo_pago": "QR Simple",
        "cuf_factura": None,
        "numero_factura": None,
        "items": [
            {
                "sku": "MON-4K-27",
                "nombre_producto": "Monitor Profesional 27 Pulgadas 4K",
                "cantidad": 1,
                "precio_unitario": Decimal("4500.00"),
                "total_linea": Decimal("4500.00")
            }
        ],
        "despacho": None
    }
}


def _extraer_codigo_clave(codigo_raw: str) -> str:
    """Extrae el código de retiro o código de orden desde texto, QR o prefijo."""
    val = codigo_raw.strip()
    if "|" in val:
        # Formato de QR: MAXI-CC|ORD-XXXX|RET-XXXX|SUC-XX
        partes = val.split("|")
        for p in partes:
            if p.startswith("RET-"):
                return p
        for p in partes:
            if p.startswith("ORD-"):
                return p
    return val.upper()


_ESTADOS_RETIRO_ENTREGABLES = {"confirmada", "en_preparacion", "despachada", "pendiente_retiro"}
_SUCURSAL_CENTRAL_UUID = "b0000000-0000-0000-0000-000000000001"


def _codigo_retiro_orden(orden_id: Any) -> str:
    return f"RET-{uuid.UUID(str(orden_id)).hex[-8:].upper()}"


def _sucursal_coincide(sucursal_pedido: Optional[str], sucursal_solicitada: Optional[str]) -> bool:
    if not sucursal_solicitada or not sucursal_pedido:
        return True
    aliases = {"SUC-01": _SUCURSAL_CENTRAL_UUID, _SUCURSAL_CENTRAL_UUID: "SUC-01"}
    return sucursal_pedido == sucursal_solicitada or aliases.get(sucursal_pedido) == sucursal_solicitada


def _objeto_relacionado(value: Any) -> Dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _cargar_pedidos_retiro_supabase(sucursal_id: Optional[str]) -> List[Dict[str, Any]]:
    client = _get_supabase_safe()
    if not client:
        return []
    try:
        query = (
            client.table("ordenes")
            .select("*, orden_items(*), perfiles_clientes(*)")
            .eq("tipo_despacho", "retiro_sucursal")
        )
        if sucursal_id:
            query = query.eq("sucursal_id", sucursal_id)
        rows = query.order("created_at", desc=True).limit(200).execute().data or []
        order_ids = [str(row["id"]) for row in rows]
        if not order_ids:
            return []

        payment_rows = client.table("pagos").select("orden_id,metodo,estado").in_("orden_id", order_ids).execute().data or []
        payments_by_order: Dict[str, List[Dict[str, Any]]] = {}
        for payment in payment_rows:
            payments_by_order.setdefault(str(payment["orden_id"]), []).append(payment)

        delivered_ids = [str(row["id"]) for row in rows if row.get("estado") == "entregada"]
        audit_by_order: Dict[str, Dict[str, Any]] = {}
        if delivered_ids:
            try:
                audits = (
                    client.table("audit_logs")
                    .select("entity_id,payload_after,created_at")
                    .eq("action", "DESPACHO_CLICK_AND_COLLECT")
                    .in_("entity_id", delivered_ids)
                    .order("created_at", desc=True)
                    .execute().data or []
                )
                for audit in audits:
                    audit_by_order.setdefault(str(audit["entity_id"]), audit)
            except Exception:
                logger.exception("No se pudo recuperar la auditoría de entregas Click & Collect")

        records = []
        for row in rows:
            order_id = str(row["id"])
            payments = payments_by_order.get(order_id, [])
            approved_payments = [p for p in payments if str(p.get("estado", "")).lower() == "aprobado"]
            if not approved_payments and row.get("estado") not in {"entregada", "cancelada"}:
                continue

            profile = _objeto_relacionado(row.get("perfiles_clientes"))
            items = row.get("orden_items") or []
            codigo_retiro = _codigo_retiro_orden(order_id)
            qr = f"MAXI-CC|{row.get('codigo_orden', '')}|{codigo_retiro}|{row.get('sucursal_id') or ''}"
            audit = audit_by_order.get(order_id, {})
            audit_payload = _objeto_relacionado(audit.get("payload_after"))
            despacho = audit_payload.get("despacho")
            if not despacho and audit:
                despacho = {
                    "fecha_entrega": audit.get("created_at"),
                    "cajero_nombre": "Cajero de turno",
                    "sucursal_id": row.get("sucursal_id"),
                    "sucursal_nombre": "Sucursal de retiro",
                    "receptor_nombre": "Receptor registrado",
                    "receptor_documento": "",
                    "receptor_tipo": "titular",
                    "numero_acta": None,
                }

            records.append({
                "orden_id": uuid.UUID(order_id),
                "codigo_orden": row["codigo_orden"],
                "codigo_retiro": codigo_retiro,
                "codigo_qr": qr,
                "estado": row.get("estado", "pendiente"),
                "sucursal_id": str(row["sucursal_id"]) if row.get("sucursal_id") else None,
                "sucursal_nombre": "Sucursal Central - La Paz" if str(row.get("sucursal_id")) == _SUCURSAL_CENTRAL_UUID else "Sucursal de retiro",
                "fecha_compra": row.get("created_at") or datetime.utcnow().isoformat(),
                "cliente_nombre": profile.get("razon_social") or profile.get("nombre_completo") or "Cliente",
                "cliente_documento": profile.get("nit_ci") or "0",
                "cliente_telefono": profile.get("telefono"),
                "cliente_email": profile.get("email"),
                "subtotal": Decimal(str(row.get("subtotal", 0))),
                "descuento": Decimal(str(row.get("descuento", 0))),
                "total": Decimal(str(row.get("total", 0))),
                "metodo_pago": ", ".join(str(p.get("metodo", "")).upper() for p in approved_payments) or "Pago registrado",
                "cuf_factura": row.get("cuf_factura"),
                "numero_factura": row.get("numero_factura"),
                "items": [{
                    "sku": item.get("sku", "ITEM"),
                    "nombre_producto": item.get("nombre_producto", "Producto"),
                    "cantidad": int(item.get("cantidad", 1)),
                    "precio_unitario": Decimal(str(item.get("precio_unitario", 0))),
                    "total_linea": Decimal(str(item.get("total_linea", 0))),
                } for item in items],
                "despacho": despacho,
                "_persistido": True,
            })
        return records
    except Exception:
        logger.exception("No se pudieron cargar órdenes pagadas de retiro desde Supabase")
        return []


def _sucursal_retiro_autorizada(current_user: Dict[str, Any], sucursal_solicitada: Optional[str]) -> Optional[str]:
    role = str(current_user.get("role", "")).lower()
    sucursal_usuario = str(current_user.get("sucursal_id") or "").strip() or None
    if role == "cajero":
        if not sucursal_usuario:
            raise HTTPException(status_code=403, detail="El cajero no tiene una sucursal asignada.")
        if sucursal_solicitada and not _sucursal_coincide(sucursal_usuario, sucursal_solicitada):
            raise HTTPException(status_code=403, detail="No puedes consultar pedidos de otra sucursal.")
        return sucursal_usuario
    return sucursal_solicitada


@router.get("/click-and-collect/pedidos", response_model=List[PedidoRetiroResponse])
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def listar_pedidos_click_and_collect(
    sucursal_id: Optional[str] = None,
    filtro_estado: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """KAN-324: Listar pedidos Click & Collect para la pantalla de mostrador."""
    sucursal_id = _sucursal_retiro_autorizada(current_user, sucursal_id)
    registros = {str(record["orden_id"]): record for record in _CLICK_AND_COLLECT_DB.values()}
    for record in _cargar_pedidos_retiro_supabase(sucursal_id):
        registros[str(record["orden_id"])] = record

    resultados = []
    
    for record in registros.values():
        if not _sucursal_coincide(record.get("sucursal_id"), sucursal_id):
            continue
        
        estado = record["estado"]
        if filtro_estado:
            if filtro_estado == "pendientes" and estado not in ("confirmada", "en_preparacion", "despachada", "pendiente_retiro"):
                continue
            elif filtro_estado == "entregados" and estado != "entregada":
                continue

        es_entregable = estado in ("confirmada", "en_preparacion", "despachada", "pendiente_retiro")
        motivo = None
        if estado == "entregada":
            desp = record.get("despacho")
            if desp:
                motivo = f"Pedido entregado el {desp.get('fecha_entrega', '')} a {desp.get('receptor_nombre', 'el titular')}"
            else:
                motivo = "El pedido ya figura como entregado previamente."
        elif estado == "cancelada":
            motivo = "El pedido fue cancelado y no puede ser despachado."

        resultados.append(PedidoRetiroResponse(
            orden_id=record["orden_id"],
            codigo_orden=record["codigo_orden"],
            codigo_retiro=record["codigo_retiro"],
            codigo_qr=record.get("codigo_qr"),
            estado=estado,
            es_entregable=es_entregable,
            motivo_rechazo=motivo,
            sucursal_id=record.get("sucursal_id"),
            sucursal_nombre=record.get("sucursal_nombre", "Sucursal Central"),
            fecha_compra=record["fecha_compra"],
            cliente_nombre=record["cliente_nombre"],
            cliente_documento=record["cliente_documento"],
            cliente_telefono=record.get("cliente_telefono"),
            cliente_email=record.get("cliente_email"),
            subtotal=record["subtotal"],
            descuento=record.get("descuento", Decimal("0.0")),
            total=record["total"],
            metodo_pago=record.get("metodo_pago"),
            cuf_factura=record.get("cuf_factura"),
            numero_factura=record.get("numero_factura"),
            items=[DetalleItemRetiro(**i) for i in record["items"]],
            despacho=AuditoriaDespachoInfo(**record["despacho"]) if record.get("despacho") else None
        ))

    return resultados


@router.post("/click-and-collect/validar", response_model=PedidoRetiroResponse)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def validar_codigo_click_and_collect(
    payload: ValidarRetiroRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    KAN-324: [BE] Endpoint para validación de código o QR de retiro Click & Collect.
    KAN-108: Validación de identidad y estado del pedido.
    """
    sucursal_id = _sucursal_retiro_autorizada(current_user, payload.sucursal_id)
    codigo_busqueda = _extraer_codigo_clave(payload.codigo)
    
    # 1. Buscar coincidencia exacta por código de retiro o código de orden
    record = None
    for r in _CLICK_AND_COLLECT_DB.values():
        if (
            r["codigo_retiro"].upper() == codigo_busqueda or
            r["codigo_orden"].upper() == codigo_busqueda or
            str(r["orden_id"]).upper() == codigo_busqueda
        ):
            if _sucursal_coincide(r.get("sucursal_id"), sucursal_id):
                record = r
            break

    # 2. Orders backed by Supabase share the same stable code and payment checks as the queue.
    if not record:
        for candidate in _cargar_pedidos_retiro_supabase(sucursal_id):
            if codigo_busqueda in {
                candidate["codigo_retiro"].upper(),
                candidate["codigo_orden"].upper(),
                str(candidate["orden_id"]).upper(),
            }:
                record = candidate
                _CLICK_AND_COLLECT_DB[candidate["codigo_retiro"]] = candidate
                break

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró ningún pedido Click & Collect con el código o QR '{payload.codigo}'."
        )

    # Evaluación de estado y entregabilidad (KAN-108)
    estado = record["estado"]
    es_entregable = estado in ("confirmada", "en_preparacion", "despachada", "pendiente_retiro")
    motivo_rechazo = None

    if estado == "entregada":
        desp = record.get("despacho")
        if desp:
            motivo_rechazo = (
                f"Este pedido YA FUE ENTREGADO previamente el {desp.get('fecha_entrega')} "
                f"al receptor {desp.get('receptor_nombre')} (Doc: {desp.get('receptor_documento')}) "
                f"por el Cajero {desp.get('cajero_nombre')}."
            )
        else:
            motivo_rechazo = "El pedido ya figura registrado en estado ENTREGADO."
    elif estado == "cancelada":
        motivo_rechazo = "El pedido se encuentra CANCELADO. Las existencias fueron restituidas a almacén."

    return PedidoRetiroResponse(
        orden_id=record["orden_id"],
        codigo_orden=record["codigo_orden"],
        codigo_retiro=record["codigo_retiro"],
        codigo_qr=record.get("codigo_qr"),
        estado=estado,
        es_entregable=es_entregable,
        motivo_rechazo=motivo_rechazo,
        sucursal_id=record.get("sucursal_id"),
        sucursal_nombre=record.get("sucursal_nombre", "Sucursal Central"),
        fecha_compra=record["fecha_compra"],
        cliente_nombre=record["cliente_nombre"],
        cliente_documento=record["cliente_documento"],
        cliente_telefono=record.get("cliente_telefono"),
        cliente_email=record.get("cliente_email"),
        subtotal=record["subtotal"],
        descuento=record.get("descuento", Decimal("0.0")),
        total=record["total"],
        metodo_pago=record.get("metodo_pago"),
        cuf_factura=record.get("cuf_factura"),
        numero_factura=record.get("numero_factura"),
        items=[DetalleItemRetiro(**i) for i in record["items"]],
        despacho=AuditoriaDespachoInfo(**record["despacho"]) if record.get("despacho") else None
    )


@router.post("/click-and-collect/confirmar-entrega", response_model=ConfirmarEntregaResponse)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def confirmar_entrega_click_and_collect(
    payload: ConfirmarEntregaRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    KAN-325: [BE] Lógica de actualización de pedido a 'Entregado' y auditoría de despacho (RF-11, RF-50).
    Registra el acta de entrega y datos del receptor (titular o tercero autorizado).
    """
    sucursal_id = _sucursal_retiro_autorizada(current_user, payload.sucursal_id)
    clave = _extraer_codigo_clave(payload.codigo_retiro)
    orden_id = str(payload.orden_id)
    record = next(
        (r for r in _CLICK_AND_COLLECT_DB.values() if str(r["orden_id"]) == orden_id),
        None,
    )
    if not record:
        for candidate in _cargar_pedidos_retiro_supabase(sucursal_id):
            if str(candidate["orden_id"]) == orden_id:
                record = candidate
                _CLICK_AND_COLLECT_DB[candidate["codigo_retiro"]] = candidate
                break

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pedido no encontrado para confirmación de entrega."
        )

    if not _sucursal_coincide(record.get("sucursal_id"), sucursal_id):
        raise HTTPException(status_code=403, detail="Este pedido pertenece a otra sucursal.")
    codigos_validos = {
        str(record["codigo_retiro"]).upper(),
        str(record["codigo_orden"]).upper(),
        str(record["orden_id"]).upper(),
    }
    if clave not in codigos_validos:
        raise HTTPException(status_code=409, detail="El código de retiro no corresponde al pedido seleccionado.")

    # Validar que el pedido esté en un estado entregable
    if record["estado"] == "entregada":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operación inválida: El pedido ya fue entregado con anterioridad."
        )
    if record["estado"] == "cancelada":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Operación inválida: El pedido se encuentra cancelado."
        )
    if record["estado"] not in _ESTADOS_RETIRO_ENTREGABLES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El pedido no está listo para retiro (estado actual: {record['estado']}).",
        )
    receptor_nombre = payload.receptor_nombre.strip()
    receptor_documento = payload.receptor_documento.strip()
    if len(receptor_nombre) < 2 or len(receptor_documento) < 4:
        raise HTTPException(status_code=422, detail="Registra el nombre y documento válidos del receptor.")

    ahora_iso = datetime.utcnow().isoformat()
    correlativo_acta = f"ACTA-CC-{datetime.utcnow().year}-{str(uuid.uuid4().hex[:6]).upper()}"

    # Construir auditoría inmutable de despacho (RF-50)
    auditoria = {
        "fecha_entrega": ahora_iso,
        "cajero_id": str(current_user.get("user_id") or current_user.get("sub", "cajero-pos")),
        "cajero_nombre": current_user.get("nombre_completo") or payload.cajero_nombre or "Cajero de turno",
        "sucursal_id": sucursal_id or record.get("sucursal_id", "SUC-01"),
        "sucursal_nombre": payload.sucursal_nombre or record.get("sucursal_nombre", "Sucursal Central - La Paz"),
        "receptor_nombre": receptor_nombre,
        "receptor_documento": receptor_documento,
        "receptor_tipo": payload.receptor_tipo,
        "receptor_telefono": payload.receptor_telefono,
        "observaciones": payload.observaciones,
        "numero_acta": correlativo_acta
    }

    audit_guardado = True
    if record.get("_persistido"):
        client = _get_supabase_safe()
        if not client:
            raise HTTPException(status_code=503, detail="No se pudo conectar con la base de datos para registrar la entrega.")
        try:
            updated = client.table("ordenes").update({
                "estado": "entregada",
                "updated_at": ahora_iso
            }).eq("id", orden_id).eq("tipo_despacho", "retiro_sucursal").in_("estado", list(_ESTADOS_RETIRO_ENTREGABLES)).select("id").execute()
            if not updated.data:
                raise HTTPException(status_code=409, detail="El pedido cambió de estado o ya fue despachado por otro cajero.")

            client.table("audit_logs").insert({
                "user_id": auditoria["cajero_id"],
                "user_role": current_user.get("role"),
                "action": "DESPACHO_CLICK_AND_COLLECT",
                "entity": "ordenes",
                "entity_id": orden_id,
                "payload_before": {"estado": record["estado"]},
                "payload_after": {
                    "estado": "entregada",
                    "despacho": auditoria
                }
            }).execute()
        except HTTPException:
            raise
        except Exception:
            audit_guardado = False
            logger.exception("El pedido %s se entregó, pero no se pudo guardar la auditoría.", orden_id)

    record["estado"] = "entregada"
    record["despacho"] = auditoria

    comprobante = {
        "acta_numero": correlativo_acta,
        "codigo_orden": record["codigo_orden"],
        "codigo_retiro": record["codigo_retiro"],
        "titular": record["cliente_nombre"],
        "receptor": receptor_nombre,
        "documento_receptor": receptor_documento,
        "tipo_receptor": payload.receptor_tipo,
        "cajero": auditoria["cajero_nombre"],
        "sucursal": auditoria["sucursal_nombre"],
        "fecha": ahora_iso,
        "total_items": sum(i["cantidad"] for i in record["items"]),
        "monto_total": float(record["total"])
    }

    return ConfirmarEntregaResponse(
        success=True,
        orden_id=record["orden_id"],
        codigo_orden=record["codigo_orden"],
        codigo_retiro=record["codigo_retiro"],
        nuevo_estado="entregada",
        fecha_entrega=ahora_iso,
        receptor_nombre=receptor_nombre,
        receptor_documento=receptor_documento,
        receptor_tipo=payload.receptor_tipo,
        cajero_nombre=auditoria["cajero_nombre"],
        comprobante_entrega=comprobante,
        mensaje=(
            "Pedido entregado y auditoría de despacho registrada."
            if audit_guardado
            else "Pedido entregado; no se pudo guardar el registro de auditoría. Notifica al administrador."
        )
    )


# Compatibilidad retroactiva con endpoint simple
@router.post(
    "/pedidos/retiro-sucursal/validar",
    summary="Validar retiro en sucursal (Click & Collect)",
)
@require_jwt_claims("sub", allowed_roles={"cajero", "administrador"})
async def validar_retiro_sucursal(
    codigo_retiro: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Compatibilidad: validar nunca debe marcar un pedido como entregado."""
    pedido = await validar_codigo_click_and_collect(
        ValidarRetiroRequest(codigo=codigo_retiro, sucursal_id=current_user.get("sucursal_id")),
        current_user=current_user,
    )
    return {
        "codigo_retiro": codigo_retiro,
        "estado": pedido.estado.upper(),
        "es_entregable": pedido.es_entregable,
        "mensaje": "Pedido validado; la entrega requiere confirmación física y registro del receptor.",
    }
