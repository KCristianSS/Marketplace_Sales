"""Adaptador de Entregas: solicitudes durables publicadas por el worker de Pub/Sub."""
import asyncio
from fastapi import HTTPException
from backend.shared import despachos


class EntregasClient:
    async def solicitar_despacho(self, despacho_data: dict) -> dict:
        """Recupera/reintenta la solicitud ya creada por el commit de la orden."""
        return await asyncio.to_thread(despachos.operar, "reintentar",
            orden_id=str(despacho_data["orden_id"]), actor="sistema")

    async def consultar_estado_envio(self, tracking_number: str) -> dict:
        """RIO-ENT-02: cada consulta explícita encola un mensaje hacia Entregas."""
        client = despachos.get_supabase_admin_client()
        if client is None:
            raise HTTPException(503, "Se requiere persistencia para consultar Entregas.")
        filas = await asyncio.to_thread(lambda: client.table("despachos").select("orden_id")
            .eq("guia", tracking_number).limit(1).execute().data or [])
        if not filas:
            raise HTTPException(404, "Guía de despacho no encontrada.")
        return await asyncio.to_thread(despachos.operar, "consultar", orden_id=str(filas[0]["orden_id"]), actor="sistema")

entregas_client = EntregasClient()
