"""Compatibilidad del seguimiento integrado con el historial persistido."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.services.ordenes.app import routers
from backend.services.ordenes.app.main import app
from backend.shared.config import settings
from backend.shared.security import create_access_token
from backend.tests.test_historial_persistido import BaseDatos, orden


@pytest.fixture
def entorno(monkeypatch):
    cliente = str(uuid4())
    row = orden(cliente)
    db = BaseDatos([row])
    db.tablas['orden_estados_historial'] = [{
        'orden_id': row['id'], 'estado_nuevo': 'confirmada',
        'cambiado_en': row['created_at'],
    }]
    monkeypatch.setattr(routers, '_get_supabase_safe', lambda: db)
    monkeypatch.setattr(routers, '_perfil_cliente_id', lambda _db, user: user['user_id'])
    # Un registro en memoria no debe ocultar un fallo o ausencia en persistencia.
    monkeypatch.setattr(routers, '_ORDENES_DB', {row['id']: SimpleNamespace(**row)})
    token = create_access_token({'sub': cliente, 'role': 'cliente'})
    return SimpleNamespace(db=db, row=row, client=TestClient(app),
                           headers={'Authorization': f'Bearer {token}'})


def test_seguimiento_lee_bd_y_acepta_precision_postgresql(entorno):
    response = entorno.client.get(f"/api/v1/ordenes/{entorno.row['id']}/seguimiento", headers=entorno.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['estado_actual'] == 'confirmada'
    assert data['fecha_estimada'].startswith('2026-11-10T03:56:59.783470')
    assert data['historial'][0]['actual'] is True


def test_seguimiento_rechaza_otro_cliente(entorno):
    token = create_access_token({'sub': str(uuid4()), 'role': 'cliente'})
    response = entorno.client.get(f"/api/v1/ordenes/{entorno.row['id']}/seguimiento",
                                  headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403


@pytest.mark.parametrize('fallo', ['sin_conexion', 'error_bd', 'no_existe'])
def test_seguimiento_no_sustituye_bd_por_memoria(entorno, monkeypatch, fallo):
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'development')
    if fallo == 'sin_conexion':
        monkeypatch.setattr(routers, '_get_supabase_safe', lambda: None)
    elif fallo == 'error_bd':
        entorno.db.error = True
    else:
        entorno.db.tablas['ordenes'] = []
    response = entorno.client.get(f"/api/v1/ordenes/{entorno.row['id']}/seguimiento", headers=entorno.headers)
    assert response.status_code == (404 if fallo == 'no_existe' else 503)
