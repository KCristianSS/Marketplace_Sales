from decimal import Decimal
from typing import Dict
import hashlib
import json
import time
import httpx
from decimal import ROUND_HALF_UP
from fastapi import HTTPException
from jose import jwt, JWTError
from backend.shared.config import settings
from backend.shared.flete_config import obtener_configuracion, ConfiguracionFlete
from backend.shared.redis_client import consultar_reserva


def dinero(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def huella_items(items):
    lineas = sorted((str(i["variante_id"]), int(i["cantidad"]), str(dinero(i["precio_unitario"]))) for i in items)
    return hashlib.sha256(json.dumps(lineas).encode()).hexdigest()


def validar_cotizacion(token, reserva_id, cliente_id, verificar_vigencia=True):
    try:
        datos = jwt.decode(token or "", settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                           audience="cotizacion-flete", options={"verify_exp": verificar_vigencia})
        if datos.get("type") != "flete" or datos.get("reserva_id") != reserva_id or datos.get("cliente_id") != str(cliente_id):
            raise ValueError("Cotización ajena a esta reserva")
        return datos
    except (JWTError, ValueError, TypeError):
        raise HTTPException(409, "La cotización de envío no es válida o venció. Vuelve a cotizar antes de pagar.")


async def cotizar_flete(payload):
    ciudad = payload.ciudad.strip().lower()
    zona = payload.zona.strip().lower()
    actual = await obtener_configuracion()
    config = ConfiguracionFlete.model_validate(actual["configuracion"])
    destino = next((z for z in config.zonas if z.activa and z.ciudad.casefold() == ciudad.casefold()
                    and z.nombre.casefold() == zona.casefold()), None)
    if destino is None:
        raise HTTPException(422, "El destino seleccionado no tiene cobertura.")
    es_express = payload.tipo_envio == "express_mismo_dia"
    if (es_express and not destino.express_habilitado) or (not es_express and not destino.estandar_habilitado):
        raise HTTPException(422, "La modalidad seleccionada no está disponible para esta zona.")
    base = destino.tarifa_base
    subtotal = payload.subtotal_productos
    peso = payload.peso_estimado_kg
    descuento = Decimal("0")
    reserva = None
    if payload.reserva_id:
        reserva = await consultar_reserva(payload.reserva_id)
        if not reserva or reserva.get("status") != "ACTIVA":
            raise HTTPException(409, "La reserva de stock no está activa. Renueva el checkout.")
        if not payload.direccion or len(payload.direccion.strip()) < 5:
            raise HTTPException(422, "Completa la dirección de entrega (mínimo 5 caracteres).")
        items = reserva["items"]
        subtotal = sum((Decimal(str(i["precio_unitario"])) * int(i["cantidad"]) for i in items), Decimal("0"))
        # El peso por unidad es una estimación administrable mientras el catálogo no define pesos.
        peso = sum(int(i["cantidad"]) for i in items) * config.peso_estimado_por_unidad_kg
        if payload.cupon:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.post(f"{settings.MS_CARRITO_URL}/api/v1/carrito/validar-cupon",
                                                 json={"codigo": payload.cupon, "subtotal": float(subtotal)})
                    response.raise_for_status()
                    cupon = response.json()
                if not cupon.get("valido"):
                    raise HTTPException(422, cupon.get("mensaje", "El cupón no es válido."))
                descuento = dinero(cupon["descuento"])
            except (httpx.HTTPError, ValueError, KeyError):
                raise HTTPException(503, "No pudimos validar el cupón para cotizar el total. Intenta nuevamente.")
    recargo_peso = max(Decimal("0"), peso - config.peso_incluido_kg) * config.recargo_por_kg
    express = config.recargo_express if es_express else Decimal("0")
    original = dinero(base + recargo_peso + express)
    # Umbral tras cupón y antes de canjear puntos.
    gratis = config.envio_gratis_habilitado and subtotal - descuento >= config.umbral_envio_gratis
    costo = Decimal("0.00") if gratis else original
    tiempo = destino.plazo_express if es_express else destino.plazo_estandar
    puntos = Decimal(payload.puntos_canjeados) * Decimal(str(settings.FIDELIDAD_VALOR_PUNTO_BOB))
    if puntos > max(Decimal("0"), subtotal - descuento):
        raise HTTPException(422, "El descuento de puntos supera el valor de los productos.")
    total = dinero(max(Decimal("0"), subtotal - descuento - puntos) + costo)
    resultado = dict(ciudad=destino.ciudad, zona=destino.nombre, costo_flete=costo,
        costo_original=original, flete_gratis=gratis, umbral_flete_gratis=config.umbral_envio_gratis,
        tiempo_estimado=tiempo, tipo_envio=payload.tipo_envio, moneda="BOB", total=total,
        mensaje="Flete gratis" if gratis else f"Costo de envío: BOB {costo:.2f}",
        desglose=dict(tarifa_base_zona=float(base), recargo_peso=float(recargo_peso),
            recargo_express=float(express), descuento_promocion=float(original) if gratis else 0,
            subtotal_evaluado=float(subtotal - descuento), peso_estimado_kg=float(peso)))
    if reserva:
        expira = min(time.time() + 900, reserva["expires_at"])
        datos = dict(configuracion_version=actual["version"], zona_id=str(destino.id), type="flete", aud="cotizacion-flete", exp=expira,
            reserva_id=payload.reserva_id, cliente_id=str(reserva["cliente_id"]),
            items=huella_items(reserva["items"]), subtotal=str(dinero(subtotal)),
            descuento=str(dinero(descuento + puntos)), total=str(total), costo_flete=str(costo),
            ciudad=resultado["ciudad"], zona=resultado["zona"], direccion=payload.direccion.strip(),
            referencia=payload.referencia or "", tipo_envio=payload.tipo_envio,
            tiempo_estimado=tiempo, moneda="BOB")
        resultado.update(cotizacion_flete=jwt.encode(datos, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM), expira_en=expira)
    from backend.shared.envios_eventos import encolar_cotizacion
    await encolar_cotizacion(payload, resultado, subtotal=subtotal, descuento=descuento, puntos=puntos,
                            configuracion_version=actual["version"], config=config)
    return resultado
