import uuid
import logging
import hashlib
import hmac
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.shared.security import get_current_user
from backend.shared import vales

from backend.shared.config import settings
from backend.shared.flete import validar_cotizacion, dinero, huella_items
from backend.shared.database import get_supabase_admin_client
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.erp_clients.inventarios import inventarios_client
from backend.shared.redis_client import consultar_reserva, liberar_reserva_stock
from backend.shared.pagos_firma import firmar_webhook, verificar_firma

try:
    from app import pagos_validacion as _validacion
    from app.pagos_repo import repo as _pagos_repo
except (ModuleNotFoundError, ImportError):
    from backend.services.ordenes.app import pagos_validacion as _validacion
    from backend.services.ordenes.app.pagos_repo import repo as _pagos_repo

logger = logging.getLogger("maxiconecta.pagos")

router = APIRouter(prefix="/api/v1/pagos", tags=["Pagos y Pasarelas Digitales (US-16 · RIO-PAG-01)"])

# Caché en memoria para transacciones activas y desacople rápido
_transacciones_cache: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------------------
# SCHEMAS DE ENTRADA Y SALIDA
# ------------------------------------------------------------------------------
class DatosTarjetaRequest(BaseModel):
    numero_tarjeta: str
    nombre_titular: str
    fecha_vencimiento: str
    cvv: str

class IniciarPagoRequest(BaseModel):
    proposito: Literal["compra", "vale"] = "compra"
    vale_reserva_id: Optional[uuid.UUID] = None
    tipo_despacho: str = "domicilio"
    cotizacion_flete: Optional[str] = None
    monto: float = Field(..., gt=0, description="Monto total a procesar")
    moneda: str = Field(default="BOB", description="Código de moneda (BOB, USD)")
    metodo_pago: str = Field(..., description="'qr', 'tarjeta', 'pasarela'")
    cliente_id: Optional[str] = "cliente-anonimo"
    reserva_id: Optional[str] = None
    orden_id: Optional[str] = None
    descripcion: Optional[str] = "Compra MaxiConecta Marketplace"
    datos_tarjeta: Optional[DatosTarjetaRequest] = None

class IniciarPagoResponse(BaseModel):
    transaccion_id: str
    token_pago: str
    estado: str
    metodo_pago: str
    monto: float
    moneda: str
    codigo_autorizacion: Optional[str] = None
    qr_payload: Optional[str] = None
    redirect_url: Optional[str] = None
    expira_en_segundos: int = 900
    mensaje: str
    created_at: str

class WebhookPagoRequest(BaseModel):
    transaccion_id: str
    evento: Literal["pago.aprobado", "pago.rechazado", "pago.pendiente", "pago.expirado"]
    codigo_autorizacion: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    monto: Optional[float] = None
    firma_hmac: Optional[str] = None

class TransaccionPagoResponse(BaseModel):
    transaccion_id: str
    token_pago: Optional[str] = None
    estado: str
    metodo_pago: str
    monto: float
    moneda: str
    codigo_autorizacion: Optional[str] = None
    orden_id: Optional[str] = None
    reserva_id: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    created_at: str
    updated_at: str

class SimularWebhookRequest(BaseModel):
    transaccion_id: str
    resultado: str = Field(..., description="'aprobado' o 'rechazado'")
    motivo: Optional[str] = None

def _get_supabase_safe():
    try:
        return get_supabase_admin_client()
    except Exception as e:
        logger.debug(f"Supabase client no inicializado: {e}")
        return None

# ------------------------------------------------------------------------------
# 1. INICIAR PAGO Y GENERACIÓN DE TOKEN (RIO-PAG-01)
# ------------------------------------------------------------------------------
@router.post("/iniciar", response_model=IniciarPagoResponse, status_code=status.HTTP_201_CREATED)
async def iniciar_pago(payload: IniciarPagoRequest, request: Request,
                       credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    """
    US-16 · RIO-PAG-01: Genera el token transaccional de cobro, emite el payload dinámico
    (QR interoperable, autorización de tarjeta o URL de pasarela) y registra la transacción.
    """
    cotizacion = None
    reserva_vale = None
    cliente_vales = None
    if payload.proposito == "vale" or payload.vale_reserva_id:
        user = await get_current_user(request, credentials)
        try:
            uuid.UUID(user["user_id"])
        except (ValueError, TypeError):
            raise HTTPException(422, "Se requiere una cuenta de cliente válida para utilizar vales.")
        if payload.cliente_id != user["user_id"]:
            raise HTTPException(403, "El pago debe pertenecer al usuario autenticado.")
        if payload.metodo_pago.lower().strip() not in {"qr", "tarjeta", "pasarela"} or payload.moneda != "BOB":
            raise HTTPException(422, "Los vales requieren un cobro digital confirmado en BOB.")
        if Decimal(str(payload.monto)) != dinero(payload.monto):
            raise HTTPException(422, "El importe admite como máximo dos decimales.")
        if payload.proposito == "vale" and (payload.vale_reserva_id or payload.reserva_id or payload.orden_id or payload.moneda != "BOB" or payload.monto > 10000):
            raise HTTPException(422, "Compra de vale inválida: usa BOB, hasta Bs 10000 y sin otros vales ni reserva de productos.")
        if payload.vale_reserva_id:
            reserva_vale = vales.operar("reserva", user["user_id"], reserva_id=str(payload.vale_reserva_id))
            if (reserva_vale["estado"] != "reservada" or reserva_vale["checkout_id"] != payload.reserva_id
                    or dinero(payload.monto) != dinero(reserva_vale["total"]) - dinero(reserva_vale["monto"])):
                raise HTTPException(409, "El pago no coincide con el saldo reservado del vale.")
        if payload.proposito == "vale":
            vales.generar_codigo("configuracion", "validacion")
        cliente_vales = vales.cliente_bd()
        # Comprobar el despliegue antes de iniciar un cobro.
        try:
            cliente_vales.table("tarjetas_regalo").select("id").limit(1).execute()
        except Exception:
            raise HTTPException(503, "Aplica la migración de tarjetas de regalo antes de cobrar.")
    if payload.reserva_id and payload.tipo_despacho == "domicilio":
        cotizacion = validar_cotizacion(payload.cotizacion_flete, payload.reserva_id, payload.cliente_id)
        reserva = await consultar_reserva(payload.reserva_id)
        if not reserva or reserva.get("status") != "ACTIVA" or huella_items(reserva["items"]) != cotizacion["items"]:
            raise HTTPException(409, "La reserva cambió o venció. Vuelve a cotizar el envío.")
        aporte_vale = dinero(reserva_vale["monto"]) if reserva_vale else dinero(0)
        if payload.moneda != "BOB" or dinero(payload.monto) + aporte_vale != dinero(cotizacion["total"]):
            raise HTTPException(409, "El total cambió. Actualiza la cotización antes de pagar.")
    metodo_norm = payload.metodo_pago.lower().strip()
    if metodo_norm not in ("tarjeta", "qr", "pasarela", "efectivo", "transferencia"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Método de pago '{payload.metodo_pago}' no soportado. Métodos válidos: 'qr', 'tarjeta', 'pasarela'."
        )

    # Validar reserva de stock en Redis si existe
    if payload.reserva_id:
        reserva = await consultar_reserva(payload.reserva_id)
        if cliente_vales and (not reserva or reserva.get("status") != "ACTIVA"):
            raise HTTPException(409, "Renueva la reserva de productos antes de iniciar el pago con vale.")
        if reserva and reserva.get("status") == "EXPIRADA":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La reserva temporal de stock ha expirado (límite de 15 minutos). Por favor renuévala."
            )

    if metodo_norm == "tarjeta" and payload.datos_tarjeta:
        numero = payload.datos_tarjeta.numero_tarjeta.replace(" ", "").replace("-", "")
        if not numero.isdigit() or not 13 <= len(numero) <= 19:
            raise HTTPException(422, "El número de tarjeta debe contener entre 13 y 19 dígitos.")
    transaccion_id = f"TX-PAG-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    # Llamada al cliente ERP Pagos (RIO-PAG-01)
    erp_res = await pagos_client.procesar_cobro(
        monto=payload.monto,
        metodo=metodo_norm,
        moneda=payload.moneda,
        transaccion_id=transaccion_id,
        metadata={
            "proposito": payload.proposito,
            "vale_reserva_id": str(payload.vale_reserva_id) if payload.vale_reserva_id else None,
            "cliente_id": payload.cliente_id,
            "reserva_id": payload.reserva_id,
            "orden_id": payload.orden_id,
            "descripcion": payload.descripcion
        }
    )

    token_pago = erp_res.get("token_pago") or f"TOK-PAG-{uuid.uuid4().hex[:12].upper()}"
    if cliente_vales and settings.ENVIRONMENT not in {"development", "testing"} and erp_res.get("modo") in {"mock_fallback", "fallback"}:
        raise HTTPException(503, "El proveedor de pagos no confirmó un cobro real.")
    if (payload.proposito == "vale" or reserva_vale) and str(erp_res.get("estado") or erp_res.get("status") or "").lower() in {"rechazado", "rechazada", "error", "fallido", "denegado"}:
        raise HTTPException(409, "El proveedor rechazó el cobro.")
    codigo_auth = erp_res.get("codigo_autorizacion")
    # Para QR y pasarela la transacción se inicia en estado 'pendiente' para esperar escaneo/pago del usuario
    if metodo_norm in ("qr", "pasarela"):
        estado_inicial = "pendiente"
    elif metodo_norm == "tarjeta":
        estado_inicial = "aprobado"
        codigo_auth = codigo_auth or f"AUTH-{uuid.uuid4().hex[:6].upper()}"
    else:
        estado_inicial = "aprobado"
    if cliente_vales and metodo_norm == "tarjeta" and str(erp_res.get("estado") or erp_res.get("status") or "").lower() not in {"aprobado", "aprobada", "approved", "ok"}:
        estado_inicial = "pendiente"

    now_iso = datetime.utcnow().isoformat()
    qr_payload = erp_res.get("qr_payload")
    if metodo_norm == "qr" and not qr_payload:
        qr_payload = f"MAXI-QR|EMVCO|BOB|{payload.monto:.2f}|{transaccion_id}|{token_pago}|NIT=1028374029"

    redirect_url = erp_res.get("redirect_url")
    if metodo_norm == "pasarela" and not redirect_url:
        redirect_url = f"https://pasarela.maxiconecta.bo/checkout?token={token_pago}&tx={transaccion_id}&monto={payload.monto:.2f}"

    record = {
        "proposito": payload.proposito,
        "vale_reserva_id": str(payload.vale_reserva_id) if payload.vale_reserva_id else None,
        "cotizacion_flete": payload.cotizacion_flete,
        "entrega": cotizacion,
        "transaccion_id": transaccion_id,
        "token_pago": token_pago,
        "estado": estado_inicial,
        "metodo": metodo_norm,
        "monto": float(payload.monto),
        "moneda": payload.moneda,
        "codigo_autorizacion": codigo_auth,
        "cliente_id": payload.cliente_id,
        "reserva_id": payload.reserva_id,
        "orden_id": payload.orden_id,
        "motivo_rechazo": None,
        "qr_payload": qr_payload,
        "redirect_url": redirect_url,
        "expira_en_segundos": erp_res.get("expira_en_segundos", 900),
        "created_at": now_iso,
        "updated_at": now_iso
    }

    _transacciones_cache[transaccion_id] = record
    _transacciones_cache[token_pago] = record

    # Persistencia en base de datos Supabase
    client = cliente_vales or _get_supabase_safe()
    if client:
        try:
            client.table("pagos").insert({
                "transaccion_id": transaccion_id,
                "token_pago": token_pago,
                "metodo": metodo_norm,
                "monto": float(payload.monto),
                "moneda": payload.moneda,
                "estado": estado_inicial,
                "orden_id": payload.orden_id if (payload.orden_id and len(payload.orden_id) == 36) else None,
                "raw_payload": record
            }).execute()
        except Exception as e:
            if cliente_vales:
                try:
                    await pagos_client.reversar_cobro(transaccion_id, payload.monto)
                finally:
                    _transacciones_cache.pop(transaccion_id, None)
                    _transacciones_cache.pop(token_pago, None)
                raise HTTPException(503, "No se pudo guardar el pago del vale; se solicitó la reversión del cobro.")
            logger.warning(f"Aviso al guardar pago en Supabase (conservado en memoria): {e}")

    mensaje = "Token transaccional generado exitosamente."
    if metodo_norm == "qr":
        mensaje = "Código QR dinámico emitido. Esperando confirmación de la pasarela bancaria."
    elif metodo_norm == "tarjeta":
        mensaje = "Pago con tarjeta aprobado y verificado."
    elif metodo_norm == "pasarela":
        mensaje = "Redirección a pasarela de pago segura preparada."

    return IniciarPagoResponse(
        transaccion_id=transaccion_id,
        token_pago=token_pago,
        estado=estado_inicial,
        metodo_pago=metodo_norm,
        monto=float(payload.monto),
        moneda=payload.moneda,
        codigo_autorizacion=codigo_auth,
        qr_payload=qr_payload,
        redirect_url=redirect_url,
        expira_en_segundos=record["expira_en_segundos"],
        mensaje=mensaje,
        created_at=now_iso
    )

# ------------------------------------------------------------------------------
# 2. CONSULTA DE ESTADO DE TRANSACCIÓN (POLLING / LIVE CHECK)
# ------------------------------------------------------------------------------
@router.get("/transacciones/{id_or_token}", response_model=TransaccionPagoResponse)
async def obtener_estado_transaccion(id_or_token: str):
    """
    Consulta en tiempo real el estado de una transacción por ID o Token de pago.
    Permite al frontend detectar la confirmación inmediata tras escaneo de QR o pasarela.
    """
    record = _transacciones_cache.get(id_or_token)
    if not record:
        client = _get_supabase_safe()
        if client:
            try:
                res = client.table("pagos").select("*").or_(
                    f"transaccion_id.eq.{id_or_token},token_pago.eq.{id_or_token}"
                ).limit(1).execute()
                if res.data:
                    row = res.data[0]
                    raw = row.get("raw_payload") or {}
                    record = {
                        "proposito": raw.get("proposito", "compra"),
                        "vale_reserva_id": raw.get("vale_reserva_id"),
                        "cotizacion_flete": raw.get("cotizacion_flete"),
                        "entrega": raw.get("entrega"),
                        "cliente_id": raw.get("cliente_id"),
                        "transaccion_id": row.get("transaccion_id") or id_or_token,
                        "token_pago": row.get("token_pago") or raw.get("token_pago"),
                        "estado": row.get("estado", "pendiente"),
                        "metodo": row.get("metodo", "qr"),
                        "monto": float(row.get("monto", 0.0)),
                        "moneda": row.get("moneda", "BOB"),
                        "codigo_autorizacion": raw.get("codigo_autorizacion"),
                        "orden_id": row.get("orden_id") or raw.get("orden_id"),
                        "reserva_id": raw.get("reserva_id"),
                        "motivo_rechazo": raw.get("motivo_rechazo"),
                        "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
                        "updated_at": row.get("updated_at") or datetime.utcnow().isoformat()
                    }
                    _transacciones_cache[id_or_token] = record
            except Exception as e:
                logger.warning(f"Error consultando Supabase para transacción {id_or_token}: {e}")

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transacción o token de pago '{id_or_token}' no encontrado."
        )

    return TransaccionPagoResponse(
        transaccion_id=record["transaccion_id"],
        token_pago=record.get("token_pago"),
        estado=record["estado"],
        metodo_pago=record["metodo"],
        monto=float(record["monto"]),
        moneda=record["moneda"],
        codigo_autorizacion=record.get("codigo_autorizacion"),
        orden_id=record.get("orden_id"),
        reserva_id=record.get("reserva_id"),
        motivo_rechazo=record.get("motivo_rechazo"),
        created_at=record["created_at"],
        updated_at=record["updated_at"]
    )

# ------------------------------------------------------------------------------
# 3. WEBHOOK RECEPTOR DE NOTIFICACIONES DE PAGO (US-16 · APROBADO / RECHAZADO)
# ------------------------------------------------------------------------------
@router.post("/webhook")
async def recibir_webhook_pago(payload: WebhookPagoRequest):
    """
    US-16: Endpoint webhook receptor de notificaciones de la pasarela bancaria o POS.
    Procesa eventos 'pago.aprobado' o 'pago.rechazado' y ejecuta acciones atómicas:
    - Si aprobado: actualiza el pago a 'aprobado' y confirma la orden/reserva.
    - Si rechazado: actualiza el pago a 'rechazado' y libera la reserva de stock (compensación).
    """
    tx_id = payload.transaccion_id

    # KAN-54: la firma HMAC (si se envía) siempre debe ser válida.
    if payload.firma_hmac is not None and not verificar_firma(payload.firma_hmac, tx_id, payload.evento.lower().strip(), payload.monto):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma HMAC del webhook inválida.")

    # KAN-54: pagos de una orden (registrados con /pagos/registrar) -> validación idempotente.
    pago_orden = _pagos_repo.get_pago_por_tx(tx_id)
    if pago_orden:
        if not payload.firma_hmac:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El webhook de un pago de orden requiere firma HMAC.")
        if pago_orden.get("orden_id"):
            return await _validacion.procesar_webhook(
                pago_orden, payload.evento, payload.monto, payload.codigo_autorizacion, payload.motivo_rechazo
            )

    if settings.ENVIRONMENT not in {"development", "testing"}:
        if not settings.PAGOS_WEBHOOK_SECRET:
            raise HTTPException(503, "Configura PAGOS_WEBHOOK_SECRET para recibir confirmaciones bancarias.")
        texto = f"{tx_id}|{payload.evento}|{dinero(payload.monto) if payload.monto is not None else ''}"
        firma = hmac.new(settings.PAGOS_WEBHOOK_SECRET.encode(), texto.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, payload.firma_hmac or ""):
            raise HTTPException(401, "Firma de confirmación de pago inválida.")
    if tx_id not in _transacciones_cache:
        try:
            await obtener_estado_transaccion(tx_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    record = _transacciones_cache.get(tx_id)
    now_iso = datetime.utcnow().isoformat()

    # Normalizar evento
    evento = payload.evento.lower().strip()
    nuevo_estado = "pendiente"
    if "aprobado" in evento:
        nuevo_estado = "aprobado"
    elif "rechazado" in evento:
        nuevo_estado = "rechazado"
    elif "expirado" in evento:
        nuevo_estado = "rechazado"

    codigo_auth = payload.codigo_autorizacion or (f"AUTH-{uuid.uuid4().hex[:6].upper()}" if nuevo_estado == "aprobado" else None)

    if record:
        record["estado"] = nuevo_estado
        record["updated_at"] = now_iso
        if codigo_auth:
            record["codigo_autorizacion"] = codigo_auth
        if payload.motivo_rechazo:
            record["motivo_rechazo"] = payload.motivo_rechazo
    else:
        record = {
            "transaccion_id": tx_id,
            "token_pago": None,
            "estado": nuevo_estado,
            "metodo": "qr",
            "monto": payload.monto or 0.0,
            "moneda": "BOB",
            "codigo_autorizacion": codigo_auth,
            "motivo_rechazo": payload.motivo_rechazo,
            "created_at": now_iso,
            "updated_at": now_iso
        }
        _transacciones_cache[tx_id] = record

    # Acciones compensatorias o de confirmación
    reserva_id = record.get("reserva_id")
    orden_id = record.get("orden_id")

    if nuevo_estado == "rechazado" and reserva_id:
        logger.info(f"Pago {tx_id} rechazado. Ejecutando protocolo compensatorio: liberando reserva {reserva_id}")
        await liberar_reserva_stock(reserva_id)
    if nuevo_estado == "rechazado" and record.get("vale_reserva_id"):
        vales.operar("liberar", record["cliente_id"], reserva_id=record["vale_reserva_id"])

    # Actualizar estado en Supabase
    client = _get_supabase_safe()
    if client:
        try:
            update_data: Dict[str, Any] = {
                "estado": nuevo_estado,
                "updated_at": now_iso
            }
            client.table("pagos").update(update_data).eq("transaccion_id", tx_id).execute()

            # Si la orden ya existía, actualizar su estado correspondiente
            if orden_id and len(orden_id) == 36:
                nuevo_estado_orden = "confirmada" if nuevo_estado == "aprobado" else "cancelada"
                client.table("ordenes").update({"estado": nuevo_estado_orden}).eq("id", orden_id).execute()
        except Exception as e:
            logger.warning(f"Aviso actualizando webhook en Supabase: {e}")

    logger.info(f"Webhook procesado para {tx_id}: estado={nuevo_estado}")
    return {
        "recibido": True,
        "transaccion_id": tx_id,
        "nuevo_estado": nuevo_estado,
        "codigo_autorizacion": codigo_auth,
        "mensaje": f"Notificación procesada exitosamente como '{nuevo_estado}'"
    }

# ------------------------------------------------------------------------------
# 4. SIMULADOR DE WEBHOOK (DEV / DEMO / QA)
# ------------------------------------------------------------------------------
@router.post("/simular-webhook")
async def simular_webhook(payload: SimularWebhookRequest):
    """
    Herramienta interactiva para pruebas y demostración de US-16:
    Dispara internamente el webhook con 'aprobado' o 'rechazado' para una transacción dada.
    """
    if settings.ENVIRONMENT not in {"development", "testing"}:
        raise HTTPException(403, "La simulación de pagos solo está disponible en desarrollo y pruebas.")
    tx_id = payload.transaccion_id
    evento = f"pago.{payload.resultado.lower()}"
    webhook_payload = WebhookPagoRequest(
        transaccion_id=tx_id,
        evento=evento,
        motivo_rechazo=payload.motivo or ("Fondos insuficientes o timeout de pasarela" if payload.resultado == "rechazado" else None),
        codigo_autorizacion=f"AUTH-SIM-{uuid.uuid4().hex[:6].upper()}" if payload.resultado == "aprobado" else None,
        firma_hmac=firmar_webhook(tx_id, evento, None),  # simulación: la pasarela "firma" el aviso
    )
    return await recibir_webhook_pago(webhook_payload)
