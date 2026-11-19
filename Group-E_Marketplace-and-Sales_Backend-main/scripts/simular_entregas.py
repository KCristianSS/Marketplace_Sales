"""ERP de Entregas simulado: consume y responde por Pub/Sub, sin respuestas HTTP ficticias."""
import argparse
import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.shared.config import settings
from backend.shared.despachos import crear_suscriptor
from backend.shared.pubsub_client import GooglePubSubClient

logger = logging.getLogger("simulador.entregas")


class SimuladorEntregas:
    def __init__(self, archivo: str, avanzar=False):
        self.archivo, self.avanzar = archivo, avanzar
        Path(archivo).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(archivo) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS solicitudes(id TEXT PRIMARY KEY, orden_id TEXT, estado TEXT, version INT)")
            conn.execute("CREATE TABLE IF NOT EXISTS respuestas(request_id TEXT PRIMARY KEY, datos TEXT)")

    def responder(self, evento: dict):
        if not isinstance(evento, dict) or not isinstance(evento.get('payload'), dict):
            raise ValueError('La solicitud debe incluir un payload estructurado.')
        if evento.get("source") != "maxiconecta.marketplace.grupo-e" or evento.get("destination") != "entregas":
            raise ValueError("Solicitud ajena a Entregas.")
        tipo = evento.get("event_type")
        if tipo not in {"despacho.solicitado", "despacho.estado.consultado", "despacho.cancelacion.solicitada", "despacho.cotizacion.calculada"}:
            raise ValueError("Tipo de solicitud inválido.")
        request_id = str(uuid.UUID(evento["event_id"]))
        payload = evento["payload"]
        if tipo == "despacho.cotizacion.calculada":
            return self.recibir_cotizacion(evento, request_id)
        solicitud, orden_id = str(uuid.UUID(payload["solicitud_id"])), str(uuid.UUID(payload["orden_id"]))
        with sqlite3.connect(self.archivo, timeout=15) as conn:
            conn.execute("BEGIN IMMEDIATE")
            previa = conn.execute("SELECT datos FROM respuestas WHERE request_id=?", (request_id,)).fetchone()
            if previa:
                return json.loads(previa[0])
            row = conn.execute("SELECT orden_id,estado,version FROM solicitudes WHERE id=?", (solicitud,)).fetchone()
            if row and row[0] != orden_id:
                raise ValueError("Solicitud reutilizada para otra orden.")
            if tipo == 'despacho.estado.consultado' and not row:
                raise LookupError("Consulta recibida antes que la solicitud; reintentar después.")
            estado, version = (row[1], row[2]) if row else ('programado', 0)
            motivo, respuesta_tipo = None, 'despacho.generado'
            if tipo == 'despacho.solicitado' and not row:
                if len((payload.get('entrega') or {}).get('direccion', '').strip()) < 5 or not payload.get('items'):
                    estado, motivo, respuesta_tipo = 'rechazado', 'Dirección o productos incompletos.', 'despacho.rechazado'
            elif tipo == 'despacho.cancelacion.solicitada':
                estado, respuesta_tipo = 'cancelado', 'despacho.cancelado'
            elif tipo == 'despacho.estado.consultado':
                respuesta_tipo = 'despacho.estado.actualizado'
                if self.avanzar:
                    estado = {'programado': 'en_preparacion', 'en_preparacion': 'en_transito', 'en_transito': 'entregado'}.get(estado, estado)
            version += 1
            if estado == 'cancelado':
                respuesta_tipo = 'despacho.cancelado'
            elif estado == 'rechazado':
                respuesta_tipo = 'despacho.rechazado'
                motivo = motivo or 'Solicitud rechazada por datos incompletos.'
            respuesta_payload = {
                'solicitud_id': solicitud, 'orden_id': orden_id, 'request_event_id': request_id,
                'version': version, 'estado': estado, 'motivo': motivo,
                'guia': f'TRK-SIM-{solicitud.replace("-", "")[:12].upper()}' if estado not in {'rechazado', 'cancelado'} else None,
                'transportista': 'Transportista simulado',
                'ruta': f"Ruta simulada - {(payload.get('entrega') or {}).get('ciudad', 'Destino')}",
                'ubicacion_actual': 'Centro logístico simulado' if estado != 'entregado' else 'Destino',
                'fecha_estimada': (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            }
            respuesta = {'event_id': str(uuid.uuid4()), 'event_type': respuesta_tipo,
                'source': 'erp.entregas', 'destination': 'maxiconecta',
                'correlation_id': solicitud, 'payload': respuesta_payload}
            conn.execute('INSERT INTO solicitudes VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET estado=excluded.estado,version=excluded.version',
                         (solicitud, orden_id, estado, version))
            conn.execute('INSERT INTO respuestas VALUES(?,?)', (request_id, json.dumps(respuesta)))
            return respuesta

    def recibir_cotizacion(self, evento, request_id):
        """Confirma la recepción del cálculo de Ventas sin crear una entrega."""
        payload = evento["payload"]
        cotizacion_id = str(uuid.UUID(payload["cotizacion_id"]))
        if (payload.get("simulacion") is not True or not isinstance(payload.get("calculo"), dict)
                or evento.get("correlation_id") != cotizacion_id):
            raise ValueError("Cotización simulada inválida.")
        with sqlite3.connect(self.archivo, timeout=15) as conn:
            conn.execute("BEGIN IMMEDIATE")
            previa = conn.execute("SELECT datos FROM respuestas WHERE request_id=?", (request_id,)).fetchone()
            if previa:
                return json.loads(previa[0])
            respuesta = dict(event_id=str(uuid.uuid4()), event_type="despacho.cotizacion.recibida",
                source="erp.entregas", destination="maxiconecta", correlation_id=cotizacion_id,
                payload=dict(cotizacion_id=cotizacion_id, request_event_id=request_id, simulacion=True,
                    estado="recibida", origen_calculo="maxiconecta.ventas", calculo=payload["calculo"]))
            conn.execute('INSERT INTO respuestas VALUES(?,?)', (request_id, json.dumps(respuesta)))
            return respuesta


async def ejecutar(subscription: str, archivo: str, avanzar=False):
    simulador = SimuladorEntregas(archivo, avanzar)
    subscriber = crear_suscriptor()
    publisher = GooglePubSubClient(topic_name=settings.PUBSUB_TOPIC_RESPUESTAS_ENTREGAS)
    try:
        while True:
            try:
                lote = await asyncio.to_thread(subscriber.pull, request={'subscription': subscription, 'max_messages': 10}, timeout=5, retry=None)
            except Exception as exc:
                if type(exc).__name__ == 'DeadlineExceeded':
                    continue
                raise
            for recibido in lote.received_messages:
                try:
                    if recibido.message.attributes.get('destino') == 'entregas':
                        respuesta = await asyncio.to_thread(simulador.responder, json.loads(recibido.message.data.decode('utf-8')))
                        publicado = await publisher.publish_event(respuesta['event_type'], respuesta['payload'],
                            attributes={'destino': 'maxiconecta', 'version_contrato': '1'},
                            correlation_id=respuesta['correlation_id'], event_id=respuesta['event_id'],
                            source='erp.entregas', destination='maxiconecta')
                        if publicado['status'] != 'PUBLICADO':
                            continue
                except LookupError:
                    continue
                except (ValueError, KeyError, TypeError):
                    logger.warning('Solicitud inválida: %s', recibido.message.message_id)
                await asyncio.to_thread(subscriber.acknowledge, request={'subscription': subscription, 'ack_ids': [recibido.ack_id]})
    finally:
        subscriber.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subscription', required=True, help='Suscripción exclusiva filtrada por destino=entregas')
    parser.add_argument('--state', default='simulador_entregas.sqlite3')
    parser.add_argument('--avanzar', action='store_true', help='Avanzar un estado por consulta, para demostración')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(ejecutar(args.subscription, args.state, args.avanzar))
    except KeyboardInterrupt:
        pass
