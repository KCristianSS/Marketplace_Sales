"""Cola durable de correos transaccionales por cambios de estado (KAN-217)."""
import asyncio
import html
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, Optional
from urllib.parse import quote

from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client

logger = logging.getLogger("maxiconecta.notificaciones")
MAX_INTENTOS = 4  # envío inicial más tres reintentos
ESPERAS_REINTENTO_SEGUNDOS = (30, 120, 600)
INTERVALO_WORKER_SEGUNDOS = 5


def _url_seguimiento(orden_id: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/mi-cuenta?tab=pedidos&orden={quote(orden_id)}"


def _plantilla(codigo_orden: str, estado: str, orden_id: str) -> tuple[str, str]:
    etiquetas = {
        "pendiente": "Pendiente",
        "confirmada": "Confirmado",
        "en_preparacion": "En preparación",
        "despachada": "Despachado",
        "entregada": "Entregado",
        "cancelada": "Cancelado",
    }
    etiqueta = etiquetas.get(estado, estado.replace("_", " ").capitalize())
    url = _url_seguimiento(orden_id)
    codigo_seguro = html.escape(codigo_orden)
    asunto = f"Actualización de tu pedido {codigo_orden}: {etiqueta}"
    contenido = (
        "<html><body style='font-family:Arial,sans-serif;color:#1f2937'>"
        f"<h2>Tu pedido {codigo_seguro} está: {html.escape(etiqueta)}</h2>"
        "<p>Te avisamos que el estado de tu pedido tuvo una actualización.</p>"
        f"<p><a href='{html.escape(url, quote=True)}'>Consultar seguimiento del pedido</a></p>"
        "<p>Gracias por comprar en MaxiConecta.</p></body></html>"
    )
    return asunto, contenido


def _smtp_configurado() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL and settings.SMTP_USER and settings.SMTP_PASSWORD)


def _enviar_smtp(destino: str, asunto: str, contenido: str) -> None:
    if not _smtp_configurado():
        raise RuntimeError("Configura el servidor, usuario, contraseña y remitente SMTP para habilitar el envío de correos.")
    message = EmailMessage()
    message["Subject"] = asunto
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = destino
    message.set_content("Tu pedido tuvo una actualización. Abre el mensaje en formato HTML para ver el enlace de seguimiento.")
    message.add_alternative(contenido, subtype="html")
    timeout_seconds = 15
    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout_seconds) as server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout_seconds) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
            server.send_message(message)


async def _cargar_cliente_y_preferencias(client: Any, cliente_id: str) -> Optional[Dict[str, Any]]:
    profile = client.table("perfiles_clientes").select("id,email").eq("id", cliente_id).limit(1).execute().data or []
    if not profile or not profile[0].get("email"):
        logger.warning("La orden del cliente %s no tiene correo de destino", cliente_id)
        return None
    preference = client.table("preferencias_notificacion").select("canal_correo,avisos_estado_pedido").eq("cliente_id", cliente_id).limit(1).execute().data or []
    if preference:
        pref = preference[0]
        if not bool(pref.get("avisos_estado_pedido", True)) or not bool(pref.get("canal_correo", True)):
            logger.info("Aviso por correo omitido para cliente %s según sus preferencias", cliente_id)
            return None
    return profile[0]


async def encolar_cambio_estado(
    orden_id: str,
    cliente_id: str,
    codigo_orden: str,
    estado_anterior: str,
    estado_nuevo: str,
) -> None:
    """Guarda la transición en el outbox; el worker de fondo realiza el envío."""
    client = get_supabase_admin_client()
    if not client:
        logger.warning("No se encoló la notificación de %s: Supabase no está disponible", orden_id)
        return
    try:
        customer = await _cargar_cliente_y_preferencias(client, cliente_id)
        if not customer:
            return
        subject, body = _plantilla(codigo_orden, estado_nuevo, orden_id)
        event_key = f"{orden_id}:{estado_anterior}:{estado_nuevo}"
        now = datetime.now(timezone.utc).isoformat()
        client.table("notificaciones_log").upsert({
            "event_key": event_key,
            "orden_id": orden_id,
            "cliente_id": cliente_id,
            "correo_destino": customer["email"],
            "estado_orden": estado_nuevo,
            "asunto": subject,
            "contenido": body,
            "estado": "pendiente",
            "intentos": 0,
            "max_intentos": MAX_INTENTOS,
            "proximo_intento_at": now,
            "actualizado_at": now,
        }, on_conflict="event_key", ignore_duplicates=True).execute()
    except Exception:
        # Un fallo de correo o bitácora nunca revierte una transición ya guardada.
        logger.exception("No se pudo encolar la notificación de estado para la orden %s", orden_id)


async def procesar_notificacion(notificacion_id: str) -> None:
    if not _smtp_configurado():
        return
    client = get_supabase_admin_client()
    if not client:
        return
    now = datetime.now(timezone.utc)
    try:
        claimed = client.table("notificaciones_log").update({
            "estado": "procesando", "actualizado_at": now.isoformat()
        }).eq("id", notificacion_id).eq("estado", "pendiente").lte(
            "proximo_intento_at", now.isoformat()
        ).select("*").execute().data or []
        if not claimed:
            return
        row = claimed[0]
        try:
            contenido = row["contenido"].replace("{{SEGUIMIENTO_URL}}", html.escape(_url_seguimiento(str(row["orden_id"])), quote=True))
            await asyncio.to_thread(_enviar_smtp, row["correo_destino"], row["asunto"], contenido)
            sent_at = datetime.now(timezone.utc).isoformat()
            client.table("notificaciones_log").update({
                "estado": "enviada", "intentos": int(row.get("intentos", 0)) + 1,
                "enviado_at": sent_at, "ultimo_error": None, "actualizado_at": sent_at,
            }).eq("id", notificacion_id).execute()
        except Exception as exc:
            attempts = int(row.get("intentos", 0)) + 1
            retrying = attempts < int(row.get("max_intentos", MAX_INTENTOS))
            wait_seconds = ESPERAS_REINTENTO_SEGUNDOS[min(attempts - 1, len(ESPERAS_REINTENTO_SEGUNDOS) - 1)]
            next_state = "pendiente" if retrying else "fallida"
            next_attempt = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
            client.table("notificaciones_log").update({
                "estado": next_state, "intentos": attempts,
                "proximo_intento_at": next_attempt.isoformat(),
                "ultimo_error": str(exc)[:2000], "actualizado_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", notificacion_id).execute()
            logger.warning("Fallo de correo para notificación %s (intento %s/%s): %s", notificacion_id, attempts, MAX_INTENTOS, exc)
    except Exception:
        logger.exception("No se pudo procesar notificación %s", notificacion_id)


async def worker_notificaciones(stop_event: Optional[asyncio.Event] = None) -> None:
    """Recupera trabajos pendientes después de reinicios y procesa los vencidos."""
    while stop_event is None or not stop_event.is_set():
        client = get_supabase_admin_client()
        if client and _smtp_configurado():
            try:
                now = datetime.now(timezone.utc)
                stale_before = (now - timedelta(minutes=2)).isoformat()
                client.table("notificaciones_log").update({
                    "estado": "pendiente", "proximo_intento_at": now.isoformat(),
                    "actualizado_at": now.isoformat(),
                }).eq("estado", "procesando").lt("actualizado_at", stale_before).execute()
                due = client.table("notificaciones_log").select("id").eq("estado", "pendiente").lte(
                    "proximo_intento_at", now.isoformat()
                ).order("proximo_intento_at").limit(20).execute().data or []
                await asyncio.gather(*(procesar_notificacion(row["id"]) for row in due))
            except Exception:
                logger.exception("Error al consultar la cola de notificaciones")
        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVALO_WORKER_SEGUNDOS)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(INTERVALO_WORKER_SEGUNDOS)


async def obtener_notificacion(notificacion_id: str) -> Optional[Dict[str, Any]]:
    client = get_supabase_admin_client()
    if not client:
        return None
    rows = client.table("notificaciones_log").select("*").eq("id", notificacion_id).limit(1).execute().data or []
    return rows[0] if rows else None


async def reencolar_notificacion(notificacion_id: str) -> Optional[Dict[str, Any]]:
    client = get_supabase_admin_client()
    if not client:
        return None
    now = datetime.now(timezone.utc).isoformat()
    rows = client.table("notificaciones_log").update({
        "estado": "pendiente", "intentos": 0, "ultimo_error": None,
        "proximo_intento_at": now, "actualizado_at": now,
    }).eq("id", notificacion_id).eq("estado", "fallida").select("id").execute().data or []
    if not rows:
        return None
    return await obtener_notificacion(notificacion_id)
