from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.services.clientes.app.main import app
from backend.services.clientes.app import services
from backend.shared.security import create_access_token

client = TestClient(app)


@pytest.fixture
def sesion(monkeypatch):
    monkeypatch.setattr(services, 'get_supabase_admin_client', lambda: None)
    monkeypatch.setattr(services, '_PREFERENCIAS_DB', {})
    cid = str(uuid4())
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': cid, 'role': 'cliente'})}
    return cid, headers


def test_preferencias_correo_guardadas_y_recuperadas(sesion):
    cid, headers = sesion
    url = f'/api/v1/clientes/{cid}/preferencias-notificacion'
    assert client.get(url, headers=headers).json()['canal_correo'] is True
    r = client.put(url, headers=headers, json={'canal_correo': True, 'avisos_estado_pedido': True, 'avisos_promociones': True})
    assert r.status_code == 200
    data = client.get(url, headers=headers).json()
    assert data['avisos_promociones'] is True
    assert data['canal_sms'] is False and data['canal_push'] is False and data['telefono_sms'] is None


@pytest.mark.parametrize('campo', ['canal_sms', 'canal_push'])
def test_rechaza_canales_distintos_de_correo(sesion, campo):
    cid, headers = sesion
    r = client.put(f'/api/v1/clientes/{cid}/preferencias-notificacion', headers=headers, json={campo: True})
    assert r.status_code == 422


def test_estado_pedido_requiere_correo(sesion):
    cid, headers = sesion
    url = f'/api/v1/clientes/{cid}/preferencias-notificacion'
    assert client.put(url, headers=headers, json={'canal_correo': False, 'avisos_estado_pedido': True}).status_code == 422
    assert client.put(url, headers=headers, json={'canal_correo': False, 'avisos_estado_pedido': False}).status_code == 200


def test_preferencias_solo_del_cliente_autenticado(sesion):
    _, headers = sesion
    url = f'/api/v1/clientes/{uuid4()}/preferencias-notificacion'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers).status_code == 403
    assert client.put(url, headers=headers, json={}).status_code == 403


def test_fallo_base_de_datos_no_reporta_guardado_exitoso(sesion, monkeypatch):
    cid, headers = sesion
    class Query:
        def upsert(self, *args, **kwargs): return self
        def execute(self): raise RuntimeError('BD no disponible')
    monkeypatch.setattr(services, 'get_supabase_admin_client', lambda: SimpleNamespace(table=lambda _: Query()))
    r = client.put(f'/api/v1/clientes/{cid}/preferencias-notificacion', headers=headers, json={'canal_correo': True})
    assert r.status_code == 503
    assert cid not in services._PREFERENCIAS_DB


def test_ruta_heredada_tambien_exige_autorizacion_y_solo_correo(sesion):
    cid, headers = sesion
    url = f'/api/v1/clientes/{cid}/notificaciones'
    assert client.patch(url, json={'email': True}).status_code == 401
    assert client.patch(url, headers=headers, json={'email': True, 'sms': True}).status_code == 422
    assert client.patch(url, headers=headers, json={'email': True}).status_code == 200
