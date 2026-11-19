"""Configuración versionada de envíos; Supabase en producción, memoria en desarrollo."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import List
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.shared.config import settings
from backend.shared.database import get_supabase_admin_client


class ZonaFlete(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    ciudad: str = Field(min_length=2, max_length=100)
    nombre: str = Field(min_length=2, max_length=150)
    tarifa_base: Decimal = Field(ge=0, le=1000000, max_digits=12, decimal_places=2)
    activa: bool = True
    estandar_habilitado: bool = True
    express_habilitado: bool = True
    plazo_estandar: str = Field(min_length=3, max_length=160)
    plazo_express: str = Field(min_length=3, max_length=160)


class ConfiguracionFlete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    envio_gratis_habilitado: bool = True
    umbral_envio_gratis: Decimal = Field(default=Decimal("500"), ge=0, le=1000000, decimal_places=2)
    recargo_express: Decimal = Field(default=Decimal("15"), ge=0, le=1000000, decimal_places=2)
    peso_incluido_kg: Decimal = Field(default=Decimal("5"), ge=0, le=100000, decimal_places=3)
    recargo_por_kg: Decimal = Field(default=Decimal("5"), ge=0, le=1000000, decimal_places=2)
    peso_estimado_por_unidad_kg: Decimal = Field(default=Decimal("1.5"), gt=0, le=100000, decimal_places=3)
    zonas: List[ZonaFlete] = Field(max_length=1000)

    @model_validator(mode="after")
    def zonas_unicas(self):
        ciudades = {}
        for zona in self.zonas:
            zona.ciudad = ciudades.setdefault(zona.ciudad.casefold(), zona.ciudad)
        ids = [z.id for z in self.zonas]
        destinos = [(z.ciudad.casefold(), z.nombre.casefold()) for z in self.zonas]
        if len(set(ids)) != len(ids) or len(set(destinos)) != len(destinos):
            raise ValueError("No se permiten zonas duplicadas en una misma ciudad ni identificadores repetidos.")
        for zona in self.zonas:
            if zona.activa and not (zona.estandar_habilitado or zona.express_habilitado):
                raise ValueError(f"La zona {zona.nombre} debe tener alguna modalidad habilitada o desactivarse.")
        return self


class ActualizarFlete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    configuracion: ConfiguracionFlete


def configuracion_inicial():
    datos = json.loads(Path(__file__).with_name("flete_defaults.json").read_text(encoding="utf-8"))
    return ConfiguracionFlete.model_validate(datos).model_dump(mode="json")


_MEMORIA = None
_LOCK = asyncio.Lock()


def _cliente():
    client = get_supabase_admin_client()
    key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    configurado = bool(key and key != "anon-key")
    if client is None and (configurado or settings.ENVIRONMENT.lower() not in {"development", "testing", "test", "local"}):
        raise HTTPException(503, "No está disponible la configuración de envíos.")
    return client


async def obtener_configuracion():
    global _MEMORIA
    client = _cliente()
    if client is not None:
        try:
            rows = client.table("flete_configuracion").select("*").eq("id", 1).limit(1).execute().data or []
            if not rows:
                raise ValueError("Falta la configuración inicial")
            row = rows[0]
            config = ConfiguracionFlete.model_validate(row["configuracion"]).model_dump(mode="json")
            return {**row, "configuracion": config, "almacenamiento": "base_datos"}
        except Exception as exc:
            raise HTTPException(503, "No se pudo leer la configuración de envíos. Verifica la conexión y la migración de envíos.") from exc
    if _MEMORIA is None:
        _MEMORIA = dict(version=1, configuracion=configuracion_inicial(), actualizado_por=None, actualizado_en=None)
    return {**deepcopy(_MEMORIA), "almacenamiento": "memoria"}


async def guardar_configuracion(payload: ActualizarFlete, usuario: str):
    global _MEMORIA
    try:
        anterior = await obtener_configuracion()
    except Exception:
        anterior = {"_auditoria": "Valor anterior no disponible."}
    cambios = dict(configuracion=payload.configuracion.model_dump(mode="json"),
                   version=payload.version + 1, actualizado_por=usuario,
                   actualizado_en=datetime.now(timezone.utc).isoformat())
    client = _cliente()
    if client is not None:
        try:
            rows = client.table("flete_configuracion").update(cambios).eq("id", 1).eq("version", payload.version).execute().data or []
        except Exception as exc:
            raise HTTPException(503, "No se pudieron guardar las reglas de envío. Los cambios no se aplicaron.") from exc
        if not rows:
            raise HTTPException(409, "Otro administrador actualizó los envíos. Recarga la configuración antes de guardar.")
        from backend.shared.audit import registrar_auditoria
        registrar_auditoria(client, current_user={"user_id": usuario}, accion="REGLAS_ENVIO_ACTUALIZADAS",
            entidad="flete_configuracion", antes=anterior, despues=rows[0])
        return {**rows[0], "almacenamiento": "base_datos"}
    async with _LOCK:
        actual = await obtener_configuracion()
        if actual["version"] != payload.version:
            raise HTTPException(409, "Otro administrador actualizó los envíos. Recarga la configuración antes de guardar.")
        _MEMORIA = cambios
        from backend.shared.audit import registrar_auditoria
        registrar_auditoria(None, current_user={"user_id": usuario}, accion="REGLAS_ENVIO_ACTUALIZADAS",
            entidad="flete_configuracion", antes=anterior, despues=cambios)
        return {**deepcopy(cambios), "almacenamiento": "memoria"}


async def opciones_publicas():
    actual = await obtener_configuracion()
    config = ConfiguracionFlete.model_validate(actual["configuracion"])
    return dict(version=actual["version"], envio_gratis_habilitado=config.envio_gratis_habilitado,
                umbral_envio_gratis=config.umbral_envio_gratis,
                zonas=[z.model_dump(mode="json", exclude={"activa"}) for z in config.zonas if z.activa])
