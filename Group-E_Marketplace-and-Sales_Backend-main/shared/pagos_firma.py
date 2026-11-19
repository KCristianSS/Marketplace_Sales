"""Firma HMAC-SHA256 de los webhooks de la pasarela de pagos (simulada) — KAN-54."""
import hashlib
import hmac
from decimal import Decimal
from typing import Any, Optional

from backend.shared.config import settings


def _canonico(transaccion_id: str, evento: str, monto: Any) -> bytes:
    monto_txt = f"{Decimal(str(monto)):.2f}" if monto is not None else ""
    return f"{transaccion_id}|{evento}|{monto_txt}".encode("utf-8")


def firmar_webhook(transaccion_id: str, evento: str, monto: Any = None, secreto: Optional[str] = None) -> str:
    clave = (secreto or settings.PAGOS_WEBHOOK_SECRET).encode("utf-8")
    return hmac.new(clave, _canonico(transaccion_id, evento, monto), hashlib.sha256).hexdigest()


def verificar_firma(firma: Optional[str], transaccion_id: str, evento: str, monto: Any = None) -> bool:
    if not firma:
        return False
    return hmac.compare_digest(firma.strip().lower(), firmar_webhook(transaccion_id, evento, monto))
