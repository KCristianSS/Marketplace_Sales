from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.shared.audit import registrar_auditoria
from backend.shared.audit_context import trusted_role
from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_current_user

router = APIRouter(prefix="/api/v1/clientes/corporativos",tags=["Empresas para cotizaciones B2B"])


class EmpresaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid",str_strip_whitespace=True)
    nit_ci: str = Field(pattern=r"^[0-9]{5,20}$")
    razon_social: str = Field(min_length=2,max_length=200)
    email: EmailStr = Field(max_length=150)
    nombre_completo: Optional[str] = Field(None,min_length=2,max_length=200)
    telefono: Optional[str] = Field(None,max_length=50)

    @field_validator("email")
    @classmethod
    def normalizar_correo(cls,value): return str(value).lower()


class EmpresaResponse(BaseModel):
    id: UUID
    nombre_completo: str
    razon_social: Optional[str] = None
    nit_ci: str
    email: str
    telefono: Optional[str] = None


class RegistroEmpresaResponse(BaseModel):
    cliente: EmpresaResponse
    creado: bool


@router.post("",response_model=RegistroEmpresaResponse,status_code=201,
             summary="Registrar una empresa comercial sin crear una cuenta de acceso")
def registrar_empresa(payload: EmpresaCreate,response: Response,current_user: dict=Depends(get_current_user)):
    if trusted_role(current_user.get("payload") or {}) not in {"administrador","gerente_comercial"}:
        raise HTTPException(403,"Solo administración y gerencia comercial pueden registrar empresas.")
    client = get_supabase_admin_client()
    if client is None: raise HTTPException(503,"El registro de empresas requiere conexión con la base de datos.")
    try:
        result = client.rpc("registrar_empresa_b2b",{"p_datos":payload.model_dump(mode="json",exclude_none=True)}).execute().data
    except Exception as exc:
        raise HTTPException(503,"No se pudo registrar la empresa. Intenta nuevamente.") from exc
    if not isinstance(result,dict): raise HTTPException(503,"La base de datos no confirmó el registro de la empresa.")
    if result.get("error"): raise HTTPException(result.get("status",409),result["error"])
    if result["creado"]:
        registrar_auditoria(client,current_user=current_user,accion="EMPRESA_B2B_REGISTRADA",entidad="perfiles_clientes",
            entidad_id=result["cliente"]["id"],despues=result["cliente"])
    else:
        response.status_code=200
    return result
