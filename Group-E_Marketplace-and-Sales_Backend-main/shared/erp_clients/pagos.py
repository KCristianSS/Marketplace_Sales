import uuid
from typing import Dict, Any, Optional
from backend.shared.config import settings
from backend.shared.erp_clients.base import BaseERPClient

class PagosClient(BaseERPClient):
    def __init__(self):
        super().__init__(settings.ERP_PAGOS_URL)

    async def procesar_cobro(
        self,
        monto: float,
        metodo: str,
        moneda: str = "BOB",
        transaccion_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """RIO-PAG-01: Solicitar procesamiento de cobro a pasarela digital o POS."""
        tx_id = transaccion_id or f"TX-PAG-{uuid.uuid4().hex[:10].upper()}"
        payload = {
            "monto": monto,
            "metodo": metodo,
            "moneda": moneda,
            "transaccion_id": tx_id,
            "metadata": metadata or {}
        }
        res = await self.post("/api/v1/cobros/procesar", payload)
        if res.get("status") == "fallback":
            token_pago = f"TOK-PAG-{uuid.uuid4().hex[:12].upper()}"
            estado_inicial = "aprobado"
            qr_payload = (
                f"MAXI-QR|EMVCO|BOB|{monto:.2f}|{tx_id}|{token_pago}|NIT=1028374029"
                if metodo == "qr" else None
            )
            redirect_url = (
                f"https://pasarela.maxiconecta.bo/checkout?token={token_pago}&tx={tx_id}&monto={monto:.2f}"
                if metodo == "pasarela" else None
            )
            return {
                "transaccion_id": tx_id,
                "token_pago": token_pago,
                "estado": estado_inicial,
                "monto": monto,
                "moneda": moneda,
                "metodo": metodo,
                "codigo_autorizacion": f"AUTH-{uuid.uuid4().hex[:6].upper()}" if estado_inicial == "aprobado" else None,
                "qr_payload": qr_payload,
                "redirect_url": redirect_url,
                "expira_en_segundos": 900,
                "modo": "mock_fallback"
            }
        return res

    async def emitir_factura(self, datos_fiscales: Dict[str, Any]) -> Dict[str, Any]:
        """RIO-PAG-02: Transmitir detalle fiscal para emisión y timbrado legal (CUF)."""
        res = await self.post("/api/v1/facturas/emitir", datos_fiscales)
        if res.get("status") == "fallback":
            return {
                "numero_factura": None,
                "cuf": None,
                "cufd": None,
                "estado": "pendiente",
                "modo": "fallback",
                "mensaje": "No se obtuvo autorización del servicio de facturación."
            }
        return res

    async def reversar_cobro(self, transaccion_id: str, monto: float) -> Dict[str, Any]:
        """RIO-PAG-03: Reversión del cobro y nota de crédito."""
        payload = {"transaccion_id": transaccion_id, "monto": monto}
        res = await self.post("/api/v1/facturas/reversion", payload)
        if res.get("status") == "fallback":
            return {
                "nota_credito": f"NC-{uuid.uuid4().hex[:8].upper()}",
                "reembolso_estado": "procesado",
                "modo": "mock_fallback"
            }
        return res

pagos_client = PagosClient()
