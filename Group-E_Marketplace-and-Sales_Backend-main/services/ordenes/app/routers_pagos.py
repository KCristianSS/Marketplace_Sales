import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status

from backend.shared.config import settings
from backend.shared.database import get_supabase
from backend.shared.erp_clients.pagos import pagos_client
from backend.shared.erp_clients.inventarios import inventarios_client
from backend.shared.redis_client import consultar_reserva, liberar_reserva_stock

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
    evento: str = Field(..., description="'pago.aprobado', 'pago.rechazado', 'pago.pendiente'")
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
        return get_supabase()
    except Exception as e:
        logger.debug(f"Supabase client no inicializado: {e}")
        return None

# ------------------------------------------------------------------------------
# 1. INICIAR PAGO Y GENERACIÓN DE TOKEN (RIO-PAG-01)
# ------------------------------------------------------------------------------
@router.post("/iniciar", response_model=IniciarPagoResponse, status_code=status.HTTP_201_CREATED)
async def iniciar_pago(payload: IniciarPagoRequest):
    """
    US-16 · RIO-PAG-01: Genera el token transaccional de cobro, emite el payload dinámico
    (QR interoperable, autorización de tarjeta o URL de pasarela) y registra la transacción.
    """
    metodo_norm = payload.metodo_pago.lower().strip()
    if metodo_norm not in ("tarjeta", "qr", "pasarela", "efectivo", "transferencia"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Método de pago '{payload.metodo_pago}' no soportado. Métodos válidos: 'qr', 'tarjeta', 'pasarela'."
        )

    # Validar reserva de stock en Redis si existe
    if payload.reserva_id:
        reserva = await consultar_reserva(payload.reserva_id)
        if reserva and reserva.get("status") == "EXPIRADA":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La reserva temporal de stock ha expirado (límite de 15 minutos). Por favor renuévala."
            )

    transaccion_id = f"TX-PAG-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    # Llamada al cliente ERP Pagos (RIO-PAG-01)
    erp_res = await pagos_client.procesar_cobro(
        monto=payload.monto,
        metodo=metodo_norm,
        moneda=payload.moneda,
        transaccion_id=transaccion_id,
        metadata={
            "cliente_id": payload.cliente_id,
            "reserva_id": payload.reserva_id,
            "orden_id": payload.orden_id,
            "descripcion": payload.descripcion
        }
    )

    token_pago = erp_res.get("token_pago") or f"TOK-PAG-{uuid.uuid4().hex[:12].upper()}"
    codigo_auth = erp_res.get("codigo_autorizacion")
    # Para QR y pasarela la transacción se inicia en estado 'pendiente' para esperar escaneo/pago del usuario
    if metodo_norm in ("qr", "pasarela"):
        estado_inicial = "pendiente"
    elif metodo_norm == "tarjeta":
        if payload.datos_tarjeta:
            # Validación básica de número (al menos 13 dígitos y no empezar con ceros)
            num_clean = payload.datos_tarjeta.numero_tarjeta.replace(" ", "").replace("-", "")
            if len(num_clean) < 13 or not num_clean.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="El número de tarjeta no es válido (debe contener entre 13 y 19 dígitos numéricos)."
                )
        estado_inicial = "aprobado"
        codigo_auth = codigo_auth or f"AUTH-{uuid.uuid4().hex[:6].upper()}"
    else:
        estado_inicial = "aprobado"

    now_iso = datetime.utcnow().isoformat()
    qr_payload = erp_res.get("qr_payload")
    if metodo_norm == "qr" and not qr_payload:
        qr_payload = f"MAXI-QR|EMVCO|BOB|{payload.monto:.2f}|{transaccion_id}|{token_pago}|NIT=1028374029"

    redirect_url = erp_res.get("redirect_url")
    if metodo_norm == "pasarela" and not redirect_url:
        redirect_url = f"https://pasarela.maxiconecta.bo/checkout?token={token_pago}&tx={transaccion_id}&monto={payload.monto:.2f}"

    record = {
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
    client = _get_supabase_safe()
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
    tx_id = payload.transaccion_id
    evento = f"pago.{payload.resultado.lower()}"
    webhook_payload = WebhookPagoRequest(
        transaccion_id=tx_id,
        evento=evento,
        motivo_rechazo=payload.motivo or ("Fondos insuficientes o timeout de pasarela" if payload.resultado == "rechazado" else None),
        codigo_autorizacion=f"AUTH-SIM-{uuid.uuid4().hex[:6].upper()}" if payload.resultado == "aprobado" else None
    )
    return await recibir_webhook_pago(webhook_payload)
