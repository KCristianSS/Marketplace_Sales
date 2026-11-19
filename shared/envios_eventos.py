"""Cotizaciones de demostración y auditoría persistente de mensajería de Entregas."""
import asyncio
import logging
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client

logger = logging.getLogger("uvicorn.error.envios")


def registrar_mensaje(envelope, atributos, estado, *, direccion="salida", message_id=None, error=None, topic=None):
    client = get_supabase_admin_client()
    if client is None:
        raise RuntimeError("Se requiere Supabase para conservar la trazabilidad de envíos.")
    payload = envelope.get("payload") or {}
    raw_order = payload.get("orden_id")
    row = dict(event_id=envelope["event_id"], tipo_evento=envelope["event_type"],
        direccion=direccion, estado=estado, orden_id=str(UUID(str(raw_order))) if raw_order else None,
        correlation_id=envelope.get("correlation_id"), simulacion=payload.get("simulacion") is True,
        topic=topic or (settings.PUBSUB_TOPIC_ENTREGAS if direccion == "salida" else settings.PUBSUB_TOPIC_RESPUESTAS_ENTREGAS),
        message_id=message_id, ultimo_error=error, mensaje=envelope, atributos=atributos,
        estado_logistico=payload.get("estado"))
    client.table("envios_mensajes_log").insert(row).execute()


def operar_cotizacion(accion, **datos):
    client = get_supabase_admin_client()
    if client is None:
        raise RuntimeError("No está disponible la cola de cotizaciones de envío.")
    return client.rpc("operar_cotizacion_envio", {"p_accion": accion, "p_datos": datos}).execute().data


async def encolar_cotizacion(payload, resultado, *, subtotal, descuento, puntos, configuracion_version, config):
    if not settings.PUBSUB_COTIZACIONES_SIMULACION_ENABLED:
        return
    cotizacion_id = str(uuid4())
    # Solo datos del cálculo: no enviar el JWT firmado, el cupón ni datos personales.
    calculo = {k: v for k, v in resultado.items() if k not in {"cotizacion_flete", "expira_en"}}
    from fastapi.encoders import jsonable_encoder
    evento = jsonable_encoder(dict(version_contrato=1, simulacion=True, cotizacion_id=cotizacion_id,
        reserva_id=payload.reserva_id, origen_calculo="maxiconecta.ventas",
        configuracion_version=configuracion_version,
        entradas=dict(ciudad=resultado["ciudad"], zona=resultado["zona"], tipo_envio=payload.tipo_envio,
            subtotal_productos=subtotal, descuento_cupon=descuento, descuento_puntos=puntos,
            peso_estimado_kg=resultado["desglose"]["peso_estimado_kg"],
            peso_incluido_kg=config.peso_incluido_kg, recargo_por_kg=config.recargo_por_kg),
        formulas=dict(flete="tarifa_base_zona + max(0, peso_estimado_kg - peso_incluido_kg) * recargo_por_kg + recargo_express - descuento_promocion",
            total="subtotal_productos - descuento_cupon - descuento_puntos + costo_flete"),
        calculo=calculo))
    try:
        await asyncio.to_thread(operar_cotizacion, "encolar", id=cotizacion_id, payload=evento)
        logger.info("[PubSub] COTIZACION ENCOLADA event_id=%s simulacion=true costo_flete=%s total=%s",
                    cotizacion_id, resultado["costo_flete"], resultado["total"])
    except Exception:
        # La demostración no debe impedir cotizar ni modificar el importe comercial.
        logger.exception("No se pudo encolar la cotización simulada event_id=%s", cotizacion_id)


async def publicar_cotizaciones_pendientes():
    if not settings.PUBSUB_COTIZACIONES_SIMULACION_ENABLED:
        return 0
    from backend.shared.pubsub_client import GooglePubSubClient
    lote = await asyncio.to_thread(operar_cotizacion, "reclamar")
    publisher = GooglePubSubClient(topic_name=settings.PUBSUB_TOPIC_ENTREGAS)
    for evento in lote.get("eventos", []):
        message_id, error = None, None
        try:
            publicado = await publisher.publish_event("despacho.cotizacion.calculada", evento["payload"],
                attributes={"destino": "entregas", "version_contrato": "1", "simulacion": "true"},
                event_id=evento["id"], correlation_id=evento["id"], destination="entregas")
            if publicado.get("status") == "PUBLICADO" and not publicado.get("simulated"):
                message_id = publicado["message_id"]
            else:
                error = "Pub/Sub no confirmó el envío de la cotización simulada."
        except Exception:
            logger.exception("Error publicando cotización simulada event_id=%s", evento["id"])
            error = "No se pudo publicar la cotización simulada."
        await asyncio.to_thread(operar_cotizacion, "finalizar", id=evento["id"], lease_id=evento["lease_id"],
                                message_id=message_id, error=error)
    return len(lote.get("eventos", []))


def registrar_respuesta_cotizacion(envelope, *, atributos=None, message_id=None):
    payload = envelope["payload"]
    try:
        cotizacion_id = str(UUID(payload["cotizacion_id"]))
        UUID(envelope["event_id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Respuesta de cotización inválida.") from exc
    if (payload.get("simulacion") is not True or envelope.get("correlation_id") != cotizacion_id
            or payload.get("request_event_id") != cotizacion_id):
        raise ValueError("Respuesta de cotización sin correlación válida.")
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, "No se pudo guardar la respuesta de cotización.")
    try:
        rows = client.table("envios_cotizaciones_outbox").select("id").eq("id", cotizacion_id).limit(1).execute().data
        if not rows:
            raise ValueError("La respuesta no corresponde a una cotización conocida.")
        registrar_mensaje(envelope, atributos or {}, "recibido", direccion="entrada", message_id=message_id)
    except ValueError:
        raise
    except Exception as exc:
        raise HTTPException(503, "No se pudo guardar la respuesta de cotización.") from exc
    return {"recibido": True, "simulacion": True}
