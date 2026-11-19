"""Reglas de emisión y vencimiento de cotizaciones B2B (KAN-194)."""
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.shared.database import get_supabase_admin_client
from backend.shared.cotizaciones_config import obtener_configuracion_b2b, descuento_b2b
try:
    from app.schemas import CotizacionVolumenCreate, CotizacionVolumenItemResponse, CotizacionVolumenResponse
except ModuleNotFoundError:
    from backend.services.ordenes.app.schemas import CotizacionVolumenCreate, CotizacionVolumenItemResponse, CotizacionVolumenResponse

logger = logging.getLogger("maxiconecta.cotizaciones")
DIAS_VIGENCIA_PERMITIDOS = {7, 15, 30}


def _dinero(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def marcar_vencidas(client: Any, fecha_hoy: date | None = None) -> None:
    """Marca como vencidas las cotizaciones emitidas cuya fecha inclusiva ya pasó."""
    hoy = fecha_hoy or datetime.now(timezone(timedelta(hours=-4))).date()
    client.table("cotizaciones_b2b").update({
        "estado": "vencida", "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("estado", "emitida").lt("vigencia_hasta", hoy.isoformat()).execute()


async def worker_vencimiento_cotizaciones(stop_event, intervalo_segundos: int = 60) -> None:
    while not stop_event.is_set():
        client = get_supabase_admin_client()
        if client:
            try:
                import asyncio
                await asyncio.to_thread(marcar_vencidas, client)
            except Exception:
                logger.exception("No se pudieron marcar las cotizaciones vencidas")
        try:
            import asyncio
            await asyncio.wait_for(stop_event.wait(), timeout=intervalo_segundos)
        except asyncio.TimeoutError:
            pass


def cotizaciones_a_respuestas(client: Any, rows: List[Dict[str, Any]]) -> List[CotizacionVolumenResponse]:
    if not rows:
        return []
    quote_ids = [str(row["id"]) for row in rows]
    customer_ids = list({str(row["cliente_id"]) for row in rows})
    customers = client.table("perfiles_clientes").select("id,nombre_completo,razon_social,nit_ci").in_("id", customer_ids).execute().data or []
    items = client.table("cotizacion_items").select("cotizacion_id,variante_id,cantidad,precio_unitario,total_linea").in_("cotizacion_id", quote_ids).execute().data or []
    variant_ids = list({str(item["variante_id"]) for item in items})
    variants = client.table("variantes").select("id,sku,nombre_variante,producto_id").in_("id", variant_ids).execute().data or [] if variant_ids else []
    product_ids = list({str(item["producto_id"]) for item in variants if item.get("producto_id")})
    products = client.table("productos").select("id,nombre").in_("id", product_ids).execute().data or [] if product_ids else []
    customers_by_id = {str(row["id"]): row for row in customers}
    variants_by_id = {str(row["id"]): row for row in variants}
    products_by_id = {str(row["id"]): row for row in products}
    items_by_quote: Dict[str, List[CotizacionVolumenItemResponse]] = {}
    for item in items:
        variant = variants_by_id.get(str(item["variante_id"]), {})
        product = products_by_id.get(str(variant.get("producto_id")), {})
        item_name = product.get("nombre") or variant.get("nombre_variante") or variant.get("sku") or "Producto"
        if variant.get("nombre_variante") and variant.get("nombre_variante") != item_name:
            item_name = f"{item_name} · {variant['nombre_variante']}"
        items_by_quote.setdefault(str(item["cotizacion_id"]), []).append(CotizacionVolumenItemResponse(
            variante_id=UUID(str(item["variante_id"])),
            sku=variant.get("sku", ""),
            nombre_producto=item_name,
            cantidad=int(item["cantidad"]),
            precio_unitario=_dinero(item["precio_unitario"]),
            total_linea=_dinero(item["total_linea"]),
        ))
    respuestas = []
    for row in rows:
        customer = customers_by_id.get(str(row["cliente_id"]), {})
        vigencia = row["vigencia_hasta"]
        if isinstance(vigencia, str):
            vigencia = date.fromisoformat(vigencia[:10])
        created = row.get("created_at") or datetime.now(timezone.utc).isoformat()
        subtotal = _dinero(row.get("subtotal", 0))
        pct = _dinero(row.get("descuento_porcentaje", 0))
        total = _dinero(row.get("total", 0))
        respuestas.append(CotizacionVolumenResponse(
            id=UUID(str(row["id"])),
            codigo_cotizacion=row["codigo_cotizacion"],
            cliente_id=UUID(str(row["cliente_id"])),
            nombre_cliente=customer.get("nombre_completo") or "Cliente corporativo",
            razon_social=customer.get("razon_social"),
            nit_ci=customer.get("nit_ci") or "",
            gerente_id=UUID(str(row["gerente_id"])) if row.get("gerente_id") else None,
            subtotal=subtotal,
            descuento_porcentaje=pct,
            descuento_monto=_dinero(subtotal * pct / Decimal("100")),
            total=total,
            vigencia_dias=int(row.get("vigencia_dias") or 0),
            vigencia_hasta=vigencia,
            estado=row.get("estado", "emitida"),
            created_at=created,
            items=items_by_quote.get(str(row["id"]), []),
            configuracion_descuento_version=row.get("configuracion_descuento_version"),
        ))
    return respuestas


def emitir_cotizacion(client: Any, payload: CotizacionVolumenCreate, gerente_id: str) -> CotizacionVolumenResponse:
    if not payload.items:
        raise HTTPException(status_code=422, detail="Agrega al menos un producto para emitir la cotización.")
    if payload.vigencia_dias not in DIAS_VIGENCIA_PERMITIDOS:
        raise HTTPException(status_code=422, detail="La vigencia debe ser de 7, 15 o 30 días.")
    variant_ids = [str(item.variante_id) for item in payload.items]
    if len(set(variant_ids)) != len(variant_ids):
        raise HTTPException(status_code=422, detail="No repitas la misma variante; ajusta su cantidad en una sola línea.")

    profile_rows = client.table("perfiles_clientes").select("id,tipo_cliente,nit_ci").eq("id", str(payload.cliente_id)).limit(1).execute().data or []
    if not profile_rows:
        raise HTTPException(status_code=404, detail="No se encontró el cliente.")
    profile = profile_rows[0]
    if str(profile.get("tipo_cliente", "")).lower() != "corporativo_b2b" or not str(profile.get("nit_ci") or "").strip():
        raise HTTPException(status_code=422, detail="La cotización requiere un cliente corporativo con NIT registrado.")

    variant_rows = client.table("variantes").select("id,sku,nombre_variante,precio,producto_id").in_("id", variant_ids).execute().data or []
    by_id = {str(row["id"]): row for row in variant_rows}
    if len(by_id) != len(variant_ids):
        raise HTTPException(status_code=422, detail="Uno o más productos ya no están disponibles en el catálogo.")
    product_ids = list({str(row["producto_id"]) for row in variant_rows})
    product_rows = client.table("productos").select("id,nombre,estado").in_("id", product_ids).execute().data or []
    products = {str(row["id"]): row for row in product_rows}
    for variant in variant_rows:
        product = products.get(str(variant["producto_id"]))
        if not product or str(product.get("estado", "publicado")).lower() not in {"publicado", "activo"}:
            raise HTTPException(status_code=422, detail=f"El producto de SKU {variant.get('sku', '')} no está disponible para cotizar.")

    # Si existe una lista de precios B2B vigente, se toma su precio antes de aplicar la escala.
    b2b_lists = client.table("listas_precios").select("id").eq("canal", "b2b").eq("tipo_cliente", "corporativo_b2b").eq("activo", True).limit(1).execute().data or []
    prices_by_variant: Dict[str, Decimal] = {}
    if b2b_lists:
        now = datetime.now(timezone.utc).isoformat()
        price_rows = client.table("precios_items").select("variante_id,precio").eq("lista_precio_id", str(b2b_lists[0]["id"])).in_("variante_id", variant_ids).lte("fecha_inicio", now).or_(f"fecha_fin.is.null,fecha_fin.gte.{now}").execute().data or []
        prices_by_variant = {str(row["variante_id"]): _dinero(row["precio"]) for row in price_rows}

    total_unidades = sum(item.cantidad for item in payload.items)
    reglas = obtener_configuracion_b2b(client)
    if payload.configuracion_descuento_version is not None and payload.configuracion_descuento_version != reglas.version:
        raise HTTPException(409,"Las escalas de descuento cambiaron. Actualiza las reglas y revisa el estimado antes de emitir.")
    descuento_pct = descuento_b2b(total_unidades,reglas.configuracion)
    lines = []
    subtotal = Decimal("0")
    for item in payload.items:
        variant = by_id[str(item.variante_id)]
        price = prices_by_variant.get(str(item.variante_id), _dinero(variant["precio"]))
        line_total = _dinero(price * item.cantidad)
        subtotal += line_total
        lines.append({
            "variante_id": str(item.variante_id), "cantidad": item.cantidad,
            "precio_unitario": float(price), "total_linea": float(line_total),
        })
    subtotal = _dinero(subtotal)
    total = _dinero(subtotal * (Decimal("100") - descuento_pct) / Decimal("100"))
    today = datetime.now(timezone(timedelta(hours=-4))).date()
    valid_until = today + timedelta(days=payload.vigencia_dias)
    try:
        codigo_result = client.rpc("generar_codigo_cotizacion_b2b").execute().data
    except Exception as exc:
        logger.exception("No se pudo reservar el siguiente correlativo de cotización")
        raise HTTPException(status_code=503, detail="No se pudo generar el número correlativo de la cotización.") from exc
    codigo = codigo_result if isinstance(codigo_result, str) else (codigo_result[0] if isinstance(codigo_result, list) and codigo_result else None)
    if not codigo:
        raise HTTPException(status_code=503, detail="No se pudo generar el número correlativo de la cotización.")

    quote_id = str(uuid4())
    header = {
        "id": quote_id,
        "codigo_cotizacion": codigo,
        "cliente_id": str(payload.cliente_id),
        "gerente_id": gerente_id,
        "subtotal": float(subtotal),
        "descuento_porcentaje": float(descuento_pct),
        "total": float(total),
        "vigencia_dias": payload.vigencia_dias,
        "vigencia_hasta": valid_until.isoformat(),
        "estado": "emitida",
        "configuracion_descuento_version": reglas.version,
        "reglas_descuento": reglas.configuracion.model_dump(mode="json"),
    }
    try:
        inserted = client.table("cotizaciones_b2b").insert(header).execute().data or []
        if not inserted:
            raise RuntimeError("La cotización no se insertó.")
        client.table("cotizacion_items").insert([{**line, "cotizacion_id": quote_id} for line in lines]).execute()
    except Exception as exc:
        try:
            client.table("cotizaciones_b2b").delete().eq("id", quote_id).execute()
        except Exception:
            logger.exception("No se pudo revertir la cabecera parcial de cotización %s", quote_id)
        logger.exception("No se pudo persistir la cotización B2B %s", codigo)
        raise HTTPException(status_code=503, detail="No se pudo guardar la cotización; inténtalo nuevamente.") from exc
    stored = client.table("cotizaciones_b2b").select("*").eq("id", quote_id).limit(1).execute().data or [inserted[0]]
    from backend.shared.audit import registrar_auditoria
    registrar_auditoria(client, current_user={"user_id": gerente_id, "role": "gerente_comercial"},
        accion="COTIZACION_EMITIDA", entidad="cotizaciones_b2b", entidad_id=quote_id,
        despues={**stored[0], "items": lines})
    return cotizaciones_a_respuestas(client, stored)[0]
