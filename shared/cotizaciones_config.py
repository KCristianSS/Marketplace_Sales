"""Escalas B2B versionadas; todas las cotizaciones se calculan en el servidor."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EscalaB2B(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimo_unidades: int = Field(ge=1, le=10000000, strict=True)
    descuento_porcentaje: Decimal = Field(ge=0, le=100, decimal_places=2)


class ConfiguracionB2B(BaseModel):
    model_config = ConfigDict(extra="forbid")
    habilitado: bool
    escalas: list[EscalaB2B] = Field(max_length=50)

    @model_validator(mode="after")
    def validar_escalas(self):
        ordenadas = sorted(self.escalas, key=lambda e: e.minimo_unidades)
        if len({e.minimo_unidades for e in ordenadas}) != len(ordenadas):
            raise ValueError("No repitas la cantidad mínima entre escalas.")
        if any(b.descuento_porcentaje < a.descuento_porcentaje for a, b in zip(ordenadas, ordenadas[1:])):
            raise ValueError("El descuento no puede disminuir cuando aumenta la cantidad mínima.")
        self.escalas = ordenadas
        return self


class RegistroConfiguracionB2B(BaseModel):
    version: int
    configuracion: ConfiguracionB2B
    actualizado_por: Optional[UUID] = None
    actualizado_en: datetime


class ActualizarConfiguracionB2B(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    configuracion: ConfiguracionB2B


def obtener_configuracion_b2b(client) -> RegistroConfiguracionB2B:
    try:
        rows = client.table("cotizaciones_configuracion").select("*").eq("id",1).limit(1).execute().data or []
        if not rows: raise ValueError("Sin configuración")
        return RegistroConfiguracionB2B.model_validate(rows[0])
    except Exception as exc:
        raise HTTPException(503,"No se pudieron cargar los descuentos B2B. Verifica la configuración del servicio.") from exc


def descuento_b2b(cantidad: int, config: ConfiguracionB2B) -> Decimal:
    if not config.habilitado: return Decimal("0")
    return next((e.descuento_porcentaje for e in reversed(config.escalas) if cantidad>=e.minimo_unidades),Decimal("0"))


def guardar_configuracion_b2b(client, payload: ActualizarConfiguracionB2B, user: dict) -> RegistroConfiguracionB2B:
    try:
        result = client.rpc("guardar_configuracion_cotizaciones", {
            "p_version":payload.version,"p_configuracion":payload.configuracion.model_dump(mode="json"),"p_actor":user["user_id"],
        }).execute().data
    except Exception as exc:
        raise HTTPException(503,"No se pudieron guardar los descuentos. Tus cambios siguen disponibles.") from exc
    if not isinstance(result,dict): raise HTTPException(503,"La base de datos no confirmó los cambios.")
    if result.get("error"): raise HTTPException(result.get("status",409),result["error"])
    record = RegistroConfiguracionB2B.model_validate(result["registro"])
    from backend.shared.audit import registrar_auditoria
    registrar_auditoria(client,current_user=user,accion="DESCUENTOS_B2B_ACTUALIZADOS",entidad="cotizaciones_configuracion",
        antes=result["anterior"],despues=result["registro"])
    return record
