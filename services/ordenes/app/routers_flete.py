from fastapi import APIRouter, Depends, Response
from backend.shared.security import require_role
from backend.shared.flete_config import (
    ActualizarFlete, obtener_configuracion, guardar_configuracion, opciones_publicas,
)

router = APIRouter(prefix="/api/v1/ordenes/flete", tags=["Configuración de envíos"])
administrar_envios = require_role(["administrador", "gerente_comercial"])


@router.get("/opciones")
async def consultar_opciones(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await opciones_publicas()


@router.get("/configuracion")
async def consultar_configuracion(response: Response, usuario=Depends(administrar_envios)):
    response.headers["Cache-Control"] = "no-store"
    return await obtener_configuracion()


@router.put("/configuracion")
async def actualizar_configuracion(payload: ActualizarFlete, usuario=Depends(administrar_envios)):
    return await guardar_configuracion(payload, str(usuario["user_id"]))
