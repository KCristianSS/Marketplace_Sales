"""Preparación de recompra; catálogo por HTTP e inventario por el adaptador RIO."""
import asyncio
from decimal import Decimal

import httpx
from fastapi import HTTPException

try:
    from app.schemas import OrdenResponse, ItemRecompraResponse, RecompraResponse
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app.schemas import OrdenResponse, ItemRecompraResponse, RecompraResponse
from backend.shared.config import settings
from backend.shared.erp_clients.inventarios import inventarios_client


async def preparar_recompra(orden: OrdenResponse) -> RecompraResponse:
    resultado = RecompraResponse(orden_id=orden.id)
    if not orden.items:
        resultado.avisos.append("El pedido no tiene productos para repetir.")
        return resultado

    # No se reutilizan precios históricos ni se importa código de otro servicio.
    try:
        async with httpx.AsyncClient(base_url=settings.MS_CATALOGO_URL, timeout=10.0) as client:
            respuesta = await client.get("/api/v1/catalogo/productos", params={"estado": "publicado"})
            respuesta.raise_for_status()
            productos = respuesta.json()
            candidatos = []
            for item in orden.items:
                coincidencia = None
                for producto in productos:
                    if producto["estado"] != "publicado":
                        continue
                    variantes = producto.get("variantes") or []
                    variante = next((v for v in variantes if v["id"] == str(item.variante_id)), None)
                    # Compatibilidad con órdenes antiguas del marketplace (ID del producto).
                    if variante is None and producto["id"] == str(item.variante_id):
                        variante = next((v for v in variantes if v["sku"] == item.sku), None)
                        if variante is None and producto["sku"] == item.sku and len(variantes) == 1:
                            variante = variantes[0]
                    if variante:
                        coincidencia = (producto, variante)
                        break
                if coincidencia is None:
                    resultado.avisos.append(f"{item.nombre_producto} ({item.sku}): ya no está disponible en el catálogo.")
                else:
                    candidatos.append((item, *coincidencia))

            precios = {}
            ids = list(dict.fromkeys(v["id"] for _, _, v in candidatos))
            for inicio in range(0, len(ids), 200):
                respuesta = await client.get("/api/v1/catalogo/precios/resolver-lote", params={
                    "variante_ids": ",".join(ids[inicio:inicio + 200]), "canal": "web", "tipo_cliente": "retail",
                })
                respuesta.raise_for_status()
                precios.update(respuesta.json())

            for item, producto, variante in candidatos:
                tarifa = precios[variante["id"]]
                precio = Decimal(str(tarifa["precio"]))
                if tarifa.get("moneda") != "BOB":
                    resultado.avisos.append(f"{item.nombre_producto}: no tiene un precio vigente en bolivianos.")
                    continue
                if not precio.is_finite() or precio < 0:
                    raise ValueError("Precio de catálogo inválido")
                sku = item.sku if item.sku in {producto["sku"], variante["sku"]} else variante["sku"]
                resultado.items.append(ItemRecompraResponse(
                    variante_id=variante["id"], variante_original_id=item.variante_id,
                    sku=sku, nombre=producto["nombre"], cantidad=item.cantidad,
                    precio_unitario=precio, stock_disponible=0,
                ))
                if precio != item.precio_unitario:
                    resultado.avisos.append(f"{producto['nombre']} ({sku}): el precio actual es Bs. {precio:.2f} (antes Bs. {item.precio_unitario:.2f}).")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar el catálogo y los precios actuales. Inténtalo nuevamente.") from exc

    # Una consulta por SKU, incluso si varias líneas comparten inventario.
    limite = asyncio.Semaphore(8)

    async def consultar(sku):
        async with limite:
            try:
                stock = await inventarios_client.consultar_disponibilidad(sku)
                cantidad = stock["stock_disponible"]
                if type(cantidad) is not int or cantidad < 0:
                    return sku, None
                return sku, cantidad
            except Exception:
                return sku, None

    stock_por_sku = dict(await asyncio.gather(*(consultar(sku) for sku in dict.fromkeys(i.sku for i in resultado.items))))
    disponibles = []
    for item in resultado.items:
        stock = stock_por_sku[item.sku]
        if stock is None:
            resultado.avisos.append(f"{item.nombre} ({item.sku}): no pudimos verificar su stock; no se agregó.")
        elif stock == 0:
            resultado.avisos.append(f"{item.nombre} ({item.sku}): está agotado; no se agregó.")
        else:
            item.stock_disponible = stock
            disponibles.append(item)
    resultado.items = disponibles
    return resultado
