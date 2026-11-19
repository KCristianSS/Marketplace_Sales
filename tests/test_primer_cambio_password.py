from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from backend.services.clientes.app import routers
from backend.services.clientes.app.main import app
from backend.services.clientes.app.schemas import PerfilResponse
from backend.shared.security import decode_access_token


def test_primer_acceso_emite_token_limitado_y_bloquea_modulos():
    uid = uuid4()
    perfil = PerfilResponse(id=uid, nombre_completo='Cajero', email='cajero@example.com', role='cajero', debe_cambiar_password=True)
    session = routers._create_token_response({}, perfil)
    claims = decode_access_token(session.access_token)
    assert claims['purpose'] == 'cambio_password'
    assert claims['role'] == 'cambio_password'
    assert session.refresh_token == ''
    response = TestClient(app).get('/api/v1/clientes/auth/me', headers={'Authorization': f'Bearer {session.access_token}'})
    assert response.status_code == 403


def test_cambio_exige_token_y_password_temporal(monkeypatch):
    uid = uuid4()
    perfil = PerfilResponse(id=uid, nombre_completo='Cajero', email='cajero@example.com', role='cajero', debe_cambiar_password=True)
    token = routers._create_token_response({}, perfil).access_token
    changes = []
    class Query:
        def select(self, *args): return self
        def update(self, value): changes.append(value); return self
        def eq(self, *args): return self
        def limit(self, *args): return self
        def execute(self): return SimpleNamespace(data=[{'user_id': str(uid), 'email': 'cajero@example.com', 'activo': True, 'debe_cambiar_password': True}])
    class Auth:
        admin = SimpleNamespace(update_user_by_id=lambda user, data: changes.append((user, data)))
        def sign_in_with_password(self, data):
            if data['password'] != 'temporal': raise ValueError('incorrecta')
            return SimpleNamespace(user=SimpleNamespace(id=str(uid)))
    auth = Auth()
    monkeypatch.setattr(routers, 'get_supabase_admin_client', lambda: SimpleNamespace(table=lambda _: Query(), auth=auth))
    monkeypatch.setattr(routers, 'get_supabase_client', lambda: SimpleNamespace(auth=auth))
    client = TestClient(app)
    body = {'password_actual': 'mal', 'password_nueva': 'nueva-segura'}
    assert client.post('/api/v1/clientes/auth/primer-cambio-password', json=body).status_code == 403
    assert client.post('/api/v1/clientes/auth/primer-cambio-password', json=body, headers={'Authorization': f'Bearer {token}'}).status_code == 400
    assert not changes
    body['password_actual'] = 'temporal'
    response = client.post('/api/v1/clientes/auth/primer-cambio-password', json=body, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert changes[0][0] == str(uid)
    assert changes[1] == {'debe_cambiar_password': False}
