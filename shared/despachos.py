"""Cola transaccional y recepción de RIO-ENT por Pub/Sub. Sin fallback monetario/logístico ficticio."""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client
from backend.shared.pubsub_client import GooglePubSubClient

logger = logging.getLogger("uvicorn.error.despachos")


def operar(accion: str, **datos):
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, "Los despachos requieren persistencia en Supabase.")
    try:
        res = client.rpc("operar_despacho", {"p_accion": accion, "p_datos": datos}).execute().data
    except Exception as exc:
        logger.warning("Falló el RPC de despachos (%s): %s", accion, type(exc).__name__)
        raise HTTPException(503, "No se pudo acceder a despachos. Verifica la migración y la conexión.")
    if not isinstance(res, dict):
        raise HTTPException(503, "Respuesta de persistencia de despachos inválida.")
    if res.get("error"):
        raise HTTPException(res.get("status", 409), res["error"])
    return res


class RespuestaEntrega(BaseModel):
    event_id: UUID
    event_type: Literal["despacho.generado", "despacho.rechazado", "despacho.estado.actualizado", "despacho.cancelado"]
    solicitud_id: UUID
    request_event_id: UUID
    orden_id: UUID
    version: int = Field(gt=0)
    estado: Literal["programado", "en_preparacion", "en_transito", "entregado", "rechazado", "cancelado"]
    guia: Optional[str] = Field(None, max_length=120)
    transportista: Optional[str] = Field(None, max_length=200)
    ruta: Optional[str] = Field(None, max_length=300)
    ubicacion_actual: Optional[str] = Field(None, max_length=300)
    motivo: Optional[str] = Field(None, max_length=500)
    fecha_estimada: Optional[datetime] = None

    @model_validator(mode="after")
    def coherencia(self):
        if self.event_type == "despacho.rechazado" and (self.estado != "rechazado" or not self.motivo):
            raise ValueError("El rechazo requiere estado rechazado y motivo.")
        if self.event_type == "despacho.cancelado" and self.estado != "cancelado":
            raise ValueError("La cancelación requiere estado cancelado.")
        if self.estado in {"programado", "en_preparacion", "en_transito", "entregado"} and not self.guia:
            raise ValueError("El estado logístico requiere una guía del ERP.")
        return self


def procesar_respuesta(envelope: dict, *, atributos=None, message_id=None):
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise ValueError("El mensaje de Entregas debe ser un objeto con payload estructurado.")
    if envelope.get("source") != "erp.entregas" or envelope.get("destination") != "maxiconecta":
        raise ValueError("Origen o destino de respuesta de Entregas inválido.")
    if envelope.get("event_type") == "despacho.cotizacion.recibida":
        from backend.shared.envios_eventos import registrar_respuesta_cotizacion
        return registrar_respuesta_cotizacion(envelope, atributos=atributos, message_id=message_id)
    payload = dict(envelope.get("payload") or {})
    payload.update(event_id=envelope.get("event_id"), event_type=envelope.get("event_type"))
    respuesta = RespuestaEntrega.model_validate(payload)
    if envelope.get("correlation_id") != str(respuesta.solicitud_id):
        raise ValueError("La correlación no corresponde al despacho.")
    resultado = operar("respuesta", **respuesta.model_dump(mode="json"))
    from backend.shared.envios_eventos import registrar_mensaje
    estado = "duplicado" if resultado.get("duplicado") else "aplicado" if resultado.get("aplicado") else "ignorado"
    if settings.ENVIRONMENT != "testing":
        try:
            registrar_mensaje(envelope, atributos or {}, estado, direccion="entrada", message_id=message_id)
        except Exception as exc:
            logger.exception("No se pudo guardar la trazabilidad de respuesta event_id=%s", envelope["event_id"])
            raise HTTPException(503, "No se pudo guardar la trazabilidad de la respuesta.") from exc
    logger.info("[PubSub] RESPUESTA RECIBIDA event_id=%s tipo=%s estado=%s orden_id=%s",
                envelope["event_id"], envelope["event_type"], estado, respuesta.orden_id)
    return resultado


async def publicar_pendientes():
    registros = await asyncio.to_thread(operar, "reclamar")
    publisher = GooglePubSubClient(topic_name=settings.PUBSUB_TOPIC_ENTREGAS)

    async def enviar(e):
        message_id, error = None, None
        try:
            payload = e["payload"]
            if e["tipo_evento"] == "despacho.solicitado":
                direccion = (payload.get("entrega") or {}).get("direccion", "")
                if not isinstance(direccion, str) or len(direccion.strip()) < 5 or not payload.get("items"):
                    raise ValueError("Faltan dirección de entrega o productos en la orden persistida.")
            res = await publisher.publish_event(e["tipo_evento"], payload,
                attributes={"destino": "entregas", "version_contrato": "1"},
                correlation_id=payload["solicitud_id"], event_id=e["id"], destination="entregas")
            if res.get("status") == "PUBLICADO" and not res.get("simulated"):
                message_id = res["message_id"]
            else:
                error = "Pub/Sub no confirmó la publicación; se reintentará automáticamente."
        except Exception as exc:
            error = str(exc) if isinstance(exc, ValueError) else "No se pudo publicar el mensaje de despacho."
        await asyncio.to_thread(operar, "finalizar", event_id=e["id"], lease_id=e["lease_id"],
                                message_id=message_id, error=error)
    await asyncio.gather(*(enviar(e) for e in registros.get("eventos", [])))
    return len(registros.get("eventos", []))


def crear_suscriptor():
    from google.cloud import pubsub_v1
    path = GooglePubSubClient()._resolve_credentials_path()
    if path and path != "__emulator__":
        return pubsub_v1.SubscriberClient.from_service_account_file(path)
    if os.getenv("PUBSUB_EMULATOR_HOST"):
        return pubsub_v1.SubscriberClient()
    raise RuntimeError("Configura las credenciales o el emulador de Pub/Sub.")


async def consumir_lote(subscriber, subscription: str):
    try:
        lote = await asyncio.to_thread(subscriber.pull, request={"subscription": subscription, "max_messages": 10}, timeout=5, retry=None)
    except Exception as exc:
        if type(exc).__name__ == "DeadlineExceeded":
            return
        raise
    for recibido in lote.received_messages:
        try:
            message = recibido.message
            # Una suscripción compartida no debe procesar las solicitudes de otros sistemas.
            if message.attributes.get("destino") == "maxiconecta":
                await asyncio.to_thread(procesar_respuesta, json.loads(message.data.decode("utf-8")),
                                        atributos=dict(message.attributes), message_id=message.message_id)
        except (ValueError, TypeError, UnicodeDecodeError):
            logger.warning("Respuesta de Entregas inválida descartada: %s", recibido.message.message_id)
        except HTTPException as exc:
            if exc.status_code >= 500:
                continue  # Sin ACK: la BD no confirmó la recepción, Pub/Sub debe reentregar.
            logger.warning("Respuesta de Entregas no correlacionada: %s", recibido.message.message_id)
        await asyncio.to_thread(subscriber.acknowledge, request={"subscription": subscription, "ack_ids": [recibido.ack_id]})


async def _publicador():
    while True:
        try:
            await publicar_pendientes()
        except Exception as exc:
            logger.warning("Publicador de despachos pendiente de conexión/configuración: %s", type(exc).__name__)
        try:
            from backend.shared.envios_eventos import publicar_cotizaciones_pendientes
            await publicar_cotizaciones_pendientes()
        except Exception as exc:
            logger.warning("Publicador de cotizaciones pendiente de conexión/configuración: %s", type(exc).__name__)
        await asyncio.sleep(5)


async def _receptor():
    while True:
        subscriber = None
        try:
            subscriber = crear_suscriptor()
            while True:
                await consumir_lote(subscriber, settings.PUBSUB_SUBSCRIPTION_ENTREGAS)
                await asyncio.sleep(0.2)
        except Exception as exc:
            logger.warning("Receptor de Entregas pendiente de configuración: %s", type(exc).__name__)
            await asyncio.sleep(15)
        finally:
            if subscriber:
                subscriber.close()


@asynccontextmanager
async def lifespan_despachos(app):
    tareas = []
    if settings.DESPACHOS_WORKER_ENABLED and settings.ENVIRONMENT != "testing":
        tareas.append(asyncio.create_task(_publicador()))
        if settings.PUBSUB_SUBSCRIPTION_ENTREGAS:
            tareas.append(asyncio.create_task(_receptor()))
    try:
        yield
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
