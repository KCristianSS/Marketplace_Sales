from typing import Dict, Any
from backend.shared.config import settings
from backend.shared.erp_clients.base import BaseERPClient

class ContabilidadClient(BaseERPClient):
    def __init__(self):
        super().__init__(settings.ERP_CONTABILIDAD_URL)

    async def registrar_asiento_venta(self, orden_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        RIO-CON-01: Asiento contable de ventas (evento OrderPaidEvent).

        ``orden_data`` incluye ``desglose_pagos`` (lista de {metodo, monto, transaccion_id,
        referencia, estado}) y ``totales_por_metodo`` para que Contabilidad distribuya el
        asiento entre Caja, Bancos y cobros QR cuando la venta se pagó con varios métodos.
        """
        res = await self.post("/api/v1/asientos/venta", orden_data)
        if res.get("status") == "fallback":
            return {"asiento_id": "ASI-VTA-001", "estado": "asentado", "modo": "mock_fallback"}
        return res

    async def registrar_costo_ventas(self, costo_data: Dict[str, Any]) -> Dict[str, Any]:
        """RIO-CON-02: Registro contable del costo de mercadería vendida."""
        res = await self.post("/api/v1/asientos/costo-ventas", costo_data)
        if res.get("status") == "fallback":
            return {"asiento_id": "ASI-CMV-001", "estado": "asentado", "modo": "mock_fallback"}
        return res

    async def registrar_reversion(self, reversion_data: Dict[str, Any]) -> Dict[str, Any]:
        """RIO-CON-04: Asientos de reversión por cancelaciones y devoluciones."""
        res = await self.post("/api/v1/asientos/reversion", reversion_data)
        if res.get("status") == "fallback":
            return {"asiento_id": "ASI-REV-001", "estado": "revertido", "modo": "mock_fallback"}
        return res

    async def notificar_arqueo_con_diferencia(self, arqueo_data: Dict[str, Any]) -> Dict[str, Any]:
        """KAN-341: avisa a Contabilidad de un arqueo ciego con sobrante/faltante. Respuesta simulada si el ERP no responde."""
        res = await self.post("/api/v1/arqueos/diferencia", arqueo_data)
        if res.get("status") == "fallback":
            return {"notificacion_id": "NOT-ARQ-SIM", "estado": "recibida", "modo": "mock_fallback"}
        return res

    async def registrar_reembolso(self, reembolso_data: Dict[str, Any]) -> Dict[str, Any]:
        """KAN-55: asiento de reembolso (egreso/reversión de ingreso). Respuesta simulada si el ERP no responde."""
        res = await self.post("/api/v1/asientos/reembolso", reembolso_data)
        if res.get("status") == "fallback":
            return {"asiento_id": "ASI-RMB-SIM", "estado": "asentado", "modo": "mock_fallback"}
        return res

contabilidad_client = ContabilidadClient()
