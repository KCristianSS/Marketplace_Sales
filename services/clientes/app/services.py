"""Preferencias de notificación por correo para clientes (KAN-42)."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException
try:
    from app.schemas import PreferenciasNotificacionBase, PreferenciasNotificacionUpdate, PreferenciasNotificacionResponse
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.schemas import PreferenciasNotificacionBase, PreferenciasNotificacionUpdate, PreferenciasNotificacionResponse
from backend.shared.database import get_supabase_admin_client
from backend.shared.config import settings

logger = logging.getLogger('maxiconecta.clientes.services')
_PREFERENCIAS_DB = {}


class PreferenciasService:
    @classmethod
    def validar_preferencias(cls, payload: PreferenciasNotificacionBase):
        if payload.avisos_estado_pedido and not payload.canal_correo:
            raise HTTPException(422, 'Activa el correo para recibir las actualizaciones de tus pedidos, o desactiva ese tipo de aviso.')

    @classmethod
    def obtener_default(cls, cliente_id: uuid.UUID, telefono_cliente: Optional[str] = None):
        return PreferenciasNotificacionResponse(cliente_id=cliente_id, mensaje='Preferencias por defecto: correo activo.')

    @classmethod
    def _respuesta(cls, cliente_id, row, mensaje):
        return PreferenciasNotificacionResponse(
            id=row.get('id'), cliente_id=cliente_id, canal_correo=bool(row.get('canal_correo', True)),
            avisos_estado_pedido=bool(row.get('avisos_estado_pedido', True)),
            avisos_promociones=bool(row.get('avisos_promociones', False)),
            avisos_recordatorios=bool(row.get('avisos_recordatorios', False)),
            updated_at=row.get('updated_at'), mensaje=mensaje)

    @classmethod
    def obtener_preferencias(cls, cliente_id: uuid.UUID, telefono_cliente: Optional[str] = None):
        client = get_supabase_admin_client()
        if client:
            try:
                rows = client.table('preferencias_notificacion').select('*').eq('cliente_id', str(cliente_id)).limit(1).execute().data or []
            except Exception as exc:
                logger.warning('No se pudieron consultar las preferencias: %s', type(exc).__name__)
                raise HTTPException(503, 'No se pudieron recuperar tus preferencias. Inténtalo nuevamente.') from exc
            return cls._respuesta(cliente_id, rows[0], 'Preferencias recuperadas.') if rows else cls.obtener_default(cliente_id)
        if settings.ENVIRONMENT != 'testing':
            raise HTTPException(503, 'El servicio de preferencias no está disponible.')
        row = _PREFERENCIAS_DB.get(str(cliente_id))
        return cls._respuesta(cliente_id, row, 'Preferencias recuperadas.') if row else cls.obtener_default(cliente_id)

    @classmethod
    def actualizar_preferencias(cls, cliente_id: uuid.UUID, payload: PreferenciasNotificacionUpdate, telefono_cliente: Optional[str] = None):
        cls.validar_preferencias(payload)
        row = {**payload.model_dump(), 'cliente_id': str(cliente_id), 'canal_sms': False, 'canal_push': False,
               'telefono_sms': None, 'updated_at': datetime.now(timezone.utc).isoformat()}
        client = get_supabase_admin_client()
        if client:
            try:
                rows = client.table('preferencias_notificacion').upsert(row, on_conflict='cliente_id').execute().data or []
                if not rows:
                    raise RuntimeError('Guardado no confirmado')
                row = rows[0]
            except Exception as exc:
                logger.warning('No se pudieron guardar las preferencias: %s', type(exc).__name__)
                raise HTTPException(503, 'No se guardaron tus preferencias. Inténtalo nuevamente.') from exc
        elif settings.ENVIRONMENT == 'testing':
            row['id'] = _PREFERENCIAS_DB.get(str(cliente_id), {}).get('id', str(uuid.uuid4()))
            _PREFERENCIAS_DB[str(cliente_id)] = row
        else:
            raise HTTPException(503, 'El servicio de preferencias no está disponible.')
        return cls._respuesta(cliente_id, row, 'Preferencias de correo guardadas.')
