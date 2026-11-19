from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.services.clientes.app import services_usuarios as svc
from backend.services.clientes.app.schemas import UsuarioInternoCreate


def test_alta_crea_cuenta_y_no_persiste_password(monkeypatch):
    rows, auth_requests = [], []
    auth_id = str(uuid4())

    class Query:
        def __init__(self): self.filters = []
        def select(self, *_a): return self
        def eq(self, k, v): self.filters.append((k, v)); return self
        def limit(self, *_a): return self
        def insert(self, row): rows.append(row); return self
        def execute(self):
            return SimpleNamespace(data=[r for r in rows if all(str(r.get(k)) == str(v) for k, v in self.filters)])

    def create_user(request):
        auth_requests.append(request)
        return SimpleNamespace(user=SimpleNamespace(id=auth_id))

    client = SimpleNamespace(table=lambda _name: Query(), auth=SimpleNamespace(admin=SimpleNamespace(create_user=create_user)))
    monkeypatch.setattr(svc, 'get_supabase_admin_client', lambda: client)
    monkeypatch.setattr(svc.UsuariosInternosService, 'registrar_audit_log', lambda *_a, **_kw: None)
    result = svc.UsuariosInternosService.crear(UsuarioInternoCreate(
        nombre_completo='Cajero nuevo', email='staff@example.com', rol='cajero', sucursal_id='SUC-01'))
    assert str(result.user_id) == auth_id
    assert result.password_temporal == auth_requests[0]['password']
    assert auth_requests[0]['app_metadata']['role'] == 'cajero'
    assert 'password_temporal' not in rows[0]
    assert svc.UsuariosInternosService.obtener_por_id(result.id).password_temporal is None


def test_listado_vacio_no_inventa_usuarios_y_error_no_usa_memoria(monkeypatch):
    class Query:
        fail = False
        def select(self, *_a): return self
        def order(self, *_a, **_kw): return self
        def execute(self):
            if self.fail: raise RuntimeError('offline')
            return SimpleNamespace(data=[])
    query = Query()
    monkeypatch.setattr(svc, 'get_supabase_admin_client', lambda: SimpleNamespace(table=lambda _: query))
    assert svc.UsuariosInternosService.listar() == []
    query.fail = True
    with pytest.raises(HTTPException) as error:
        svc.UsuariosInternosService.listar()
    assert error.value.status_code == 503
