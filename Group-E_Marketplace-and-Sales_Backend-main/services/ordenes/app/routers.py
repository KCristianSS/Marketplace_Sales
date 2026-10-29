import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
try:
    from app.schemas import (
        OrdenCreate, OrdenResponse, ItemOrdenResponse, HistorialOrdenesResponse,
        TransicionEstadoRequest, CotizacionB2BCreate, CotizacionB2BResponse,
        ResenaCreate, ResenaElegibleResponse, ResenaResponse, ModeracionResenaRequest,
        CalculoFleteRequest, CalculoFleteResponse, SucursalRetiroResponse, CoordenadasSucursal,
        PubSubPruebaRequest, PubSubMovimientoRequest
    )
    from app.routers_facturacion import generar_cuf, _FACTURAS_STORE
    from app.pdf import generar_comprobante_pdf
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.schemas import (
        OrdenCreate, OrdenResponse, ItemOrdenResponse, HistorialOrdenesResponse,
        TransicionEstadoRequest, CotizacionB2BCreate, CotizacionB2BResponse,
        ResenaCreate, ResenaElegibleResponse, ResenaResponse, ModeracionResenaRequest,
        CalculoFleteRequest, CalculoFleteResponse, SucursalRetiroResponse, CoordenadasSucursal,
        PubSubPruebaRequest, PubSubMovimientoRequest
    )
    from backend.services.ordenes.app.routers_facturacion import generar_cuf, _FACTURAS_STORE
    from backend.services.ordenes.app.pdf import generar_comprobante_pdf

from backend.shared.erp_clients.inventarios import inventarios_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.erp_clients.entregas import entregas_client
from backend.shared.erp_clients.contabilidad import contabilidad_client
from backend.shared.erp_clients.crm import crm_client
from backend.shared.redis_client import consultar_reserva, confirmar_reserva_stock, liberar_reserva_stock
from backend.shared.security import get_current_user, require_jwt_claims, decode_access_token
from backend.shared.database import get_supabase_admin_client
from backend.shared.config import settings
from backend.shared.pubsub_client import EVENTOS_PUBSUB_LOG, pubsub_client
from backend.shared.pagos_divididos import (
    PagoProcesado, PagoInvalidoError, normalizar_pagos,
    construir_order_paid_event, publicar_order_paid_event,
)
from backend.shared.saga import SagaOrchestrator

logger = logging.getLogger("maxiconecta.ordenes")
router = APIRouter(prefix="/api/v1/ordenes", tags=["Órdenes y Ventas"])

def _get_supabase_safe() -> Optional[Any]:
    try:
        return get_supabase_admin_client()
    except Exception as e:
        logger.warning(f"Aviso al inicializar cliente Supabase: {e}")
        return None

_ORDENES_DB = {}
_COTIZACIONES_DB = {}
_RESENAS_DB: Dict[str, Dict[str, Any]] = {}
logger = logging.getLogger("maxiconecta.ordenes")

TRANSICIONES_VALIDAS = {
    "pendiente": ["confirmada", "cancelada"],
    "confirmada": ["en_preparacion", "cancelada"],
    "en_preparacion": ["despachada", "cancelada"],
    "despachada": ["entregada"],
    "entregada": [],
    "cancelada": []
}


def _persistir_orden_supabase(orden: OrdenResponse, payload: OrdenCreate) -> None:
    client = get_supabase_admin_client()
    if not client:
        return
    try:
        requested_ids = list(dict.fromkeys(str(item.variante_id) for item in payload.items))
        variantes = client.table("variantes").select("id,producto_id").in_("id", requested_ids).execute().data or []
        variante_por_id = {str(row["id"]): str(row["id"]) for row in variantes}
        ids_producto = [identificador for identificador in requested_ids if identificador not in variante_por_id]
        if ids_producto:
            variants_by_product = client.table("variantes").select("id,producto_id").in_("producto_id", ids_producto).order("created_at").execute().data or []
            for variant in variants_by_product:
                variante_por_id.setdefault(str(variant["producto_id"]), str(variant["id"]))

        if any(str(item.variante_id) not in variante_por_id for item in payload.items):
            logger.warning("No se persistió la orden %s: un ítem no corresponde a una variante de catálogo.", orden.id)
            return

        client.table("ordenes").insert({
            "id": str(orden.id),
            "codigo_orden": orden.codigo_orden,
            "cliente_id": str(orden.cliente_id),
            "sucursal_id": str(payload.sucursal_id) if payload.sucursal_id else None,
            "canal": payload.canal,
            "tipo_despacho": payload.tipo_despacho,
            "direccion_entrega_id": str(payload.direccion_entrega_id) if payload.direccion_entrega_id else None,
            "subtotal": float(payload.subtotal),
            "descuento": float(payload.descuento),
            "costo_envio": float(payload.costo_envio),
            "total": float(payload.total),
            "estado": orden.estado,
            "tracking_number": orden.tracking_number,
            "cuf_factura": orden.cuf_factura,
        }).execute()
        client.table("orden_items").insert([
            {
                "orden_id": str(orden.id),
                "variante_id": variante_por_id[str(item.variante_id)],
                "sku": item.sku,
                "nombre_producto": item.nombre_producto,
                "cantidad": item.cantidad,
                "precio_unitario": float(item.precio_unitario),
                "total_linea": float(item.total_linea),
            }
            for item in orden.items
        ]).execute()
    except Exception:
        logger.exception("No se pudo persistir la orden %s en Supabase", orden.id)


def _uuid_db(value: Any) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except (TypeError, ValueError):
        return None


def _persistir_orden_atomica(client: Any, orden: OrdenResponse, payload: OrdenCreate, factura: Dict[str, Any], cliente_id: str) -> Dict[str, Any]:
    """Guarda orden, líneas y pagos mediante un único RPC/txn PostgreSQL."""
    requested_ids = list(dict.fromkeys(str(item.variante_id) for item in payload.items))
    variantes = client.table("variantes").select("id,producto_id").in_("id", requested_ids).execute().data or []
    variante_por_id = {str(row["id"]): str(row["id"]) for row in variantes}
    product_ids = [item_id for item_id in requested_ids if item_id not in variante_por_id]
    if product_ids:
        variants_by_product = client.table("variantes").select("id,producto_id").in_("producto_id", product_ids).order("created_at").execute().data or []
        for variant in variants_by_product:
            variante_por_id.setdefault(str(variant["producto_id"]), str(variant["id"]))
    if any(str(item.variante_id) not in variante_por_id for item in payload.items):
        raise ValueError("Uno o más productos de la orden no corresponden a una variante válida.")

    order_data = {
        "id": str(orden.id),
        "codigo_orden": orden.codigo_orden,
        "cliente_id": cliente_id,
        "sucursal_id": _uuid_db(payload.sucursal_id),
        "canal": payload.canal,
        "tipo_despacho": payload.tipo_despacho,
        "direccion_entrega_id": _uuid_db(payload.direccion_entrega_id),
        "subtotal": str(payload.subtotal),
        "descuento": str(payload.descuento),
        "costo_envio": str(payload.costo_envio),
        "total": str(payload.total),
        "estado": orden.estado,
        "tracking_number": orden.tracking_number,
        "reserva_id": payload.reserva_id,
        "cuf_factura": orden.cuf_factura,
        "numero_factura": orden.numero_factura,
    }
    items_data = [
        {
            "variante_id": variante_por_id[str(item.variante_id)],
            "sku": item.sku,
            "nombre_producto": item.nombre_producto,
            "cantidad": item.cantidad,
            "precio_unitario": str(item.precio_unitario),
            "total_linea": str(item.total_linea),
        }
        for item in orden.items
    ]
    payments_data = [
        {
            "transaccion_id": pago.transaccion_id,
            "metodo": pago.metodo.lower(),
            "monto": str(pago.monto),
            "raw_payload": factura if indice == 0 else {},
        }
        for indice, pago in enumerate(orden.pagos)
    ]
    try:
        result = client.rpc("confirmar_orden_atomica", {
            "p_orden": order_data,
            "p_items": items_data,
            "p_pagos": payments_data,
        }).execute()
    except Exception as exc:
        if not _es_rpc_no_desplegado(exc):
            raise
        logger.warning("RPC confirmar_orden_atomica no desplegado; se usa la persistencia por pasos.")
        return _persistir_orden_por_pasos(client, order_data, items_data, payments_data)
    data = result.data
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("La base de datos no confirmó la transacción de la orden.")
    return data


def _es_rpc_no_desplegado(exc: Exception) -> bool:
    mensaje = str(exc)
    return "PGRST202" in mensaje or "Could not find the function" in mensaje


def _persistir_orden_por_pasos(client: Any, order_data: Dict[str, Any], items_data: List[Dict[str, Any]], payments_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Equivalente al RPC sin transacción: compensa borrando la orden si un paso posterior falla."""
    orden_id = order_data["id"]
    transaccion_id = payments_data[0]["transaccion_id"] if payments_data else None
    if transaccion_id:
        previo = client.table("pagos").select("orden_id").eq("transaccion_id", transaccion_id).limit(1).execute().data or []
        if previo and previo[0].get("orden_id"):
            return {"id": str(previo[0]["orden_id"]), "codigo_orden": order_data["codigo_orden"], "existente": True}

    _insertar_omitiendo_columnas_faltantes(client, "ordenes", {k: v for k, v in order_data.items() if v is not None})
    try:
        if items_data:
            client.table("orden_items").insert([{**item, "orden_id": orden_id} for item in items_data]).execute()
        if payments_data:
            client.table("pagos").insert([
                {**pago, "orden_id": orden_id, "moneda": "BOB", "estado": "aprobado"} for pago in payments_data
            ]).execute()
    except Exception:
        # orden_items and pagos cascade on delete, so removing the order discards the partial write.
        client.table("ordenes").delete().eq("id", orden_id).execute()
        raise
    return {"id": orden_id, "codigo_orden": order_data["codigo_orden"], "existente": False}


_COLUMNA_INEXISTENTE = re.compile(r"column (?:\w+\.)?(\w+) does not exist|Could not find the '(\w+)' column")


def _insertar_omitiendo_columnas_faltantes(client: Any, tabla: str, fila: Dict[str, Any]) -> None:
    """Deployed schemas lag behind db/schema.sql; drop optional columns the database rejects."""
    fila = dict(fila)
    while True:
        try:
            client.table(tabla).insert(fila).execute()
            return
        except Exception as exc:
            match = _COLUMNA_INEXISTENTE.search(str(exc))
            columna = match and (match.group(1) or match.group(2))
            if not columna or columna not in fila or columna in ("id", "codigo_orden", "total"):
                raise
            logger.warning("La tabla %s no tiene la columna %s; se guarda sin ella.", tabla, columna)
            fila.pop(columna)


async def _reversar_pagos_confirmados(pagos: List[PagoProcesado]) -> List[str]:
    errores = []
    for pago in pagos:
        if pago.metodo.lower() == "efectivo":
            continue
        try:
            resultado = await pagos_client.reversar_cobro(str(pago.transaccion_id), float(pago.monto))
            estado = str(resultado.get("estado") or resultado.get("status") or "").upper()
            if estado in {"RECHAZADA", "RECHAZADO", "ERROR", "FALLIDA", "FALLIDO", "DENEGADA", "DENEGADO"}:
                errores.append(f"pago {pago.transaccion_id}: {resultado.get('mensaje') or estado}")
        except Exception as e:
            errores.append(f"pago {pago.transaccion_id}: {e}")
    return errores

@router.post("/", response_model=OrdenResponse, status_code=status.HTTP_201_CREATED)
async def crear_orden(payload: OrdenCreate):
    """RF-27: Creación atómica de orden tras pago confirmado."""
    # 0. Pago dividido: la suma de las transacciones debe igualar el total de la orden.
    try:
        pagos_normalizados = normalizar_pagos(payload.pagos, payload.metodo_pago, payload.total)
    except PagoInvalidoError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    pagos_procesados = [
        PagoProcesado(
            metodo=p.metodo,
            monto=p.monto,
            transaccion_id=(payload.transaccion_id if (len(pagos_normalizados) == 1 and payload.transaccion_id) else f"TX-{uuid.uuid4().hex[:14].upper()}"),
            referencia=p.referencia
        )
        for p in pagos_normalizados
    ]

    async def rechazar_y_reembolsar(codigo_http: int, mensaje: str):
        errores = await _reversar_pagos_confirmados(pagos_procesados)
        if errores:
            mensaje += " Revisa la reversión del cobro: " + "; ".join(errores)
        raise HTTPException(status_code=codigo_http, detail=mensaje)

    idempotency_key = pagos_procesados[0].transaccion_id if pagos_procesados else uuid.uuid4().hex
    orden_id = uuid.uuid5(uuid.NAMESPACE_URL, f"maxiconecta:orden:{idempotency_key}")
    codigo = f"ORD-{datetime.utcnow().year}-{orden_id.hex[:12].upper()}"
    loyalty_client = _get_supabase_safe()
    if loyalty_client and idempotency_key:
        try:
            prior_payment = loyalty_client.table("pagos").select("orden_id").eq("transaccion_id", idempotency_key).limit(1).execute().data or []
            if prior_payment and prior_payment[0].get("orden_id"):
                return await obtener_orden(uuid.UUID(str(prior_payment[0]["orden_id"])))
        except Exception as e:
            logger.warning("No se pudo verificar si la orden ya fue creada: %s", e)

    if payload.puntos_canjeados:
        try:
            cliente_puntos_id = str(uuid.UUID(str(payload.cliente_id)))
        except (ValueError, TypeError):
            await rechazar_y_reembolsar(status.HTTP_422_UNPROCESSABLE_ENTITY, "Debes iniciar sesión para canjear puntos.")

        descuento_puntos = Decimal(payload.puntos_canjeados) * Decimal(str(settings.FIDELIDAD_VALOR_PUNTO_BOB))
        if payload.descuento < descuento_puntos:
            await rechazar_y_reembolsar(status.HTTP_422_UNPROCESSABLE_ENTITY, "El descuento de la orden no cubre los puntos canjeados.")
        total_esperado = max(Decimal("0"), payload.subtotal - payload.descuento + payload.costo_envio)
        if abs(payload.total - total_esperado) > Decimal("0.01"):
            await rechazar_y_reembolsar(status.HTTP_422_UNPROCESSABLE_ENTITY, "El total de la orden no coincide con los descuentos aplicados.")

        saldo_puntos = None
        if loyalty_client:
            try:
                saldo_res = loyalty_client.table("puntos_fidelidad").select("puntos_saldo").eq("cliente_id", cliente_puntos_id).limit(1).execute()
                if saldo_res.data:
                    saldo_puntos = int(saldo_res.data[0].get("puntos_saldo", 0))
            except Exception as e:
                logger.warning("No se pudo validar saldo en Supabase antes del canje: %s", e)
        if saldo_puntos is None:
            crm_saldo = await crm_client.consultar_o_canjear_puntos(cliente_puntos_id, 0, "consultar")
            saldo_puntos = int(crm_saldo.get("saldo_puntos", 0))
        if payload.puntos_canjeados > saldo_puntos:
            await rechazar_y_reembolsar(status.HTTP_409_CONFLICT, "El saldo de puntos disponible no alcanza para este canje.")

    # 1. Validar y confirmar reserva en Redis / Inventarios (RF-14 · RIO-INV-02 / RIO-INV-03)
    if payload.reserva_id:
        reserva = await consultar_reserva(payload.reserva_id)
        if not reserva or reserva.get("status") == "EXPIRADA":
            await rechazar_y_reembolsar(status.HTTP_409_CONFLICT, "La reserva de stock ha expirado o no es válida (límite de 15 minutos superado). Por favor inicie un nuevo checkout.")
        if not await confirmar_reserva_stock(payload.reserva_id):
            await rechazar_y_reembolsar(status.HTTP_409_CONFLICT, "No se pudo confirmar la reserva de stock.")

    # 2. Generar orden de despacho si es a domicilio (RIO-ENT-01)
    tracking_num = None
    if payload.tipo_despacho == "domicilio":
        despacho_res = await entregas_client.solicitar_despacho({
            "orden_id": str(orden_id),
            "direccion_id": str(payload.direccion_entrega_id) if payload.direccion_entrega_id else None,
            "items": [
                {
                    "variante_id": str(i.variante_id),
                    "sku": i.sku,
                    "nombre_producto": i.nombre_producto,
                    "cantidad": i.cantidad,
                    "precio_unitario": float(i.precio_unitario)
                }
                for i in payload.items
            ]
        })
        tracking_num = despacho_res.get("guia_despacho")

    # 3. Generación y timbrado de Factura Legal Electrónica (RF-10, RF-45, RIO-PAG-02, KAN-367)
    df = payload.datos_fiscales
    modalidad = df.modalidad if df else "con_factura"
    es_cf = modalidad == "sin_factura" or (df and df.nit_ci in ("0", "99001"))
    nit_final = "0" if es_cf else (df.nit_ci.strip() if df and df.nit_ci else "0")
    razon_final = "CONSUMIDOR FINAL" if es_cf else (df.razon_social.strip().upper() if df and df.razon_social else "CONSUMIDOR FINAL")
    tipo_doc_final = "CI" if es_cf else (df.tipo_documento.upper() if df and df.tipo_documento else "NIT")
    email_fac = df.email_facturacion if df else None

    # Correlativo secuencial y timbrado CUF
    import time
    numero_factura = int(time.time() % 1000000) + 1000
    nit_emisor = "1028374029"
    ahora = datetime.utcnow()
    cuf = generar_cuf(
        nit_emisor=nit_emisor,
        fecha_hora=ahora,
        sucursal=0,
        modalidad=1,
        tipo_emision=1,
        tipo_doc_sector=1,
        numero_factura=numero_factura,
        punto_venta=1
    )
    cufd = f"CUFD-{uuid.uuid4().hex[:8].upper()}-{ahora.strftime('%Y%m%d')}"
    total_float = float(payload.total)
    qr_url = f"https://pilotosiat.impuestos.gob.bo/consulta/QR?nit={nit_emisor}&cuf={cuf}&numero={numero_factura}&t={total_float:.2f}"

    factura_data = {
        "numero_factura": numero_factura,
        "cuf": cuf,
        "cufd": cufd,
        "fecha_emision": ahora.isoformat(),
        "modalidad": "sin_factura" if es_cf else "con_factura",
        "datos_comprador": {
            "tipo_documento": tipo_doc_final,
            "nit_ci": nit_final,
            "razon_social": razon_final,
            "email_facturacion": email_fac
        },
        "monto_total": total_float,
        "monto_iva": round(total_float * 0.13, 2),
        "codigo_qr": qr_url,
        "leyenda_fiscal": "Ley N° 453: El proveedor deberá suministrar el servicio en las modalidades y términos ofertados."
    }

    items_res = [
        ItemOrdenResponse(
            id=uuid.uuid4(),
            variante_id=i.variante_id,
            sku=i.sku,
            nombre_producto=i.nombre_producto,
            cantidad=i.cantidad,
            precio_unitario=i.precio_unitario,
            total_linea=Decimal(str(i.cantidad)) * i.precio_unitario
        ) for i in payload.items
    ]

    orden = OrdenResponse(
        id=orden_id,
        codigo_orden=codigo,
        cliente_id=payload.cliente_id,
        canal=payload.canal,
        tipo_despacho=payload.tipo_despacho,
        subtotal=payload.subtotal,
        descuento=payload.descuento,
        costo_envio=payload.costo_envio,
        total=payload.total,
        estado="confirmada",
        tracking_number=tracking_num,
        reserva_id=payload.reserva_id,
        cuf_factura=cuf,
        numero_factura=numero_factura,
        factura=factura_data,
        created_at=datetime.utcnow(),
        items=items_res,
        pagos=pagos_procesados,
    )
    client = loyalty_client or _get_supabase_safe()
    cliente_db_uuid = None
    items_payload = [{"sku": i.sku, "cantidad": i.cantidad, "nombre": i.nombre_producto} for i in payload.items]
    stock_descuento_aplicado = False
    if client:
        try:
            # Resolver cliente_id válido para FK de Supabase
            raw_client_id = str(payload.cliente_id)
            cliente_db_uuid = _uuid_db(raw_client_id)
            if not cliente_db_uuid:
                # No es UUID (ej. 'cliente-anonimo')
                if not es_cf and nit_final != "0":
                    cli_res = client.table("perfiles_clientes").select("id").eq("nit_ci", nit_final).limit(1).execute()
                    if cli_res.data:
                        cliente_db_uuid = cli_res.data[0]["id"]
                if not cliente_db_uuid:
                    if not es_cf and df and df.guardar_perfil:
                        safe_email = email_fac if email_fac and "@" in email_fac else f"cliente.{nit_final}.{int(time.time())}@maxiconecta.bo"
                        new_cli = client.table("perfiles_clientes").insert({
                            "nombre_completo": razon_final,
                            "email": safe_email,
                            "nit_ci": nit_final,
                            "razon_social": razon_final,
                            "tipo_cliente": "retail"
                        }).execute()
                        if new_cli.data:
                            cliente_db_uuid = new_cli.data[0]["id"]
                if not cliente_db_uuid:
                    any_cli = client.table("perfiles_clientes").select("id").limit(1).execute()
                    if any_cli.data:
                        cliente_db_uuid = any_cli.data[0]["id"]
            if not cliente_db_uuid:
                raise ValueError("No se pudo asociar la orden a un perfil de cliente.")

        except Exception as e:
            await rechazar_y_reembolsar(status.HTTP_502_BAD_GATEWAY, f"No se pudo resolver el cliente de la orden: {e}")

    # RIO-INV-03: aplicar el descuento una sola vez, vinculado al identificador
    # determinista de la transacción de pago, antes del commit atómico de la orden.
    try:
        stock_result = await inventarios_client.descuento_definitivo(
            reserva_id=payload.reserva_id or f"RES-DIR-{orden_id.hex[:12]}",
            orden_id=str(orden_id),
            items=items_payload,
        )
        stock_status = str(stock_result.get("status", "")).upper()
        if stock_status in {"RECHAZADA", "RECHAZADO", "ERROR", "FALLIDA", "FALLIDO"}:
            raise RuntimeError(stock_result.get("mensaje") or "Inventarios rechazó el descuento de stock.")
        stock_descuento_aplicado = True

        if client:
            db_result = _persistir_orden_atomica(client, orden, payload, factura_data, cliente_db_uuid)
            if db_result.get("existente"):
                return await obtener_orden(uuid.UUID(str(db_result["id"])))
    except Exception as e:
        logger.exception("Falló la confirmación transaccional de la orden %s", codigo)
        errores_compensacion = []
        if stock_descuento_aplicado:
            try:
                await inventarios_client.reingreso_por_devolucion(str(orden_id), items_payload, motivo="fallo_confirmacion_orden")
            except Exception as compensacion_error:
                errores_compensacion.append(f"stock: {compensacion_error}")
        elif payload.reserva_id:
            try:
                await liberar_reserva_stock(payload.reserva_id)
            except Exception as compensacion_error:
                errores_compensacion.append(f"reserva: {compensacion_error}")
        errores_compensacion.extend(await _reversar_pagos_confirmados(pagos_procesados))
        detalle = f"No se pudo confirmar la orden; se inició la reversión del cobro y del stock: {e}"
        if errores_compensacion:
            detalle += ". Requiere revisión manual: " + "; ".join(errores_compensacion)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detalle)

    _ORDENES_DB[str(orden_id)] = orden
    _FACTURAS_STORE.insert(0, {
        **factura_data,
        "id": f"FAC-{orden_id}",
        "orden_id": str(orden_id),
        "codigo_orden": codigo,
        "subtotal": float(payload.subtotal),
        "descuento": float(payload.descuento),
        "total": total_float,
        "metodo_pago": payload.metodo_pago,
        "items": [
            {
                "sku": item.sku,
                "nombre": item.nombre_producto,
                "cantidad": item.cantidad,
                "precio_unitario": float(item.precio_unitario),
                "subtotal": float(item.total_linea),
            }
            for item in items_res
        ],
    })

    try:
        await pagos_client.emitir_factura({
            "orden_id": str(orden_id),
            "numero_factura": numero_factura,
            "cuf": cuf,
            "nit_ci": nit_final,
            "razon_social": razon_final,
            "monto_total": total_float,
        })
    except Exception as e:
        logger.warning("Aviso comunicando con ERP Pagos: %s", e)

    # Publicar el asiento contable después de que la orden quedó confirmada.
    await publicar_order_paid_event(construir_order_paid_event(
        orden_id=str(orden_id), codigo_orden=codigo, canal=payload.canal,
        total=payload.total, pagos=pagos_procesados, sucursal_id=payload.sucursal_id,
    ))

    # RF-25 / RIO-CRM-03: registrar canje y acumulación una vez confirmada la orden.
    # La regla configurable aplica puntos por compra y su equivalente de descuento.
    try:
        cliente_id = str(payload.cliente_id)
        try:
            uuid.UUID(cliente_id)
        except ValueError:
            cliente_id = ""
        puntos_canjeados = payload.puntos_canjeados
        if cliente_id and puntos_canjeados:
            crm_result = await crm_client.consultar_o_canjear_puntos(cliente_id, puntos_canjeados, "canjear")
            if client:
                saldo_actual = 0
                saldo_res = client.table("puntos_fidelidad").select("puntos_saldo").eq("cliente_id", cliente_id).limit(1).execute()
                if saldo_res.data:
                    saldo_actual = int(saldo_res.data[0].get("puntos_saldo", 0))
                saldo_nuevo = max(0, saldo_actual - puntos_canjeados)
                client.table("puntos_fidelidad").upsert({"cliente_id": cliente_id, "puntos_saldo": saldo_nuevo}, on_conflict="cliente_id").execute()
                client.table("movimientos_puntos_fidelidad").insert({
                    "cliente_id": cliente_id, "orden_id": str(orden_id), "tipo": "canje",
                    "puntos": puntos_canjeados, "valor_bob": float(puntos_canjeados * Decimal(str(settings.FIDELIDAD_VALOR_PUNTO_BOB))),
                    "descripcion": f"Canje aplicado a la orden {codigo}"
                }).execute()

        puntos_ganados = int(max(Decimal("0"), payload.subtotal - payload.descuento) // Decimal(str(settings.FIDELIDAD_BOB_POR_PUNTO)))
        if cliente_id and puntos_ganados > 0:
            await crm_client.consultar_o_canjear_puntos(cliente_id, puntos_ganados, "acumular")
            if client:
                saldo_res = client.table("puntos_fidelidad").select("puntos_saldo").eq("cliente_id", cliente_id).limit(1).execute()
                saldo_actual = int(saldo_res.data[0].get("puntos_saldo", 0)) if saldo_res.data else 0
                saldo_nuevo = saldo_actual + puntos_ganados
                client.table("puntos_fidelidad").upsert({"cliente_id": cliente_id, "puntos_saldo": saldo_nuevo}, on_conflict="cliente_id").execute()
                client.table("movimientos_puntos_fidelidad").insert({
                    "cliente_id": cliente_id, "orden_id": str(orden_id), "tipo": "acumulacion",
                    "puntos": puntos_ganados, "valor_bob": float(puntos_ganados * Decimal(str(settings.FIDELIDAD_VALOR_PUNTO_BOB))),
                    "descripcion": f"Puntos ganados por la orden {codigo}"
                }).execute()
    except Exception as e:
        logger.warning("No se pudo sincronizar la fidelización de la orden %s: %s", codigo, e)

    return orden

_bearer_opcional = HTTPBearer(auto_error=False)

async def _obtener_usuario_opcional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_opcional)
) -> Optional[Dict[str, Any]]:
    middleware_user = getattr(request.state, "current_user", None)
    if middleware_user:
        return middleware_user
    if not credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        if not payload:
            return None
        user_metadata = payload.get("user_metadata", {})
        app_metadata = payload.get("app_metadata", {})
        role = payload.get("role") or app_metadata.get("role") or user_metadata.get("role") or "cliente"
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
        return {
            "user_id": str(user_id) if user_id else None,
            "role": str(role).lower(),
            "email": payload.get("email"),
            "nombre_completo": payload.get("nombre_completo") or user_metadata.get("nombre_completo"),
            "payload": payload
        }
    except Exception:
        return None


@router.get("", response_model=HistorialOrdenesResponse)
@router.get("/", response_model=HistorialOrdenesResponse, include_in_schema=False)
async def listar_ordenes(
    cliente_id: Optional[str] = None,
    codigo_orden: Optional[str] = None,
    estado: Optional[str] = None,
    canal: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    busqueda: Optional[str] = None,
    page: int = Query(1, ge=1, description="Número de página (1-based)"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de registros por página"),
    current_user: Optional[Dict[str, Any]] = Depends(_obtener_usuario_opcional)
):
    """
    US-37 / RF-37: Historial completo de compras y órdenes con filtros avanzados,
    paginación y control de acceso (RBAC).
    - Clientes: filtrado estricto por su propio ID de cliente/usuario.
    - Administradores / Gerentes / Cajeros: consulta global multicanal o filtro específico.
    """
    target_cliente_id = cliente_id
    if current_user:
        user_role = current_user.get("role", "cliente").lower()
        if user_role == "cliente":
            target_cliente_id = current_user.get("user_id")

    ordenes_resultado: List[OrdenResponse] = []
    total_registros = 0
    client = _get_supabase_safe()

    if client:
        try:
            query = client.table("ordenes").select("*, orden_items(*), pagos(*)", count="exact")

            if target_cliente_id:
                query = query.eq("cliente_id", str(target_cliente_id))
            if estado:
                query = query.eq("estado", estado.lower().strip())
            if canal:
                query = query.eq("canal", canal.lower().strip())
            if codigo_orden:
                query = query.ilike("codigo_orden", f"%{codigo_orden.strip()}%")
            if fecha_desde:
                fd = f"{fecha_desde}T00:00:00" if "T" not in fecha_desde else fecha_desde
                query = query.gte("created_at", fd)
            if fecha_hasta:
                fh = f"{fecha_hasta}T23:59:59" if "T" not in fecha_hasta else fecha_hasta
                query = query.lte("created_at", fh)

            query = query.order("created_at", desc=True)
            offset = (page - 1) * limit
            query = query.range(offset, offset + limit - 1)

            res = query.execute()
            if res.data is not None:
                total_registros = res.count if res.count is not None else len(res.data)
                for row in res.data:
                    raw_items = row.get("orden_items") or []
                    items_res = [
                        ItemOrdenResponse(
                            id=uuid.UUID(i["id"]) if isinstance(i["id"], str) else i["id"],
                            variante_id=uuid.UUID(i["variante_id"]) if isinstance(i["variante_id"], str) else i["variante_id"],
                            sku=i.get("sku", ""),
                            nombre_producto=i.get("nombre_producto", ""),
                            cantidad=i.get("cantidad", 1),
                            precio_unitario=Decimal(str(i.get("precio_unitario", 0))),
                            total_linea=Decimal(str(i.get("total_linea", i.get("cantidad", 1) * i.get("precio_unitario", 0))))
                        )
                        for i in raw_items
                    ]
                    raw_pagos = row.get("pagos") or []
                    pagos_res = []
                    factura_payload = None
                    for p in raw_pagos:
                        if isinstance(p, dict):
                            pagos_res.append(PagoProcesado(
                                metodo=p.get("metodo", "tarjeta"),
                                monto=Decimal(str(p.get("monto", 0))),
                                transaccion_id=p.get("transaccion_id"),
                                referencia=p.get("referencia")
                            ))
                            if not factura_payload and isinstance(p.get("raw_payload"), dict):
                                factura_payload = p["raw_payload"]

                    ordenes_resultado.append(OrdenResponse(
                        id=uuid.UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
                        codigo_orden=row["codigo_orden"],
                        cliente_id=uuid.UUID(row["cliente_id"]) if isinstance(row["cliente_id"], str) and len(row["cliente_id"]) == 36 else row["cliente_id"],
                        canal=row.get("canal", "web"),
                        tipo_despacho=row.get("tipo_despacho", "domicilio"),
                        subtotal=Decimal(str(row.get("subtotal", 0))),
                        descuento=Decimal(str(row.get("descuento", 0))),
                        costo_envio=Decimal(str(row.get("costo_envio", 0))),
                        total=Decimal(str(row["total"])),
                        estado=row.get("estado", "confirmada"),
                        tracking_number=row.get("tracking_number"),
                        cuf_factura=row.get("cuf_factura"),
                        numero_factura=factura_payload.get("numero_factura") if factura_payload else None,
                        factura=factura_payload,
                        created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if "created_at" in row and row["created_at"] else datetime.utcnow(),
                        items=items_res,
                        pagos=pagos_res
                    ))

                if busqueda:
                    term = busqueda.lower().strip()
                    ordenes_resultado = [
                        o for o in ordenes_resultado
                        if term in o.codigo_orden.lower() or
                           (o.tracking_number and term in o.tracking_number.lower()) or
                           (o.cuf_factura and term in o.cuf_factura.lower()) or
                           any(term in i.nombre_producto.lower() or term in i.sku.lower() for i in o.items)
                    ]
                    total_registros = len(ordenes_resultado)

                total_paginas = max(1, (total_registros + limit - 1) // limit) if total_registros > 0 else 1
                return HistorialOrdenesResponse(
                    items=ordenes_resultado,
                    total=total_registros,
                    pagina=page,
                    limite=limit,
                    total_paginas=total_paginas
                )
        except Exception as e:
            logger.warning(f"Error consultando historial en Supabase, recurriendo a memoria local: {e}")

    # Fallback / Store en memoria local (_ORDENES_DB)
    lista_memoria = list(_ORDENES_DB.values())
    filtradas = []
    for ord_obj in lista_memoria:
        if target_cliente_id and str(ord_obj.cliente_id) != str(target_cliente_id):
            continue
        if estado and ord_obj.estado.lower() != estado.lower().strip():
            continue
        if canal and ord_obj.canal.lower() != canal.lower().strip():
            continue
        if codigo_orden and codigo_orden.lower().strip() not in ord_obj.codigo_orden.lower():
            continue
        if fecha_desde:
            try:
                dt_desde = datetime.fromisoformat(fecha_desde.split("T")[0])
                if ord_obj.created_at.date() < dt_desde.date():
                    continue
            except Exception:
                pass
        if fecha_hasta:
            try:
                dt_hasta = datetime.fromisoformat(fecha_hasta.split("T")[0])
                if ord_obj.created_at.date() > dt_hasta.date():
                    continue
            except Exception:
                pass
        if busqueda:
            term = busqueda.lower().strip()
            match = (
                term in ord_obj.codigo_orden.lower() or
                (ord_obj.tracking_number and term in ord_obj.tracking_number.lower()) or
                (ord_obj.cuf_factura and term in ord_obj.cuf_factura.lower()) or
                any(term in i.nombre_producto.lower() or term in i.sku.lower() for i in ord_obj.items)
            )
            if not match:
                continue

        filtradas.append(ord_obj)

    filtradas.sort(key=lambda o: o.created_at, reverse=True)
    total_registros = len(filtradas)
    offset = (page - 1) * limit
    items_paginados = filtradas[offset:offset + limit]
    total_paginas = max(1, (total_registros + limit - 1) // limit) if total_registros > 0 else 1

    return HistorialOrdenesResponse(
        items=items_paginados,
        total=total_registros,
        pagina=page,
        limite=limit,
        total_paginas=total_paginas
    )

@router.get("/cliente/{cliente_id}", response_model=List[OrdenResponse])
async def listar_ordenes_cliente(
    cliente_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Lista pedidos del cliente autenticado; administradores pueden consultar cualquier cuenta."""
    role = str(current_user.get("role", "")).lower()
    user_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    if role not in {"cliente", "administrador", "gerente_comercial"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para consultar estos pedidos.")
    if role == "cliente" and user_id != str(cliente_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes consultar tus propios pedidos.")

    ordenes: Dict[str, OrdenResponse] = {
        str(orden.id): orden for orden in _ORDENES_DB.values()
        if str(orden.cliente_id) == str(cliente_id)
    }
    client = _get_supabase_safe()
    if client:
        try:
            rows = client.table("ordenes").select("id").eq("cliente_id", str(cliente_id)).order("created_at", desc=True).execute().data or []
            for row in rows:
                order_id = str(row["id"])
                ordenes[order_id] = await obtener_orden(uuid.UUID(order_id))
        except Exception as exc:
            logger.exception("No se pudieron cargar los pedidos del cliente %s", cliente_id)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudieron cargar tus pedidos.") from exc
    return sorted(ordenes.values(), key=lambda order: order.created_at, reverse=True)

@router.get("/{id}/comprobante.pdf", response_class=Response)
async def descargar_comprobante_pdf(id: uuid.UUID):
    """RF-27 / KAN-198: descargar el comprobante digital de una orden."""
    orden = await obtener_orden(id)
    return Response(
        content=generar_comprobante_pdf(orden),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="comprobante-{orden.codigo_orden}.pdf"'},
    )


@router.get("/{id}", response_model=OrdenResponse)
async def obtener_orden(id: uuid.UUID):
    """RF-29, RF-37: Detalle e historial de orden."""
    oid = str(id)
    client = _get_supabase_safe()
    if client:
        try:
            res = client.table("ordenes").select("*, orden_items(*)").eq("id", oid).limit(1).execute()
            if res.data:
                row = res.data[0]
                raw_items = row.get("orden_items") or []
                raw_payments = client.table("pagos").select("metodo,monto,estado,transaccion_id,raw_payload").eq("orden_id", oid).execute().data or []
                items_res = [
                    ItemOrdenResponse(
                        id=uuid.UUID(i["id"]) if isinstance(i["id"], str) else i["id"],
                        variante_id=uuid.UUID(i["variante_id"]) if isinstance(i["variante_id"], str) else i["variante_id"],
                        sku=i["sku"],
                        nombre_producto=i["nombre_producto"],
                        cantidad=i["cantidad"],
                        precio_unitario=Decimal(str(i["precio_unitario"])),
                        total_linea=Decimal(str(i.get("total_linea", i["cantidad"] * i["precio_unitario"])))
                    )
                    for i in raw_items
                ]
                payments_res = [
                    PagoProcesado(
                        metodo=p["metodo"],
                        monto=Decimal(str(p["monto"])),
                        estado=p.get("estado", "aprobado"),
                        transaccion_id=p.get("transaccion_id"),
                    )
                    for p in raw_payments
                ]
                return OrdenResponse(
                    id=uuid.UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
                    codigo_orden=row["codigo_orden"],
                    cliente_id=uuid.UUID(row["cliente_id"]) if isinstance(row["cliente_id"], str) else row["cliente_id"],
                    canal=row.get("canal", "web"),
                    tipo_despacho=row.get("tipo_despacho", "domicilio"),
                    subtotal=Decimal(str(row["subtotal"])),
                    descuento=Decimal(str(row.get("descuento", 0))),
                    costo_envio=Decimal(str(row.get("costo_envio", 0))),
                    total=Decimal(str(row["total"])),
                    estado=row.get("estado", "confirmada"),
                    tracking_number=row.get("tracking_number"),
                    reserva_id=row.get("reserva_id"),
                    cuf_factura=row.get("cuf_factura"),
                    numero_factura=row.get("numero_factura"),
                    factura=(raw_payments[0].get("raw_payload") if raw_payments else None),
                    motivo_cancelacion=row.get("motivo_cancelacion"),
                    created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if "created_at" in row else datetime.utcnow(),
                    items=items_res,
                    pagos=payments_res,
                )
        except Exception as e:
            logger.warning(f"Error consultando orden en Supabase: {e}")

    if oid in _ORDENES_DB:
        return _ORDENES_DB[oid]
    raise HTTPException(status_code=404, detail="Orden no encontrada")

@router.patch("/{id}/estado", response_model=OrdenResponse)
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial", "cajero"})
async def cambiar_estado_orden(
    id: uuid.UUID,
    payload: TransicionEstadoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-28: Máquina de estados de la orden con auditoría de cada transición."""
    oid = str(id)
    if oid not in _ORDENES_DB:
        _ORDENES_DB[oid] = await obtener_orden(id)

    orden = _ORDENES_DB[oid]
    estado_actual = orden.estado
    nuevo_estado = payload.nuevo_estado.strip().lower()

    if nuevo_estado == "cancelada":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Para cancelar usa POST /api/v1/ordenes/{id}/cancelar: reingresa stock, revierte el asiento y el cobro.",
        )
    if nuevo_estado not in TRANSICIONES_VALIDAS.get(estado_actual, []):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Transición no permitida de '{estado_actual}' a '{nuevo_estado}'."
        )

    usuario_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    ahora = datetime.utcnow()
    client = _get_supabase_safe()
    if client:
        cambios = {
            "estado": nuevo_estado,
            "estado_actualizado_por": _uuid_db(usuario_id),
            "updated_at": ahora.isoformat(),
        }
        try:
            try:
                result = client.table("ordenes").update(cambios).eq("id", oid).eq("estado", estado_actual).select("id").execute()
            except Exception as e:
                # Databases without the 20261022 migration lack the audit column; keep transitions working.
                if "estado_actualizado_por" not in str(e):
                    raise
                cambios.pop("estado_actualizado_por")
                result = client.table("ordenes").update(cambios).eq("id", oid).eq("estado", estado_actual).select("id").execute()
        except Exception as e:
            logger.exception("No se pudo guardar la transición de la orden %s", oid)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo guardar el cambio de estado.") from e
        if not result.data:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden cambió de estado mientras se procesaba. Recarga e inténtalo otra vez.")

    orden.estado = nuevo_estado
    orden.historial_estados.append({
        "estado_anterior": estado_actual,
        "estado_nuevo": nuevo_estado,
        "usuario_id": usuario_id,
        "rol": current_user.get("role"),
        "cambiado_en": ahora.isoformat(),
    })
    return orden

def _resena_response(row: Dict[str, Any]) -> ResenaResponse:
    return ResenaResponse(
        id=row["id"],
        producto_id=row["producto_id"],
        producto_nombre=row.get("producto_nombre"),
        producto_sku=row.get("producto_sku"),
        cliente_id=row["cliente_id"],
        orden_id=row.get("orden_id"),
        codigo_orden=row.get("codigo_orden"),
        nombre_cliente=row.get("nombre_cliente"),
        calificacion=int(row["calificacion"]),
        comentario=row["comentario"],
        estado_moderacion=row.get("estado_moderacion") or ("aprobada" if row.get("aprobada") else "pendiente"),
        motivo_rechazo=row.get("motivo_rechazo"),
        created_at=row.get("created_at") or datetime.utcnow(),
    )


def _require_customer(current_user: Dict[str, Any]) -> str:
    if str(current_user.get("role", "")).lower() != "cliente":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo un cliente puede enviar reseñas.")
    cliente_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    if not cliente_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La sesión no tiene un cliente asociado.")
    return cliente_id


def _variantes_de_producto(supabase: Any, producto_id: str) -> set[str]:
    variantes = {producto_id}
    if supabase:
        try:
            rows = supabase.table("variantes").select("id").eq("producto_id", producto_id).execute().data or []
            variantes.update(str(row["id"]) for row in rows)
        except Exception:
            logger.exception("No se pudieron consultar variantes del producto %s", producto_id)
    return variantes


def _orden_contiene_producto(orden: Any, variantes_producto: set[str]) -> bool:
    return any(str(item.variante_id) in variantes_producto for item in orden.items)


def _pedidos_entregados_cliente(cliente_id: str, producto_id: str) -> List[Dict[str, Any]]:
    supabase = get_supabase_admin_client()
    variantes_producto = _variantes_de_producto(supabase, producto_id)
    ordenes: Dict[str, Dict[str, Any]] = {}

    for orden in _ORDENES_DB.values():
        if str(orden.cliente_id) != cliente_id or orden.estado != "entregada":
            continue
        if _orden_contiene_producto(orden, variantes_producto):
            ordenes[str(orden.id)] = {
                "orden_id": str(orden.id),
                "codigo_orden": orden.codigo_orden,
                "entregada_el": orden.created_at,
            }

    if supabase:
        try:
            rows = supabase.table("ordenes").select("id,codigo_orden,cliente_id,estado,updated_at,created_at").eq("cliente_id", cliente_id).eq("estado", "entregada").execute().data or []
            ids = [str(row["id"]) for row in rows]
            if ids:
                delivered_items = supabase.table("orden_items").select("orden_id,variante_id").in_("orden_id", ids).in_("variante_id", list(variantes_producto)).execute().data or []
                eligible_order_ids = {str(item["orden_id"]) for item in delivered_items}
                for row in rows:
                    order_id = str(row["id"])
                    if order_id in eligible_order_ids:
                        ordenes[order_id] = {
                            "orden_id": order_id,
                            "codigo_orden": row["codigo_orden"],
                            "entregada_el": row.get("updated_at") or row.get("created_at") or datetime.utcnow(),
                        }
        except Exception:
            logger.exception("No se pudieron consultar órdenes entregadas para reseñas")

    reviewed = set()
    if supabase and ordenes:
        try:
            rows = supabase.table("resenas").select("orden_id").eq("cliente_id", cliente_id).eq("producto_id", producto_id).in_("orden_id", list(ordenes)).execute().data or []
            reviewed.update(str(row["orden_id"]) for row in rows)
        except Exception:
            logger.exception("No se pudieron consultar reseñas existentes")
    reviewed.update(
        str(row["orden_id"])
        for row in _RESENAS_DB.values()
        if str(row["cliente_id"]) == cliente_id and str(row["producto_id"]) == producto_id
    )
    return [row for order_id, row in ordenes.items() if order_id not in reviewed]


@router.get("/resenas/elegibles/{producto_id}", response_model=List[ResenaElegibleResponse])
async def listar_ordenes_elegibles_resena(
    producto_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    cliente_id = _require_customer(current_user)
    return _pedidos_entregados_cliente(cliente_id, str(producto_id))


@router.post("/resenas", response_model=ResenaResponse, status_code=status.HTTP_201_CREATED)
async def enviar_resena(
    payload: ResenaCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    cliente_id = _require_customer(current_user)
    orden_id = str(payload.orden_id)
    elegibles = {item["orden_id"] for item in _pedidos_entregados_cliente(cliente_id, str(payload.producto_id))}
    if orden_id not in elegibles:
        ya_existe = any(
            str(row["cliente_id"]) == cliente_id
            and str(row["producto_id"]) == str(payload.producto_id)
            and str(row["orden_id"]) == orden_id
            for row in _RESENAS_DB.values()
        )
        if ya_existe:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya enviaste una reseña para esta compra.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes reseñar productos de una orden entregada a tu cuenta.")

    nombre_cliente = current_user.get("nombre_completo")
    row = {
        "id": str(uuid.uuid4()),
        "producto_id": str(payload.producto_id),
        "cliente_id": cliente_id,
        "orden_id": orden_id,
        "calificacion": payload.calificacion,
        "comentario": payload.comentario.strip(),
        "aprobada": False,
        "estado_moderacion": "pendiente",
        "motivo_rechazo": None,
        "created_at": datetime.utcnow(),
    }
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            profile = supabase.table("perfiles_clientes").select("nombre_completo").eq("id", cliente_id).limit(1).execute().data or []
            row["nombre_cliente"] = profile[0]["nombre_completo"] if profile else nombre_cliente
            result = supabase.table("resenas").insert({key: value for key, value in row.items() if key not in {"nombre_cliente", "created_at"}}).execute()
            if result.data:
                row.update(result.data[0])
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya enviaste una reseña para esta compra.") from exc
            logger.exception("No se pudo persistir la reseña en Supabase")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo guardar la reseña.") from exc
    else:
        order = _ORDENES_DB.get(orden_id)
        row["codigo_orden"] = order.codigo_orden if order else None
        row["nombre_cliente"] = nombre_cliente

    _RESENAS_DB[row["id"]] = row
    return _resena_response(row)


@router.get("/resenas/producto/{producto_id}", response_model=List[ResenaResponse])
async def listar_resenas_aprobadas(producto_id: uuid.UUID):
    supabase = get_supabase_admin_client()
    rows: List[Dict[str, Any]] = []
    if supabase:
        try:
            result = supabase.table("resenas").select("*").eq("producto_id", str(producto_id)).eq("estado_moderacion", "aprobada").order("created_at", desc=True).execute()
            rows = result.data or []
        except Exception:
            logger.exception("No se pudieron leer reseñas aprobadas")
    rows_by_id = {str(row["id"]): row for row in rows}
    rows_by_id.update({str(row["id"]): row for row in _RESENAS_DB.values() if str(row["producto_id"]) == str(producto_id) and row["estado_moderacion"] == "aprobada"})
    return [_resena_response(row) for row in rows_by_id.values()]


@router.get("/resenas/pendientes", response_model=List[ResenaResponse])
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def listar_resenas_pendientes(current_user: Dict[str, Any] = Depends(get_current_user)):
    supabase = get_supabase_admin_client()
    rows: List[Dict[str, Any]] = []
    if supabase:
        try:
            result = supabase.table("resenas").select("*").eq("estado_moderacion", "pendiente").order("created_at", desc=True).execute()
            rows = result.data or []
            client_ids = list({str(row["cliente_id"]) for row in rows})
            product_ids = list({str(row["producto_id"]) for row in rows})
            order_ids = list({str(row["orden_id"]) for row in rows if row.get("orden_id")})
            profiles = supabase.table("perfiles_clientes").select("id,nombre_completo").in_("id", client_ids).execute().data or [] if client_ids else []
            products = supabase.table("productos").select("id,nombre,sku").in_("id", product_ids).execute().data or [] if product_ids else []
            orders = supabase.table("ordenes").select("id,codigo_orden").in_("id", order_ids).execute().data or [] if order_ids else []
            profiles_by_id = {str(row["id"]): row["nombre_completo"] for row in profiles}
            products_by_id = {str(row["id"]): row for row in products}
            orders_by_id = {str(row["id"]): row["codigo_orden"] for row in orders}
            for row in rows:
                product = products_by_id.get(str(row["producto_id"]), {})
                row["producto_nombre"] = product.get("nombre")
                row["producto_sku"] = product.get("sku")
                row["nombre_cliente"] = profiles_by_id.get(str(row["cliente_id"]))
                row["codigo_orden"] = orders_by_id.get(str(row.get("orden_id")))
        except Exception:
            logger.exception("No se pudieron listar reseñas pendientes")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudieron cargar las reseñas pendientes.")
    rows_by_id = {str(row["id"]): row for row in rows}
    rows_by_id.update({str(row["id"]): row for row in _RESENAS_DB.values() if row["estado_moderacion"] == "pendiente"})
    return [_resena_response(row) for row in rows_by_id.values()]


@router.patch("/resenas/{resena_id}/moderacion", response_model=ResenaResponse)
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def moderar_resena(
    resena_id: uuid.UUID,
    payload: ModeracionResenaRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if payload.accion == "rechazar" and not (payload.motivo or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Indica el motivo para rechazar la reseña.")
    estado = "aprobada" if payload.accion == "aprobar" else "rechazada"
    motivo = payload.motivo.strip() if payload.accion == "rechazar" and payload.motivo else None
    key = str(resena_id)
    row = _RESENAS_DB.get(key)
    supabase = get_supabase_admin_client()
    if supabase:
        try:
            result = supabase.table("resenas").update({
                "aprobada": estado == "aprobada",
                "estado_moderacion": estado,
                "motivo_rechazo": motivo,
            }).eq("id", key).eq("estado_moderacion", "pendiente").execute()
            if result.data:
                row = {**(row or {}), **result.data[0]}
        except Exception:
            logger.exception("No se pudo moderar la reseña %s", key)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No se pudo guardar la moderación.")
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reseña pendiente no encontrada.")
    if row.get("estado_moderacion") != "pendiente" and key not in _RESENAS_DB:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La reseña ya fue moderada.")
    row.update({"aprobada": estado == "aprobada", "estado_moderacion": estado, "motivo_rechazo": motivo})
    _RESENAS_DB[key] = row
    return _resena_response(row)

def _construir_saga_reversion(orden: OrdenResponse, oid: str, motivo: str, client: Any = None) -> SagaOrchestrator:
    """
    RF-33: saga de reversión de una orden. Cada paso externo declara su compensación,
    de modo que si uno falla se deshacen los anteriores y ningún sistema queda a medias.
    """
    items = [{"sku": i.sku, "cantidad": i.cantidad, "nombre": i.nombre_producto} for i in orden.items]
    origen = "pos" if orden.canal == "pos" else "marketplace"
    orden_sucursal_id = getattr(orden, "sucursal_id", None)
    sucursal_id = str(orden_sucursal_id) if orden_sucursal_id else None
    saga = SagaOrchestrator("reversion_orden")

    # 1) RIO-INV-04: reingreso físico/lógico al almacén de origen.
    #    Compensación: volver a descontar el stock que se acababa de reingresar.
    saga.paso(
        "reingreso_stock",
        lambda: inventarios_client.reingreso_por_devolucion(
            oid,
            items,
            motivo=motivo,
            origen=origen,
            sucursal_id=sucursal_id,
        ),
        lambda _res: inventarios_client.descuento_directo(items, orden_id=f"UNDO-{oid}"),
    )

    # 2) RIO-CON-04: asiento contable de reversión (ingreso + costo de ventas) con el desglose por forma de pago.
    #    Compensación: volver a registrar el asiento de venta original (OrderPaidEvent).
    saga.paso(
        "reversion_contable",
        lambda: contabilidad_client.registrar_reversion({
            "orden_id": oid,
            "codigo_orden": orden.codigo_orden,
            "motivo": motivo,
            "monto_revertido": float(orden.total),
            "canal": orden.canal,
            "desglose_pagos": [
                {"metodo": p.metodo, "monto": float(p.monto), "transaccion_id": p.transaccion_id}
                for p in orden.pagos
            ],
            "items": items,
        }),
        lambda _res: publicar_order_paid_event(construir_order_paid_event(
            orden_id=oid, codigo_orden=orden.codigo_orden, canal=orden.canal,
            total=orden.total, pagos=orden.pagos,
        )),
    )

    # 3) RIO-PAG-03: reversión de cada cobro digital (el efectivo se reembolsa en caja, sin llamada externa).
    #    Compensación: volver a cobrar el tramo reversado.
    pagos_a_revertir = list(orden.pagos) or [
        PagoProcesado(metodo="tarjeta", monto=orden.total, transaccion_id=f"tx-{oid[:8]}")
    ]
    for indice, pago in enumerate(pagos_a_revertir, start=1):
        if pago.metodo == "efectivo":
            continue

        def _accion(p=pago):
            return pagos_client.reversar_cobro(transaccion_id=str(p.transaccion_id), monto=float(p.monto))

        def _compensacion(_res, p=pago):
            return pagos_client.procesar_cobro(float(p.monto), p.metodo)

        saga.paso(f"reversion_pago_{indice}_{pago.metodo}", _accion, _compensacion)

    async def guardar_cancelacion():
        if client:
            result = client.table("ordenes").update({
                "estado": "cancelada",
                "motivo_cancelacion": motivo,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", oid).eq("estado", orden.estado).select("id").execute()
            if not result.data:
                raise RuntimeError("La orden cambió de estado o no se pudo guardar la cancelación.")
        return {"status": "OK"}

    saga.paso("guardar_cancelacion", guardar_cancelacion)
    return saga


@router.post("/{id}/cancelar", response_model=OrdenResponse)
async def cancelar_orden(
    id: uuid.UUID,
    motivo: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    RF-31, RF-33: Cancelación pre-despacho con reversión contable e inventarial.

    Las tres comunicaciones externas (Inventarios, Contabilidad, Pagos) se ejecutan como
    una saga con transacciones compensatorias: la orden solo pasa a 'cancelada' si TODAS
    se completan; si alguna falla, se compensan las ya realizadas y la orden conserva su
    estado anterior (respondiendo 502 con el detalle de qué se compensó).
    """
    role = str(current_user.get("role", "")).lower()
    if role not in {"cliente", "administrador", "gerente_comercial"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para cancelar pedidos.")
    motivo = motivo.strip()
    if len(motivo) < 3 or len(motivo) > 240:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Indica un motivo de cancelación de 3 a 240 caracteres.")

    oid = str(id)
    if oid not in _ORDENES_DB:
        try:
            _ORDENES_DB[oid] = await obtener_orden(id)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise
            raise

    orden = _ORDENES_DB[oid]
    user_id = str(current_user.get("user_id") or current_user.get("sub") or "")
    if role == "cliente" and user_id != str(orden.cliente_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes cancelar tus propios pedidos.")
    if orden.estado == "cancelada":
        # Idempotencia: cancelar dos veces reingresaría el stock y revertiría el asiento dos veces.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden ya fue cancelada.")
    if "cancelada" not in TRANSICIONES_VALIDAS.get(orden.estado, []):
        raise HTTPException(status_code=400, detail="No es posible cancelar una orden que ya fue despachada o entregada")

    client = _get_supabase_safe()
    resultado = await _construir_saga_reversion(orden, oid, motivo, client).ejecutar()
    orden.reversion = resultado.a_dict()

    if not resultado.exitosa:
        logger.error("Reversión de la orden %s fallida y compensada: %s", oid, resultado.error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "mensaje": "No se pudo completar la reversión; la orden NO fue cancelada.",
                "orden_estado": orden.estado,
                "reversion": orden.reversion,
            },
        )

    orden.estado = "cancelada"
    orden.motivo_cancelacion = motivo
    if orden.reserva_id:
        try:
            await liberar_reserva_stock(orden.reserva_id)
        except Exception as e:
            logger.warning("No se pudo liberar la reserva %s tras cancelar la orden %s: %s", orden.reserva_id, oid, e)
            orden.reversion["error_liberacion_reserva"] = str(e)

    return orden


# ------------------------------------------------------------------------------
# KAN-56 / US-40 (RF-40): PANEL DE SINCRONIZACIÓN CON PUB/SUB
# ------------------------------------------------------------------------------

def _resultado_pubsub(evento: Dict[str, Any]) -> Dict[str, Any]:
    publicado = evento.get("status") == "PUBLICADO"
    return {
        "ok": publicado,
        "mensaje": (
            "Google Pub/Sub aceptó el mensaje."
            if publicado
            else "El mensaje quedó en modo offline y no se publicó en Google Cloud."
        ),
        "evento": evento,
    }


@router.get("/integraciones/pubsub/status")
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def estado_integracion_pubsub(current_user: Dict[str, Any] = Depends(get_current_user)):
    credential_path = pubsub_client._resolve_credentials_path()
    return {
        "projectId": pubsub_client.project_id,
        "topic": pubsub_client.topic_name,
        "hasCredentialsFile": bool(credential_path),
        "credentialsPath": "service-account.json" if credential_path else None,
        "mode": "ONLINE" if credential_path else "OFFLINE",
        "totalEventsLogged": len(EVENTOS_PUBSUB_LOG),
    }


@router.get("/integraciones/pubsub/historial")
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def historial_integracion_pubsub(current_user: Dict[str, Any] = Depends(get_current_user)):
    eventos = list(reversed(EVENTOS_PUBSUB_LOG[-50:]))
    return {"total": len(EVENTOS_PUBSUB_LOG), "eventos": eventos}


@router.post("/integraciones/pubsub/test")
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def publicar_prueba_pubsub(
    payload: PubSubPruebaRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    evento = await pubsub_client.publicar_mensaje_test(payload.responsable, payload.detalle)
    return _resultado_pubsub(evento)


@router.post("/integraciones/pubsub/descuento-stock")
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def publicar_descuento_pubsub(
    payload: PubSubMovimientoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    evento = await pubsub_client.publicar_descuento_stock(
        orden_id=payload.orden_id,
        items=[item.model_dump() for item in payload.items],
        origen=payload.origen,
        sucursal_id=payload.sucursal_id,
        reserva_id=payload.reserva_id,
    )
    return _resultado_pubsub(evento)


@router.post("/integraciones/pubsub/reintegro-stock")
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def publicar_reintegro_pubsub(
    payload: PubSubMovimientoRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    evento = await pubsub_client.publicar_reintegro_stock(
        orden_id=payload.orden_id,
        items=[item.model_dump() for item in payload.items],
        motivo=payload.motivo or "prueba_reintegro",
        origen=payload.origen,
        sucursal_id=payload.sucursal_id,
    )
    return _resultado_pubsub(evento)

# ------------------------------------------------------------------------------
# COTIZACIONES B2B (RF-34, RF-35, RF-36)
# ------------------------------------------------------------------------------
@router.post("/cotizaciones", response_model=CotizacionB2BResponse, status_code=status.HTTP_201_CREATED)
async def crear_cotizacion(payload: CotizacionB2BCreate):
    """RF-34: Emisión de cotización corporativa B2B."""
    cot_id = uuid.uuid4()
    codigo = f"COT-B2B-{uuid.uuid4().hex[:6].upper()}"
    subtotal = sum(i.cantidad * i.precio_unitario for i in payload.items)
    descuento = subtotal * (payload.descuento_porcentaje / Decimal("100"))
    total = subtotal - descuento

    cotizacion = CotizacionB2BResponse(
        id=cot_id,
        codigo_cotizacion=codigo,
        cliente_id=payload.cliente_id,
        total=total,
        vigencia_hasta=payload.vigencia_hasta,
        estado="borrador" if payload.descuento_porcentaje <= 10 else "pendiente_aprobacion",
        items=payload.items
    )
    _COTIZACIONES_DB[str(cot_id)] = cotizacion
    return cotizacion

@router.post("/cotizaciones/{id}/aprobar", response_model=CotizacionB2BResponse)
@require_jwt_claims("sub", allowed_roles={"administrador", "gerente_comercial"})
async def aprobar_cotizacion(
    id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """RF-35: Aprobación jerárquica de cotización B2B."""
    cid = str(id)
    if cid not in _COTIZACIONES_DB:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    cot = _COTIZACIONES_DB[cid]
    cot.estado = "aprobada"
    return cot


# ==============================================================================
# RF-15 / US-15 / KAN-31: SELECCIÓN ENTRE ENVÍO A DOMICILIO O RETIRO EN SUCURSAL
# SUBTAREAS:
# - [BE] Algoritmo de cálculo de costo de flete según zona y dirección de entrega
# - [BE] Endpoint de consulta de sucursales habilitadas con stock para retiro
# ==============================================================================

# Tarifas base de flete por ciudad y zona en Bolivia (BOB)
TARIFAS_FLETE_ZONA: Dict[str, Dict[str, Decimal]] = {
    "la paz": {
        "centro": Decimal("15.0"),
        "miraflores": Decimal("15.0"),
        "sopocachi": Decimal("15.0"),
        "san pedro": Decimal("15.0"),
        "zona sur (calacoto / san miguel)": Decimal("20.0"),
        "achumani / irpavi / cota cota": Decimal("22.0"),
        "periférica / laderas": Decimal("25.0"),
        "default": Decimal("18.0")
    },
    "el alto": {
        "ceja": Decimal("20.0"),
        "ciudad satélite": Decimal("22.0"),
        "villa adela": Decimal("25.0"),
        "rio seco": Decimal("28.0"),
        "default": Decimal("25.0")
    },
    "santa cruz": {
        "1er a 4to anillo": Decimal("18.0"),
        "equipetrol": Decimal("18.0"),
        "urubó": Decimal("28.0"),
        "5to a 8vo anillo": Decimal("25.0"),
        "plan 3000": Decimal("28.0"),
        "default": Decimal("22.0")
    },
    "cochabamba": {
        "centro / el prado": Decimal("15.0"),
        "cala cala / recoleta": Decimal("18.0"),
        "zona sur": Decimal("22.0"),
        "sacaba / quillacollo": Decimal("30.0"),
        "default": Decimal("18.0")
    },
    "nacional": {
        "sucre": Decimal("35.0"),
        "tarija": Decimal("35.0"),
        "oruro": Decimal("30.0"),
        "potosi": Decimal("35.0"),
        "beni": Decimal("45.0"),
        "pando": Decimal("50.0"),
        "default": Decimal("35.0")
    }
}

UMBRAL_FLETE_GRATIS = Decimal("500.0") # Flete 100% bonificado en compras >= 500 BOB

# Catálogo georreferenciado de sucursales habilitadas con inventario físico
SUCURSALES_RETIRO_DATA: List[Dict[str, Any]] = [
    {
        "id": "suc-lpz-01",
        "nombre": "Sucursal Central El Prado",
        "ciudad": "La Paz",
        "departamento": "La Paz",
        "direccion": "Av. 16 de Julio (El Prado) #1490, Edificio Alameda PB",
        "telefono": "+591 2 2441122",
        "horario_atencion": "Lunes a Viernes 08:30 - 20:00 | Sábado 09:00 - 18:00",
        "coordenadas": {"lat": -16.5028, "lng": -68.1328},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "A media cuadra de la Plaza del Estudiante",
        "es_habilitada": True
    },
    {
        "id": "suc-lpz-02",
        "nombre": "Sucursal Calacoto Zona Sur",
        "ciudad": "La Paz",
        "departamento": "La Paz",
        "direccion": "Calle 15 esq. Av. Ballivián #802, Torre Ketal",
        "telefono": "+591 2 2795500",
        "horario_atencion": "Lunes a Sábado 09:00 - 21:00 | Domingo 10:00 - 16:00",
        "coordenadas": {"lat": -16.5385, "lng": -68.0837},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "Frente a la Iglesia de San Miguel",
        "es_habilitada": True
    },
    {
        "id": "suc-alt-01",
        "nombre": "Sucursal Ciudad Satélite",
        "ciudad": "El Alto",
        "departamento": "La Paz",
        "direccion": "Av. Satélite #310, frente a la estación Plateada de Mi Teleférico",
        "telefono": "+591 2 2819933",
        "horario_atencion": "Lunes a Sábado 08:30 - 19:30",
        "coordenadas": {"lat": -16.5204, "lng": -68.1633},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 3 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "A pasos de la estación de teleférico Plateada",
        "es_habilitada": True
    },
    {
        "id": "suc-scz-01",
        "nombre": "Sucursal Equipetrol Norte",
        "ciudad": "Santa Cruz",
        "departamento": "Santa Cruz",
        "direccion": "Av. San Martín #1550 esq. Calle 5 Oeste",
        "telefono": "+591 3 3428800",
        "horario_atencion": "Lunes a Sábado 09:00 - 21:00 | Domingo 11:00 - 18:00",
        "coordenadas": {"lat": -17.7682, "lng": -63.1932},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "Diagonal al Hotel Los Tajibos",
        "es_habilitada": True
    },
    {
        "id": "suc-scz-02",
        "nombre": "Sucursal Ventura Mall",
        "ciudad": "Santa Cruz",
        "departamento": "Santa Cruz",
        "direccion": "4to Anillo esq. Av. San Martín, Nivel 1 Local 114",
        "telefono": "+591 3 3887766",
        "horario_atencion": "Lunes a Domingo 10:00 - 22:00 (Horario Mall)",
        "coordenadas": {"lat": -17.7548, "lng": -63.1993},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "Ingreso principal pasillo tecnológico",
        "es_habilitada": True
    },
    {
        "id": "suc-cbb-01",
        "nombre": "Sucursal Plaza Colón",
        "ciudad": "Cochabamba",
        "departamento": "Cochabamba",
        "direccion": "Calle San Martín esq. Av. Heroínas #320",
        "telefono": "+591 4 4256677",
        "horario_atencion": "Lunes a Viernes 08:30 - 19:30 | Sábado 09:00 - 14:00",
        "coordenadas": {"lat": -17.3935, "lng": -66.1568},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "A una cuadra de la Plaza Colón",
        "es_habilitada": True
    },
    {
        "id": "suc-cbb-02",
        "nombre": "Sucursal Cala Cala",
        "ciudad": "Cochabamba",
        "departamento": "Cochabamba",
        "direccion": "Av. América esq. Av. Libertador Bolívar #780",
        "telefono": "+591 4 4481199",
        "horario_atencion": "Lunes a Sábado 09:00 - 20:00",
        "coordenadas": {"lat": -17.3756, "lng": -66.1624},
        "stock_disponible": True,
        "tiempo_preparacion": "Listo para retiro en 2 horas",
        "costo_retiro": Decimal("0.0"),
        "referencia": "Frente al Boulevard Recoleta",
        "es_habilitada": True
    }
]


@router.post("/flete/calcular", response_model=CalculoFleteResponse)
@router.post("/logistica/flete/calcular", response_model=CalculoFleteResponse)
async def calcular_costo_flete(payload: CalculoFleteRequest):
    """
    US-15 / RF-15 / KAN-31 (Subtarea 1):
    Algoritmo de cálculo de costo de flete según zona y dirección de entrega.
    Aplica matrices por departamento/zona, ponderación por peso, recargo express y bonificación por ticket.
    """
    ciudad_norm = payload.ciudad.lower().strip()
    zona_norm = payload.zona.lower().strip()

    # 1. Determinar costo base según matriz
    tarifas_ciudad = TARIFAS_FLETE_ZONA.get(ciudad_norm)
    if not tarifas_ciudad:
        # Fallback nacional
        tarifas_ciudad = TARIFAS_FLETE_ZONA["nacional"]

    costo_base = tarifas_ciudad.get(zona_norm)
    if costo_base is None:
        costo_base = tarifas_ciudad.get("default", Decimal("20.0"))

    # 2. Recargo por sobrepeso (> 5kg: +5 BOB por kg adicional)
    recargo_peso = Decimal("0.0")
    if payload.peso_estimado_kg > Decimal("5.0"):
        excedente = payload.peso_estimado_kg - Decimal("5.0")
        recargo_peso = excedente * Decimal("5.0")

    # 3. Recargo por modalidad express en el mismo día (+15 BOB)
    recargo_express = Decimal("15.0") if payload.tipo_envio == "express_mismo_dia" else Decimal("0.0")

    costo_total_original = costo_base + recargo_peso + recargo_express

    # 4. Regla de bonificación comercial: flete gratis si subtotal >= 500 BOB
    es_gratis = payload.subtotal_productos >= UMBRAL_FLETE_GRATIS
    costo_final = Decimal("0.0") if es_gratis else costo_total_original

    # Tiempo de entrega estimado
    if payload.tipo_envio == "express_mismo_dia":
        tiempo_est = "Entrega HOY mismo (en menos de 4 horas hábiles)"
    elif ciudad_norm in ["la paz", "el alto", "santa cruz", "cochabamba"]:
        tiempo_est = "Entrega en 24 horas hábiles"
    else:
        tiempo_est = "Entrega nacional en 48 a 72 horas hábiles"

    mensaje = (
        f"¡Flete GRATIS aplicado por compras mayores a {UMBRAL_FLETE_GRATIS} BOB!"
        if es_gratis else
        f"Costo de envío calculado: {costo_final:.2f} BOB ({tiempo_est})"
    )

    return CalculoFleteResponse(
        ciudad=payload.ciudad,
        zona=payload.zona,
        costo_flete=costo_final,
        costo_original=costo_total_original,
        flete_gratis=es_gratis,
        umbral_flete_gratis=UMBRAL_FLETE_GRATIS,
        tiempo_estimado=tiempo_est,
        tipo_envio=payload.tipo_envio,
        mensaje=mensaje,
        desglose={
            "tarifa_base_zona": float(costo_base),
            "recargo_peso": float(recargo_peso),
            "recargo_express": float(recargo_express),
            "descuento_promocion": float(costo_total_original) if es_gratis else 0.0,
            "distancia_estimada_km": 6.5,
            "subtotal_evaluado": float(payload.subtotal_productos)
        }
    )


@router.get("/sucursales/retiro", response_model=List[SucursalRetiroResponse])
@router.get("/sucursales/habilitadas-retiro", response_model=List[SucursalRetiroResponse])
async def listar_sucursales_retiro(ciudad: Optional[str] = None):
    """
    US-15 / RF-15 / KAN-31 (Subtarea 2):
    Endpoint de consulta de sucursales habilitadas con stock físico para retiro (Click & Collect).
    Incluye coordenadas GPS para renderizado de mapa interactivo, horario de atención y tiempo de preparación.
    """
    resultado = []
    filtro_ciudad = ciudad.lower().strip() if ciudad else None

    for s in SUCURSALES_RETIRO_DATA:
        if filtro_ciudad and filtro_ciudad not in s["ciudad"].lower() and filtro_ciudad != "todas":
            continue

        resultado.append(SucursalRetiroResponse(
            id=s["id"],
            nombre=s["nombre"],
            ciudad=s["ciudad"],
            departamento=s["departamento"],
            direccion=s["direccion"],
            telefono=s["telefono"],
            horario_atencion=s["horario_atencion"],
            coordenadas=CoordenadasSucursal(**s["coordenadas"]),
            stock_disponible=s["stock_disponible"],
            tiempo_preparacion=s["tiempo_preparacion"],
            costo_retiro=s["costo_retiro"],
            referencia=s.get("referencia"),
            es_habilitada=s["es_habilitada"]
        ))

    return resultado

