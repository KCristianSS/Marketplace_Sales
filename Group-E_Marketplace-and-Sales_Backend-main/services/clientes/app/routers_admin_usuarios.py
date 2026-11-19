"""
Endpoints REST para la gestión de usuarios internos y roles (KAN-421, KAN-424).
Protegido por RBAC: solo administradores pueden crear, listar, editar o desactivar.
"""
import uuid
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

try:
    from app.schemas import (
        UsuarioInternoCreate,
        UsuarioInternoUpdate,
        UsuarioInternoResponse,
    )
    from app.services_usuarios import UsuariosInternosService
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.schemas import (
        UsuarioInternoCreate,
        UsuarioInternoUpdate,
        UsuarioInternoResponse,
    )
    from backend.services.clientes.app.services_usuarios import UsuariosInternosService

from backend.shared.security import get_current_user
from backend.shared.audit_context import trusted_role

logger = logging.getLogger("maxiconecta.admin.usuarios.api")

router = APIRouter(prefix="/api/v1/admin/usuarios", tags=["Administración de Usuarios y Roles (RBAC)"])


def _verificar_rol_administrador(current_user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verifica que el usuario solicitante cuente con rol 'administrador'.
    Criterio: Dado un usuario interno, entonces solo un administrador puede crearlo, editarlo o desactivarlo.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación para acceder a la administración de usuarios."
        )
    user_role = trusted_role(current_user.get("payload") or {})
    if user_role != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: El rol '{user_role}' no tiene permisos para gestionar usuarios internos. Requiere rol 'administrador'."
        )
    return current_user


@router.get("", response_model=List[UsuarioInternoResponse])
@router.get("/", response_model=List[UsuarioInternoResponse])
async def listar_usuarios_internos(
    rol: Optional[str] = Query(None, description="Filtrar por rol: cajero, gerente_comercial, administrador"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado: true o false"),
    sucursal_id: Optional[str] = Query(None, description="Filtrar por ID de sucursal"),
    q: Optional[str] = Query(None, description="Búsqueda por nombre o correo"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    KAN-424: Lista el personal interno del sistema con filtros de rol, sucursal y estado.
    Exclusivo para administradores.
    """
    _verificar_rol_administrador(current_user)
    return UsuariosInternosService.listar(
        rol=rol,
        activo=activo,
        sucursal_id=sucursal_id,
        q=q
    )


@router.post("", response_model=UsuarioInternoResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=UsuarioInternoResponse, status_code=status.HTTP_201_CREATED)
async def crear_usuario_interno(
    payload: UsuarioInternoCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    KAN-424: Da de alta un nuevo usuario interno, genera contraseña temporal y audita la acción.
    """
    admin = _verificar_rol_administrador(current_user)
    return UsuariosInternosService.crear(
        payload=payload,
        admin_id=str(admin.get("user_id") or admin.get("id")),
        admin_role=admin.get("role", "administrador")
    )


@router.get("/{usuario_id}", response_model=UsuarioInternoResponse)
async def obtener_usuario_interno(
    usuario_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Obtiene los detalles de un colaborador interno por ID."""
    _verificar_rol_administrador(current_user)
    return UsuariosInternosService.obtener_por_id(usuario_id)


@router.patch("/{usuario_id}", response_model=UsuarioInternoResponse)
async def actualizar_usuario_interno(
    usuario_id: uuid.UUID,
    payload: UsuarioInternoUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    KAN-424: Modifica nombre, rol o sucursal. Si se desactiva, revoca su sesión.
    """
    admin = _verificar_rol_administrador(current_user)
    return UsuariosInternosService.actualizar(
        usuario_id=usuario_id,
        payload=payload,
        admin_id=str(admin.get("user_id") or admin.get("id")),
        admin_role=admin.get("role", "administrador")
    )


@router.delete("/{usuario_id}", response_model=UsuarioInternoResponse)
async def desactivar_usuario_interno(
    usuario_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    KAN-424: Desactiva inmediatamente la cuenta del colaborador y revoca su sesión.
    """
    admin = _verificar_rol_administrador(current_user)
    return UsuariosInternosService.desactivar(
        usuario_id=usuario_id,
        admin_id=str(admin.get("user_id") or admin.get("id")),
        admin_role=admin.get("role", "administrador")
    )
