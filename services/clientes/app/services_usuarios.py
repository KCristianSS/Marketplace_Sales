"""
Servicio de Usuarios Internos (KAN-421 / KAN-423).
Administración de cajeros, gerentes comerciales y administradores con RBAC,
asignación de sucursales, generación de contraseñas temporales, revocación de sesiones
y registro de auditoría en audit_logs.
"""
import uuid
import secrets
import string
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import HTTPException, status

try:
    from app.schemas import (
        UsuarioInternoCreate,
        UsuarioInternoUpdate,
        UsuarioInternoResponse,
    )
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.schemas import (
        UsuarioInternoCreate,
        UsuarioInternoUpdate,
        UsuarioInternoResponse,
    )

from backend.shared.database import get_supabase_admin_client
from backend.shared.security import get_password_hash
from backend.shared.config import settings

logger = logging.getLogger("maxiconecta.admin.usuarios")

# Almacén en memoria persistente para entornos de desarrollo, tests y fallbacks
_USUARIOS_INTERNOS_DB: Dict[str, Dict[str, Any]] = {}

def _generar_password_temporal(longitud: int = 12) -> str:
    """Genera una contraseña temporal segura con letras, números y símbolos."""
    caracteres = string.ascii_letters + string.digits + "!@#$%&*"
    # Garantizar al menos una mayúscula, un dígito y un caracter especial
    parte1 = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%&*")
    ]
    parte2 = [secrets.choice(caracteres) for _ in range(longitud - 3)]
    lista = parte1 + parte2
    secrets.SystemRandom().shuffle(lista)
    return "".join(lista)


def _init_seed_usuarios_internos():
    """Inicializa cuentas internas semilla del sistema MaxiConecta."""
    seeds = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "user_id": "00000000-0000-0000-0000-000000000001",
            "nombre_completo": "Cesar Admin (Líder Grupo E)",
            "email": "admin@maxiconecta.bo",
            "rol": "administrador",
            "sucursal_id": None,
            "sucursal_nombre": "Acceso Corporativo Global",
            "activo": True,
            "debe_cambiar_password": False,
            "password_temporal": None,
            "sesion_revocada": False,
            "created_at": "2026-01-01T08:00:00Z",
            "updated_at": "2026-01-01T08:00:00Z"
        },
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "user_id": "00000000-0000-0000-0000-000000000002",
            "nombre_completo": "Cajero Sucursal Central",
            "email": "cajero@maxiconecta.bo",
            "rol": "cajero",
            "sucursal_id": "SUC-01",
            "sucursal_nombre": "Sucursal Central - La Paz",
            "activo": True,
            "debe_cambiar_password": False,
            "password_temporal": None,
            "sesion_revocada": False,
            "created_at": "2026-01-01T08:00:00Z",
            "updated_at": "2026-01-01T08:00:00Z"
        },
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "user_id": "00000000-0000-0000-0000-000000000003",
            "nombre_completo": "Gerente Comercial ERP",
            "email": "gerente@maxiconecta.bo",
            "rol": "gerente_comercial",
            "sucursal_id": None,
            "sucursal_nombre": "Supervisión Regional",
            "activo": True,
            "debe_cambiar_password": False,
            "password_temporal": None,
            "sesion_revocada": False,
            "created_at": "2026-01-01T08:00:00Z",
            "updated_at": "2026-01-01T08:00:00Z"
        }
    ]
    for s in seeds:
        if s["id"] not in _USUARIOS_INTERNOS_DB:
            _USUARIOS_INTERNOS_DB[s["id"]] = s

_init_seed_usuarios_internos()


class UsuariosInternosService:
    """
    Lógica de negocio y persistencia para KAN-421 / KAN-423.
    """

    @classmethod
    def registrar_audit_log(
        cls,
        action: str,
        user_id: Optional[str],
        user_role: str,
        entity_id: Optional[str],
        payload_before: Optional[Dict[str, Any]] = None,
        payload_after: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Registra la operación en la tabla audit_logs de PostgreSQL/Supabase."""
        from backend.shared.audit import registrar_auditoria
        registrar_auditoria(get_supabase_admin_client(), current_user={"user_id": user_id, "role": user_role},
            accion=action, entidad="usuarios_internos", entidad_id=entity_id,
            antes=payload_before, despues=payload_after)

    @classmethod
    def listar(
        cls,
        rol: Optional[str] = None,
        activo: Optional[bool] = None,
        sucursal_id: Optional[str] = None,
        q: Optional[str] = None
    ) -> List[UsuarioInternoResponse]:
        """Lista usuarios internos con soporte de filtros y búsqueda."""
        supabase = get_supabase_admin_client()
        lista_raw: List[Dict[str, Any]] = []

        if supabase:
            try:
                query = supabase.table("usuarios_internos").select("*")
                if rol:
                    query = query.eq("rol", rol)
                if activo is not None:
                    query = query.eq("activo", activo)
                if sucursal_id:
                    query = query.eq("sucursal_id", sucursal_id)
                res = query.order("created_at", desc=True).execute()
                if res.data:
                    lista_raw = res.data
            except Exception as e:
                logger.exception("Fallo consulta usuarios_internos en Supabase")
                raise HTTPException(503, "No se pudieron consultar los usuarios internos.") from e

        if not supabase:
            if settings.ENVIRONMENT != 'testing':
                raise HTTPException(503, "La gestión de usuarios requiere conexión con la base de datos.")
            lista_raw = list(_USUARIOS_INTERNOS_DB.values())

        # Filtrar en memoria si aplica
        resultados = []
        q_clean = q.lower().strip() if q else ""
        for u in lista_raw:
            if rol and u.get("rol") != rol:
                continue
            if activo is not None and bool(u.get("activo")) != activo:
                continue
            if sucursal_id and u.get("sucursal_id") != sucursal_id:
                continue
            if q_clean:
                nombre = str(u.get("nombre_completo", "")).lower()
                email = str(u.get("email", "")).lower()
                if q_clean not in nombre and q_clean not in email:
                    continue

            resultados.append(
                UsuarioInternoResponse(
                    id=uuid.UUID(str(u["id"])),
                    user_id=uuid.UUID(str(u["user_id"])) if u.get("user_id") else None,
                    nombre_completo=u["nombre_completo"],
                    email=u["email"],
                    rol=u["rol"],
                    sucursal_id=u.get("sucursal_id"),
                    sucursal_nombre=u.get("sucursal_nombre"),
                    activo=bool(u.get("activo", True)),
                    debe_cambiar_password=bool(u.get("debe_cambiar_password", True)),
                    password_temporal=None,
                    sesion_revocada=bool(u.get("sesion_revocada", False)),
                    created_at=str(u.get("created_at", "")),
                    updated_at=str(u.get("updated_at", ""))
                )
            )
        return resultados

    @classmethod
    def obtener_por_id(cls, usuario_id: uuid.UUID) -> UsuarioInternoResponse:
        """Obtiene un usuario interno por ID."""
        uid_str = str(usuario_id)
        supabase = get_supabase_admin_client()
        if supabase:
            try:
                res = supabase.table("usuarios_internos").select("*").eq("id", uid_str).limit(1).execute()
                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    return UsuarioInternoResponse(
                        id=uuid.UUID(str(row["id"])),
                        user_id=uuid.UUID(str(row["user_id"])) if row.get("user_id") else None,
                        nombre_completo=row["nombre_completo"],
                        email=row["email"],
                        rol=row["rol"],
                        sucursal_id=row.get("sucursal_id"),
                        sucursal_nombre=row.get("sucursal_nombre"),
                        activo=bool(row.get("activo", True)),
                        debe_cambiar_password=bool(row.get("debe_cambiar_password", True)),
                        password_temporal=None,
                        sesion_revocada=bool(row.get("sesion_revocada", False)),
                        created_at=str(row.get("created_at", "")),
                        updated_at=str(row.get("updated_at", ""))
                    )
                raise HTTPException(404, "Usuario interno no encontrado.")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(503, "No se pudo consultar el usuario interno.") from e

        if settings.ENVIRONMENT != 'testing':
            raise HTTPException(503, "La gestión de usuarios requiere conexión con la base de datos.")

        if uid_str in _USUARIOS_INTERNOS_DB:
            row = _USUARIOS_INTERNOS_DB[uid_str]
            return UsuarioInternoResponse(
                id=uuid.UUID(str(row["id"])),
                user_id=uuid.UUID(str(row["user_id"])) if row.get("user_id") else None,
                nombre_completo=row["nombre_completo"],
                email=row["email"],
                rol=row["rol"],
                sucursal_id=row.get("sucursal_id"),
                sucursal_nombre=row.get("sucursal_nombre"),
                activo=bool(row.get("activo", True)),
                debe_cambiar_password=bool(row.get("debe_cambiar_password", True)),
                password_temporal=row.get("password_temporal"),
                sesion_revocada=bool(row.get("sesion_revocada", False)),
                created_at=str(row.get("created_at", "")),
                updated_at=str(row.get("updated_at", ""))
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario interno no encontrado.")

    @classmethod
    def crear(
        cls,
        payload: UsuarioInternoCreate,
        admin_id: Optional[str] = None,
        admin_role: str = "administrador"
    ) -> UsuarioInternoResponse:
        """
        Crea un usuario interno (cajero, gerente comercial, administrador):
        - Valida que el email no esté duplicado.
        - Genera una contraseña temporal segura.
        - Obliga a cambiarla en el primer ingreso.
        - Registra la auditoría en audit_logs.
        """
        email_clean = payload.email.lower().strip()
        supabase = get_supabase_admin_client()
        if supabase is not None:
            return cls._crear_persistido(supabase, payload, admin_id, admin_role)
        if settings.ENVIRONMENT != 'testing':
            raise HTTPException(503, "La gestión de usuarios requiere conexión con la base de datos.")

        # 1. Criterio: Dado un correo ya registrado, entonces el sistema no permite duplicarlo
        for u in _USUARIOS_INTERNOS_DB.values():
            if u["email"].lower().strip() == email_clean:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El correo electrónico '{payload.email}' ya se encuentra registrado para otro colaborador."
                )

        supabase = get_supabase_admin_client()
        if supabase:
            try:
                res = supabase.table("usuarios_internos").select("id").eq("email", email_clean).limit(1).execute()
                if res.data and len(res.data) > 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"El correo electrónico '{payload.email}' ya se encuentra registrado."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning("Fallo al verificar duplicidad en Supabase: %s", e)

        # 2. Generar contraseña temporal segura
        password_temporal = _generar_password_temporal(12)
        nuevo_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        user_record = {
            "id": nuevo_id,
            "user_id": nuevo_id,
            "nombre_completo": payload.nombre_completo.strip(),
            "email": email_clean,
            "rol": payload.rol,
            "sucursal_id": payload.sucursal_id,
            "sucursal_nombre": payload.sucursal_nombre or ("Acceso Central" if payload.rol != "cajero" else "Sucursal Asignada"),
            "activo": True,
            "debe_cambiar_password": payload.debe_cambiar_password,
            "password_temporal": password_temporal,
            "sesion_revocada": False,
            "created_at": now_iso,
            "updated_at": now_iso
        }

        # 3. Guardar en memoria
        _USUARIOS_INTERNOS_DB[nuevo_id] = user_record

        # 4. Intentar guardar en Supabase (tabla usuarios_internos y Supabase Auth Admin si está disponible)
        if supabase:
            try:
                supabase.table("usuarios_internos").insert({
                    "id": nuevo_id,
                    "user_id": nuevo_id,
                    "nombre_completo": user_record["nombre_completo"],
                    "email": email_clean,
                    "rol": payload.rol,
                    "sucursal_id": payload.sucursal_id,
                    "sucursal_nombre": user_record["sucursal_nombre"],
                    "activo": True,
                    "debe_cambiar_password": payload.debe_cambiar_password,
                    "password_temporal": password_temporal,
                    "sesion_revocada": False,
                    "created_at": now_iso,
                    "updated_at": now_iso
                }).execute()
            except Exception as e:
                logger.warning("Fallo al insertar usuario_interno en Supabase: %s", e)

        # 5. Criterio: Todas las operaciones se registran en audit_logs
        cls.registrar_audit_log(
            action="CREAR_USUARIO_INTERNO",
            user_id=admin_id,
            user_role=admin_role,
            entity_id=nuevo_id,
            payload_before=None,
            payload_after={
                "id": nuevo_id,
                "email": email_clean,
                "rol": payload.rol,
                "sucursal_id": payload.sucursal_id,
                "debe_cambiar_password": payload.debe_cambiar_password
            }
        )

        return UsuarioInternoResponse(
            id=uuid.UUID(nuevo_id),
            user_id=uuid.UUID(nuevo_id),
            nombre_completo=user_record["nombre_completo"],
            email=email_clean,
            rol=payload.rol,
            sucursal_id=payload.sucursal_id,
            sucursal_nombre=user_record["sucursal_nombre"],
            activo=True,
            debe_cambiar_password=payload.debe_cambiar_password,
            password_temporal=password_temporal,
            sesion_revocada=False,
            created_at=now_iso,
            updated_at=now_iso,
            mensaje="Usuario interno creado exitosamente con contraseña temporal asignada."
        )

    @classmethod
    def _crear_persistido(cls, client, payload, admin_id, admin_role):
        email = payload.email.lower().strip()
        try:
            if client.table('usuarios_internos').select('id').eq('email', email).limit(1).execute().data:
                raise HTTPException(409, 'El correo electrónico ya se encuentra registrado.')
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, 'No se pudo verificar el registro de usuarios.') from exc
        password = _generar_password_temporal()
        try:
            auth = client.auth.admin.create_user({
                'email': email, 'password': password, 'email_confirm': True,
                'app_metadata': {'role': payload.rol, 'sucursal_id': payload.sucursal_id},
                'user_metadata': {'nombre_completo': payload.nombre_completo.strip()},
            })
        except Exception as exc:
            if getattr(exc, 'code', '') in {'email_exists', 'user_already_exists'} or 'already' in str(exc).lower():
                raise HTTPException(409, 'El correo ya tiene una cuenta de acceso. Utiliza otro correo.') from exc
            raise HTTPException(503, 'No se pudo crear la cuenta de acceso. Intenta nuevamente.') from exc
        if not auth.user:
            raise HTTPException(503, 'El proveedor no confirmó la creación de la cuenta.')
        identifier = str(uuid.uuid4())
        row = {'id': identifier, 'user_id': str(auth.user.id), 'nombre_completo': payload.nombre_completo.strip(),
               'email': email, 'rol': payload.rol, 'sucursal_id': payload.sucursal_id,
               'sucursal_nombre': payload.sucursal_nombre, 'activo': True,
               'debe_cambiar_password': payload.debe_cambiar_password, 'sesion_revocada': False}
        try:
            rows = client.table('usuarios_internos').insert(row).execute().data
            if not rows:
                raise RuntimeError('Registro no confirmado')
        except Exception as exc:
            try:
                client.auth.admin.delete_user(str(auth.user.id))
            except Exception:
                logger.exception('No se pudo revertir la cuenta de acceso tras fallar el registro interno')
            raise HTTPException(503, 'No se pudo guardar el usuario interno. No se confirmó el alta.') from exc
        cls.registrar_audit_log('CREAR_USUARIO_INTERNO', admin_id, admin_role, identifier, payload_after=row)
        result = cls.obtener_por_id(uuid.UUID(identifier))
        result.password_temporal = password
        result.mensaje = 'Usuario interno y cuenta de acceso creados.'
        return result

    @classmethod
    def actualizar(
        cls,
        usuario_id: uuid.UUID,
        payload: UsuarioInternoUpdate,
        admin_id: Optional[str] = None,
        admin_role: str = "administrador"
    ) -> UsuarioInternoResponse:
        """
        Modifica datos, rol o sucursal de un usuario interno.
        Si se desactiva, revoca de inmediato su sesión.
        Registra la auditoría en audit_logs.
        """
        actual = cls.obtener_por_id(usuario_id)
        uid_str = str(usuario_id)
        payload_before = actual.model_dump(mode="json")

        nuevo_rol = payload.rol or actual.rol
        nueva_sucursal = payload.sucursal_id if payload.sucursal_id is not None else actual.sucursal_id
        if nuevo_rol == "cajero" and not nueva_sucursal:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No se puede asignar el rol de cajero sin definir una sucursal física."
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        nuevo_activo = payload.activo if payload.activo is not None else actual.activo

        # Criterio: Dado un usuario desactivado, entonces su sesión se revoca y no puede volver a ingresar
        sesion_revocada = actual.sesion_revocada
        if nuevo_activo is False and actual.activo is True:
            sesion_revocada = True

        cambios: Dict[str, Any] = {
            "updated_at": now_iso,
            "sesion_revocada": sesion_revocada
        }
        if payload.nombre_completo is not None:
            cambios["nombre_completo"] = payload.nombre_completo.strip()
        if payload.rol is not None:
            cambios["rol"] = payload.rol
        if payload.sucursal_id is not None:
            cambios["sucursal_id"] = payload.sucursal_id
        if payload.sucursal_nombre is not None:
            cambios["sucursal_nombre"] = payload.sucursal_nombre
        if payload.activo is not None:
            cambios["activo"] = payload.activo
        if payload.debe_cambiar_password is not None:
            cambios["debe_cambiar_password"] = payload.debe_cambiar_password

        # Actualizar memoria
        if uid_str in _USUARIOS_INTERNOS_DB:
            _USUARIOS_INTERNOS_DB[uid_str].update(cambios)

        # Actualizar Supabase
        supabase = get_supabase_admin_client()
        if supabase:
            try:
                supabase.table("usuarios_internos").update(cambios).eq("id", uid_str).execute()
            except Exception as e:
                raise HTTPException(503, "No se pudieron guardar los cambios del usuario.") from e

        # Registrar en audit_logs
        cls.registrar_audit_log(
            action="ACTUALIZAR_USUARIO_INTERNO",
            user_id=admin_id,
            user_role=admin_role,
            entity_id=uid_str,
            payload_before=payload_before,
            payload_after={**payload_before, **cambios}
        )

        return cls.obtener_por_id(usuario_id)

    @classmethod
    def desactivar(
        cls,
        usuario_id: uuid.UUID,
        admin_id: Optional[str] = None,
        admin_role: str = "administrador"
    ) -> UsuarioInternoResponse:
        """
        Desactiva un usuario interno y revoca de inmediato su sesión.
        """
        return cls.actualizar(
            usuario_id=usuario_id,
            payload=UsuarioInternoUpdate(activo=False),
            admin_id=admin_id,
            admin_role=admin_role
        )
