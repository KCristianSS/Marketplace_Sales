from typing import Optional, Dict, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, model_validator

class ClienteRegistro(BaseModel):
    nombre_completo: str = Field(..., min_length=2, description="Nombre completo del cliente")
    email: EmailStr = Field(..., description="Correo electrónico válido")
    password: str = Field(..., min_length=6, description="Contraseña de al menos 6 caracteres")
    telefono: Optional[str] = None
    nit_ci: Optional[str] = None
    razon_social: Optional[str] = None
    tipo_cliente: str = "retail"

class ClienteLogin(BaseModel):
    email: EmailStr = Field(..., description="Correo electrónico registrado")
    password: str = Field(..., description="Contraseña")

class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., description="Correo electrónico asociado a la cuenta")

class PerfilResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    nombre_completo: str
    email: str
    telefono: Optional[str] = None
    nit_ci: Optional[str] = None
    razon_social: Optional[str] = None
    tipo_cliente: str = "retail"
    role: str = "cliente"
    sucursal_id: Optional[str] = None
    debe_cambiar_password: bool = False
    puntos_saldo: int = 0
    preferencias_notificacion: Dict[str, bool] = {"email": True, "sms": False, "whatsapp": False}
    mensaje: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: PerfilResponse

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class DireccionCreate(BaseModel):
    direccion: str = Field(..., min_length=3, max_length=255)
    referencia: Optional[str] = Field(None, max_length=500)
    ciudad: str = Field(..., min_length=2, max_length=100)
    zona: Optional[str] = Field(None, min_length=1, max_length=100)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)
    es_predeterminada: bool = False

    @model_validator(mode="after")
    def validar_coordenadas_pareadas(self):
        if (self.latitud is None) != (self.longitud is None):
            raise ValueError("Latitud y longitud deben proporcionarse juntas.")
        return self


class DireccionUpdate(BaseModel):
    direccion: Optional[str] = Field(None, min_length=3, max_length=255)
    referencia: Optional[str] = Field(None, max_length=500)
    ciudad: Optional[str] = Field(None, min_length=2, max_length=100)
    zona: Optional[str] = Field(None, min_length=1, max_length=100)
    latitud: Optional[float] = Field(None, ge=-90, le=90)
    longitud: Optional[float] = Field(None, ge=-180, le=180)
    es_predeterminada: Optional[bool] = None

class DireccionResponse(DireccionCreate):
    id: UUID
    cliente_id: UUID

class NotificacionesConfig(BaseModel):
    email: bool = True
    sms: Literal[False] = False
    whatsapp: Literal[False] = False

class PreferenciasNotificacionBase(BaseModel):
    canal_correo: bool = Field(default=True, description="Recibir notificaciones por correo electrónico")
    canal_sms: Literal[False] = Field(default=False, description="Canal deshabilitado; solo se utiliza correo")
    canal_push: Literal[False] = Field(default=False, description="Canal deshabilitado; solo se utiliza correo")
    telefono_sms: None = None
    avisos_estado_pedido: bool = Field(default=True, description="Avisos sobre cambios de estado del pedido (incluye entrega y cancelación)")
    avisos_promociones: bool = Field(default=False, description="Avisos sobre ofertas, promociones y descuentos")
    avisos_recordatorios: bool = Field(default=False, description="Avisos y recordatorios de compra o carrito")

class PreferenciasNotificacionUpdate(PreferenciasNotificacionBase):
    pass

class PreferenciasNotificacionResponse(PreferenciasNotificacionBase):
    id: Optional[UUID] = None
    cliente_id: UUID
    updated_at: Optional[str] = None
    mensaje: Optional[str] = None

# ------------------------------------------------------------------------------
# USUARIOS INTERNOS Y GESTIÓN DE ROLES (KAN-16 / KAN-421, KAN-423)
# ------------------------------------------------------------------------------
class UsuarioInternoCreate(BaseModel):
    nombre_completo: str = Field(..., min_length=2, max_length=200, description="Nombre completo del colaborador")
    email: EmailStr = Field(..., description="Correo corporativo único")
    rol: str = Field(..., pattern="^(cajero|gerente_comercial|administrador)$", description="Rol interno del sistema")
    sucursal_id: Optional[str] = Field(None, description="Sucursal física asignada")
    sucursal_nombre: Optional[str] = Field(None, description="Nombre descriptivo de la sucursal")
    debe_cambiar_password: bool = Field(default=True, description="Obligar a cambiar la contraseña temporal en el primer acceso")

    @model_validator(mode="after")
    def validar_sucursal_cajero(self):
        if not self.debe_cambiar_password:
            raise ValueError("El cambio de contraseña en el primer ingreso es obligatorio.")
        if self.rol == "cajero" and not self.sucursal_id:
            raise ValueError("La asignación de sucursal es obligatoria para el rol 'cajero'.")
        return self

class UsuarioInternoUpdate(BaseModel):
    nombre_completo: Optional[str] = Field(None, min_length=2, max_length=200)
    rol: Optional[str] = Field(None, pattern="^(cajero|gerente_comercial|administrador)$")
    sucursal_id: Optional[str] = None
    sucursal_nombre: Optional[str] = None
    activo: Optional[bool] = None
    debe_cambiar_password: Optional[bool] = None

class UsuarioInternoResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    nombre_completo: str
    email: str
    rol: str
    sucursal_id: Optional[str] = None
    sucursal_nombre: Optional[str] = None
    activo: bool = True
    debe_cambiar_password: bool = True
    password_temporal: Optional[str] = None
    sesion_revocada: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    mensaje: Optional[str] = None


