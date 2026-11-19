from uuid import UUID
from fastapi import APIRouter, Depends, Query
from backend.shared.security import get_current_user, require_jwt_claims
try:
    from app.services_crm_sync import crm_sync_service
except (ModuleNotFoundError, ImportError):
    from backend.services.clientes.app.services_crm_sync import crm_sync_service

router = APIRouter(prefix='/api/v1/clientes', tags=['Sincronización CRM por Pub/Sub'])


@router.get('/sync/estado', response_model=dict)
@require_jwt_claims('sub', allowed_roles={'administrador', 'gerente_comercial'})
def get_sync_estado(current_user: dict = Depends(get_current_user)):
    return crm_sync_service.obtener_estado_general()


@router.post('/{cliente_id}/resincronizar', status_code=202, response_model=dict)
@require_jwt_claims('sub', allowed_roles={'administrador', 'gerente_comercial'})
async def resincronizar_cliente(cliente_id: UUID, current_user: dict = Depends(get_current_user)):
    item = await crm_sync_service.resincronizar_cliente(cliente_id)
    return {'status': 'pendiente', 'mensaje': 'Cliente encolado para envío al CRM por Pub/Sub.', 'outbox_item': item}


@router.post('/sync/procesar-outbox', response_model=dict)
@require_jwt_claims('sub', allowed_roles={'administrador', 'gerente_comercial'})
async def procesar_outbox(batch_size: int = Query(10, ge=1, le=50), current_user: dict = Depends(get_current_user)):
    items = await crm_sync_service.procesar_outbox_pendientes(batch_size)
    return {'status': 'success', 'procesados_total': len(items), 'items': items}


@router.get('/sync/verificacion-crm', response_model=dict)
@require_jwt_claims('sub', allowed_roles={'administrador', 'gerente_comercial'})
def get_verificacion_crm(current_user: dict = Depends(get_current_user)):
    data = crm_sync_service.obtener_estado_general()
    return {'status': 'success', 'topic': data['topic'], 'verificaciones': data['ultimas_verificaciones_crm'], 'metricas': data['crm_verificacion_metricas']}
