import asyncio
import os
import sys
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from backend.shared.config import settings
except ImportError:
    try:
        from shared.config import settings
    except ImportError:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from shared.config import settings

logger = logging.getLogger("pubsub_client")

# Auditoría local de eventos publicados/recibidos en memoria (para auditoría e inspección)
EVENTOS_PUBSUB_LOG: List[Dict[str, Any]] = []


class GooglePubSubClient:
    def __init__(self):
        self.project_id = getattr(settings, "GCP_PROJECT_ID", "project-a96e5fe1-5ba6-4698-a85")
        self.topic_name = getattr(
            settings,
            "PUBSUB_TOPIC_INVENTARIOS",
            "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e"
        )
        self.credentials_path = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")

    def _resolve_credentials_path(self) -> Optional[str]:
        candidates = [
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            self.credentials_path,
            os.path.join(os.getcwd(), "service-account.json"),
            os.path.join(os.getcwd(), "service_account.json"),
            os.path.join(os.getcwd(), "credentials", "service-account.json"),
            os.path.join(os.getcwd(), "credentials", "gcp-pubsub-service-account.json"),
            os.path.join(os.path.dirname(__file__), "..", "service-account.json"),
            os.path.join(os.path.dirname(__file__), "..", "credentials", "gcp-pubsub-service-account.json"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
        return None

    async def publish_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        attributes: Optional[Dict[str, str]] = None,
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Publica un evento estructurado con formato CloudEvents/Enterprise JSON
        al tópico de Google Cloud Pub/Sub especificado.
        """
        now_iso = datetime.utcnow().isoformat() + "Z"
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        corr_id = correlation_id or payload.get("orden_id") or str(uuid.uuid4())

        envelope = {
            "specversion": "1.0",
            "event_id": event_id,
            "event_type": event_type,
            "source": "maxiconecta.marketplace.grupo-e",
            "timestamp": now_iso,
            "correlation_id": corr_id,
            "equipo": "Grupo E — Marketplace y Ventas",
            "materia": "UCB SIS-323",
            "payload": payload
        }

        attrs = {
            "grupo": "Grupo-E",
            "modulo": "Marketplace-and-Sales",
            "tipo_evento": event_type,
            "correlation_id": str(corr_id),
            "timestamp": now_iso
        }
        if attributes:
            attrs.update(attributes)

        logger.info(
            "[PubSub] Enviando topic=%s atributos=%s mensaje=%s",
            self.topic_name,
            json.dumps(attrs, ensure_ascii=False, sort_keys=True),
            json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        )
        cred_path = self._resolve_credentials_path()
        if not cred_path:
            return self._fallback_audit(
                event_id, event_type, payload, attrs,
                error="No hay credenciales Pub/Sub disponibles; evento guardado en fallback local."
            )

        try:
            message_id = await asyncio.to_thread(
                self._publicar_google_cloud,
                envelope,
                attrs,
                cred_path,
            )
            registro = {
                "event_id": event_id,
                "event_type": event_type,
                "message_id": message_id,
                "status": "PUBLICADO",
                "timestamp": now_iso,
                "topic": self.topic_name,
                "payload": payload,
                "attributes": attrs,
                "simulated": False,
            }
            EVENTOS_PUBSUB_LOG.append(registro)
            logger.info("[PubSub] Evento %s PUBLICADO (message_id=%s)", event_type, message_id)
            return registro
        except Exception as exc:
            logger.exception("[PubSub] Error publicando %s; queda registrado en fallback local", event_type)
            return self._fallback_audit(event_id, event_type, payload, attrs, error=str(exc))

    def _publicar_google_cloud(
        self,
        envelope: Dict[str, Any],
        attributes: Dict[str, str],
        credentials_path: str,
    ) -> str:
        from google.cloud import pubsub_v1

        publisher = pubsub_v1.PublisherClient.from_service_account_file(credentials_path)
        try:
            future = publisher.publish(
                self.topic_name,
                json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                **attributes,
            )
            return str(future.result(timeout=10))
        finally:
            publisher.transport.close()

    def _fallback_audit(
        self,
        event_id: str,
        event_type: str,
        payload: Dict[str, Any],
        attrs: Dict[str, str],
        error: str
    ) -> Dict[str, Any]:
        """Almacena el evento en cola de auditoría offline cuando GCP no está accesible."""
        now_iso = datetime.utcnow().isoformat() + "Z"
        registro = {
            "event_id": event_id,
            "event_type": event_type,
            "message_id": f"sim-fallback-{uuid.uuid4().hex[:8]}",
            "status": "FALLBACK_OFFLINE",
            "error": error,
            "timestamp": now_iso,
            "topic": self.topic_name,
            "payload": payload,
            "attributes": attrs,
            "simulated": True
        }
        EVENTOS_PUBSUB_LOG.append(registro)
        logger.warning(
            "[PubSub] Evento %s FALLBACK_OFFLINE topic=%s datos=%s motivo=%s",
            event_type,
            self.topic_name,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            error,
        )
        return registro

    async def publicar_descuento_stock(
        self,
        orden_id: str,
        items: List[Dict[str, Any]],
        origen: str = "marketplace",
        sucursal_id: Optional[str] = None,
        reserva_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """RIO-INV-03: Descuento definitivo de stock enviado al ERP de Inventarios."""
        payload = {
            "tipo_movimiento": "DESCUENTO_DEFINITIVO",
            "orden_id": orden_id,
            "origen": origen,
            "sucursal_id": sucursal_id or "SUC-LP-CENTRAL",
            "reserva_id": reserva_id,
            "items": [
                {
                    "sku": item.get("sku"),
                    "cantidad": int(item.get("cantidad", 1)),
                    "nombre": item.get("nombre") or item.get("nombre_producto", "")
                }
                for item in items
            ]
        }
        return await self.publish_event(
            event_type="stock.descuento",
            payload=payload,
            correlation_id=orden_id
        )

    async def publicar_reintegro_stock(
        self,
        orden_id: str,
        items: List[Dict[str, Any]],
        motivo: str = "cancelacion_orden",
        origen: str = "marketplace",
        sucursal_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """RIO-INV-04: Reingreso de stock por anulación o devolución hacia Inventarios."""
        payload = {
            "tipo_movimiento": "REINTEGRO_DEVOLUCION",
            "orden_id": orden_id,
            "motivo": motivo,
            "origen": origen,
            "sucursal_id": sucursal_id or "SUC-LP-CENTRAL",
            "items": [
                {
                    "sku": item.get("sku"),
                    "cantidad": int(item.get("cantidad", 1)),
                    "nombre": item.get("nombre") or item.get("nombre_producto", "")
                }
                for item in items
            ]
        }
        return await self.publish_event(
            event_type="stock.reintegro",
            payload=payload,
            correlation_id=orden_id
        )

    async def publicar_mensaje_test(
        self,
        responsable: str = "Kevin Sancalli",
        detalle: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prueba de publicación solicitada por la cátedra UCB SIS-323."""
        payload = {
            "evento": "PRUEBA_PUBLICACION_DOCENTE",
            "equipo": "Grupo E — Marketplace y Ventas",
            "responsable": responsable,
            "materia": "UCB SIS-323",
            "descripcion": detalle or "Prueba de publicacion para confirmacion de recepcion docente",
            "fecha_hora_utc": datetime.utcnow().isoformat() + "Z",
            "fecha_hora_bolivia": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return await self.publish_event(
            event_type="prueba_docente",
            payload=payload,
            attributes={"canal_prueba": "docente_sis323"}
        )


pubsub_client = GooglePubSubClient()
