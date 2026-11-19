import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from backend.services.clientes.app import services_crm_sync as crm
from backend.services.clientes.app.main import app
from backend.shared.security import create_access_token


def evento():
    return {'id': str(uuid4()), 'event_id': str(uuid4()), 'cliente_id': str(uuid4()),
            'event_type': 'cliente.actualizado', 'lease_id': str(uuid4()),
            'payload': {'nombre_completo': 'Prueba', 'direcciones': []}}


@pytest.mark.parametrize('publicado', [True, False])
def test_publica_con_envelope_compartido_y_no_confunde_fallback_con_sincronizado(monkeypatch, publicado):
    item = evento()
    llamadas = []
    def operar(accion, **datos):
        llamadas.append((accion, datos))
        if accion == 'reclamar': return {'eventos': [item]}
        return {'estado': 'publicado' if datos['message_id'] else 'reintentando', **datos}
    publisher = AsyncMock(return_value={'status': 'PUBLICADO' if publicado else 'FALLBACK_OFFLINE', 'message_id': 'gcp-123' if publicado else 'sim-fallback', 'simulated': not publicado})
    monkeypatch.setattr(crm, 'operar', operar)
    monkeypatch.setattr(crm.GooglePubSubClient, 'publish_event', publisher)
    result = asyncio.run(crm.CrmSyncService().procesar_outbox_pendientes())
    kwargs = publisher.call_args.kwargs
    assert kwargs['event_id'] == item['event_id']
    assert kwargs['correlation_id'] == item['cliente_id']
    assert kwargs['destination'] == 'crm' and kwargs['attributes']['destino'] == 'crm'
    assert result[0]['estado'] != 'sincronizado'
    assert llamadas[-1][1]['message_id'] == ('gcp-123' if publicado else None)


def test_reintentar_conserva_event_id(monkeypatch):
    item = evento()
    monkeypatch.setattr(crm, 'operar', lambda accion, **datos: {'eventos': [item]} if accion == 'reclamar' else datos)
    publisher = AsyncMock(return_value={'status': 'PUBLICADO', 'message_id': '123', 'simulated': False})
    monkeypatch.setattr(crm.GooglePubSubClient, 'publish_event', publisher)
    service = crm.CrmSyncService()
    asyncio.run(service.procesar_outbox_pendientes())
    asyncio.run(service.procesar_outbox_pendientes())
    assert publisher.call_args_list[0].kwargs['event_id'] == publisher.call_args_list[1].kwargs['event_id']


def test_sin_base_de_datos_no_inventa_exito(monkeypatch):
    monkeypatch.setattr(crm, 'get_supabase_admin_client', lambda: None)
    with pytest.raises(crm.HTTPException) as exc:
        crm.operar('estado')
    assert exc.value.status_code == 503


def test_respuesta_valida_origen_correlacion_y_contacto(monkeypatch):
    cid, request_id = str(uuid4()), str(uuid4())
    message = {'event_id': str(uuid4()), 'event_type': 'cliente.sincronizado', 'source': 'erp.crm',
               'destination': 'maxiconecta', 'correlation_id': cid,
               'payload': {'cliente_id': cid, 'request_event_id': request_id, 'crm_contact_id': 'CRM-123'}}
    calls = []
    monkeypatch.setattr(crm, 'operar', lambda accion, **datos: calls.append((accion, datos)) or {'aplicado': True})
    assert crm.procesar_respuesta(message)['aplicado']
    with pytest.raises(ValueError): crm.procesar_respuesta({**message, 'source': 'maxiconecta'})
    with pytest.raises(ValueError): crm.procesar_respuesta({**message, 'correlation_id': str(uuid4())})
    with pytest.raises(ValueError): crm.procesar_respuesta({**message, 'payload': {**message['payload'], 'crm_contact_id': None}})
    assert len(calls) == 1


def test_solo_gerencia_y_administracion_pueden_sincronizar(monkeypatch):
    client = TestClient(app)
    assert client.get('/api/v1/clientes/sync/estado').status_code == 401
    token = create_access_token({'sub': str(uuid4()), 'role': 'cliente'})
    assert client.get('/api/v1/clientes/sync/estado', headers={'Authorization': f'Bearer {token}'}).status_code == 403
    token = create_access_token({'sub': str(uuid4()), 'role': 'gerente_comercial'})
    monkeypatch.setattr(crm.crm_sync_service, 'obtener_estado_general', lambda: {'clientes': []})
    assert client.get('/api/v1/clientes/sync/estado', headers={'Authorization': f'Bearer {token}'}).json() == {'clientes': []}


def test_resincronizacion_lee_solo_persistencia(monkeypatch):
    calls = []
    monkeypatch.setattr(crm, 'operar', lambda accion, **datos: calls.append((accion, datos)) or {'estado': 'pendiente'})
    cid = str(uuid4())
    assert asyncio.run(crm.CrmSyncService().resincronizar_cliente(cid))['estado'] == 'pendiente'
    assert calls == [('encolar', {'cliente_id': cid})]
