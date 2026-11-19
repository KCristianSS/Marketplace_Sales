"""RIO-CRM-01: outbox persistente y mensajes reales con el publicador de despachos."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client
from backend.shared.pubsub_client import GooglePubSubClient

logger = logging.getLogger('uvicorn.error.crm')
CRM_PUBSUB_TOPIC = settings.PUBSUB_TOPIC_CRM


def operar(accion, **datos):
    client = get_supabase_admin_client()
    if client is None:
        raise HTTPException(503, 'La sincronización CRM requiere persistencia en Supabase.')
    try:
        result = client.rpc('operar_crm', {'p_accion': accion, 'p_datos': datos}).execute().data
    except Exception as exc:
        logger.warning('No se pudo acceder a CRM (%s): %s', accion, type(exc).__name__)
        raise HTTPException(503, 'No se pudo acceder a la cola CRM. Verifica conexión y migración.') from exc
    if not isinstance(result, dict):
        raise HTTPException(503, 'Respuesta de persistencia CRM inválida.')
    if result.get('error'):
        raise HTTPException(result.get('status', 409), result['error'])
    return result


class RespuestaCRM(BaseModel):
    event_id: UUID
    event_type: Literal['cliente.sincronizado', 'cliente.rechazado']
    request_event_id: UUID
    cliente_id: UUID
    crm_contact_id: Optional[str] = Field(None, min_length=1, max_length=100)
    motivo: Optional[str] = Field(None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def validar_resultado(self):
        if self.event_type == 'cliente.sincronizado' and not (self.crm_contact_id or '').strip():
            raise ValueError('La confirmación requiere crm_contact_id.')
        if self.event_type == 'cliente.rechazado' and not (self.motivo or '').strip():
            raise ValueError('El rechazo requiere un motivo.')
        return self


def procesar_respuesta(envelope, message_id=None):
    if not isinstance(envelope, dict) or envelope.get('source') != 'erp.crm' or envelope.get('destination') != 'maxiconecta':
        raise ValueError('Origen o destino CRM inválido.')
    if not isinstance(envelope.get('payload'), dict):
        raise ValueError('La respuesta requiere payload.')
    respuesta = RespuestaCRM.model_validate({**envelope['payload'], 'event_id': envelope.get('event_id'), 'event_type': envelope.get('event_type')})
    if envelope.get('correlation_id') != str(respuesta.cliente_id):
        raise ValueError('La correlación no corresponde al cliente.')
    result = operar('respuesta', **respuesta.model_dump(mode='json'), message_id=message_id)
    logger.info('[PubSub CRM] RESPUESTA RECIBIDA event_id=%s resultado=%s', respuesta.event_id, result)
    return result


class CrmSyncService:
    def __init__(self):
        self.topic = CRM_PUBSUB_TOPIC

    async def procesar_outbox_pendientes(self, batch_size=10):
        eventos = (await asyncio.to_thread(operar, 'reclamar', limite=batch_size)).get('eventos', [])
        publisher = GooglePubSubClient(topic_name=self.topic)

        async def enviar(item):
            message_id, error = None, None
            try:
                result = await publisher.publish_event(event_type=item['event_type'], payload=item['payload'],
                    attributes={'destino': 'crm', 'version_contrato': '1', 'cliente_id': item['cliente_id']},
                    correlation_id=item['cliente_id'], event_id=item['event_id'], destination='crm')
                if result.get('status') == 'PUBLICADO' and not result.get('simulated') and result.get('message_id'):
                    message_id = result['message_id']
                else:
                    error = result.get('error') or 'Pub/Sub no confirmó la publicación. Se reintentará.'
            except Exception as exc:
                logger.warning('[PubSub CRM] Falló event_id=%s: %s', item['event_id'], type(exc).__name__)
                error = 'No se pudo publicar el mensaje al CRM.'
            return await asyncio.to_thread(operar, 'finalizar', id=item['id'], lease_id=item['lease_id'],
                message_id=message_id, error=error, topic=self.topic)
        return await asyncio.gather(*(enviar(item) for item in eventos))

    async def resincronizar_cliente(self, cliente_id):
        # Snapshot del perfil y direcciones persistidos, sin aceptar datos del navegador.
        return await asyncio.to_thread(operar, 'encolar', cliente_id=str(cliente_id))

    def obtener_estado_general(self):
        data = operar('estado')
        data.update(status='success', topic=self.topic, receptor_configurado=bool(settings.PUBSUB_SUBSCRIPTION_CRM))
        return data


crm_sync_service = CrmSyncService()


async def _publicador():
    while True:
        try:
            await crm_sync_service.procesar_outbox_pendientes()
        except Exception as exc:
            logger.warning('Publicador CRM pendiente de conexión/configuración: %s', type(exc).__name__)
        await asyncio.sleep(5)


async def consumir_lote(subscriber):
    try:
        lote = await asyncio.to_thread(subscriber.pull, request={'subscription': settings.PUBSUB_SUBSCRIPTION_CRM, 'max_messages': 10}, timeout=5, retry=None)
    except Exception as exc:
        if type(exc).__name__ == 'DeadlineExceeded':
            return
        raise
    for recibido in lote.received_messages:
        try:
            message = recibido.message
            envelope = json.loads(message.data.decode('utf-8'))
            if envelope.get('source') == 'erp.crm' and envelope.get('destination') == 'maxiconecta':
                await asyncio.to_thread(procesar_respuesta, envelope, message_id=message.message_id)
        except HTTPException as exc:
            if exc.status_code >= 500:
                continue  # Sin ACK: Pub/Sub debe reentregar cuando falle la persistencia.
            logger.warning('Respuesta CRM no correlacionada: %s', recibido.message.message_id)
        except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
            logger.warning('Respuesta CRM inválida: %s', recibido.message.message_id)
        await asyncio.to_thread(subscriber.acknowledge, request={'subscription': settings.PUBSUB_SUBSCRIPTION_CRM, 'ack_ids': [recibido.ack_id]})


async def _receptor():
    from backend.shared.despachos import crear_suscriptor
    while True:
        subscriber = None
        try:
            subscriber = crear_suscriptor()
            while True:
                await consumir_lote(subscriber)
                await asyncio.sleep(0.2)
        except Exception as exc:
            logger.warning('Receptor CRM pendiente de configuración: %s', type(exc).__name__)
            await asyncio.sleep(15)
        finally:
            if subscriber:
                subscriber.close()


@asynccontextmanager
async def lifespan_crm(_app):
    tareas = []
    if settings.CRM_WORKER_ENABLED and settings.ENVIRONMENT != 'testing':
        tareas.append(asyncio.create_task(_publicador()))
        if settings.PUBSUB_SUBSCRIPTION_CRM:
            if settings.PUBSUB_SUBSCRIPTION_CRM == settings.PUBSUB_SUBSCRIPTION_ENTREGAS:
                logger.error('CRM requiere una suscripción de respuestas independiente de Entregas.')
            else:
                tareas.append(asyncio.create_task(_receptor()))
    try:
        yield
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
