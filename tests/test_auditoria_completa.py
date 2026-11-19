import asyncio
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.shared import audit_spool, routers_auditoria
from backend.shared.audit import registrar_auditoria
from backend.shared.audit_context import AuditContextMiddleware, audit_context, signed_gateway_headers
from backend.shared.config import settings
from backend.shared.security import create_access_token
from backend.tests.test_historial_persistido import BaseDatos, Consulta
from backend.tests.test_tarjetas_regalo import postgres, LocalSupabase


def headers(role='administrador', **extra):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': str(uuid4()), 'role': role, **extra})}


@pytest.fixture
def spool(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'AUDIT_SPOOL_PATH', str(tmp_path / 'audit.sqlite3'))
    return settings.AUDIT_SPOOL_PATH


def test_cola_durable_recupera_error_sin_repetir_la_operacion(monkeypatch, spool):
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'production')
    class Destination:
        fail = True
        rows = {}
        def table(self, _): return self
        def insert(self, row): self.row = row; return self
        def execute(self):
            if self.fail: raise ConnectionError('Supabase no disponible')
            self.rows[self.row['id']] = self.row
    dest = Destination()
    row = registrar_auditoria(dest, current_user={'sub': str(uuid4()), 'role': 'administrador'},
        accion='PRODUCTO_ACTUALIZADO', entidad='productos', antes={'precio': 10}, despues={'precio': 12, 'token': 'secreto'})
    assert row['persistencia'] == 'pendiente'
    assert audit_spool.summary()['pendientes'] == 1
    # Simula un nuevo proceso que abre el mismo archivo después de un reinicio.
    with sqlite3.connect(spool) as conn:
        saved = conn.execute('SELECT event FROM audit_pending').fetchone()[0]
        assert json.loads(saved)['payload_after']['token'] == '[REDACTED]'
        conn.execute('UPDATE audit_pending SET available_at=0')
    dest.fail = False
    assert audit_spool.flush_pending(dest) == 1
    assert audit_spool.flush_pending(dest) == 0
    assert list(dest.rows) == [row['id']]
    assert audit_spool.summary()['pendientes'] == 0


def test_reintento_con_respuesta_perdida_usa_id_estable(monkeypatch, spool):
    event = {'id': str(uuid4()), 'action': 'PRUEBA', 'entity': 'ordenes'}
    audit_spool.enqueue(event)
    class Duplicate(Exception): code = '23505'
    class Destination:
        def table(self, _): return self
        def insert(self, row): assert row['id'] == event['id']; return self
        def execute(self): raise Duplicate()
    assert audit_spool.deliver(Destination()) is True
    assert audit_spool.summary()['pendientes'] == 0


def context_app(gateway=False, client_ip=None):
    app = FastAPI()
    app.add_middleware(AuditContextMiddleware, gateway=gateway)
    @app.get('/context')
    async def context():
        first = dict(audit_context.get())
        await asyncio.sleep(0.01)
        assert audit_context.get() == first
        return {**first, 'forward': signed_gateway_headers()}
    if client_ip:
        async def with_peer(scope, receive, send):
            scope = {**scope, 'client': (client_ip, 1234)}
            await app(scope, receive, send)
        return with_peer
    return app


def test_origen_firmado_y_cabeceras_falsificadas():
    gateway = TestClient(context_app(gateway=True, client_ip='192.0.2.12'))
    service = TestClient(context_app(client_ip='172.18.0.7'))
    auth = headers()
    original = gateway.get('/context', headers={**auth, 'User-Agent': 'Mi navegador'}).json()
    forwarded = service.get('/context', headers={**auth, **original['forward']}).json()
    assert forwarded['ip_address'] == '192.0.2.12'
    assert forwarded['user_agent'] == 'Mi navegador'
    assert forwarded['request_id'] == original['request_id']
    fake = dict(original['forward'])
    fake['x-maxiconecta-audit'] = fake['x-maxiconecta-audit'].replace('192.0.2.12', '192.0.2.99')
    denied = service.get('/context', headers={**auth, **fake}).json()
    assert denied['ip_address'] == '172.18.0.7'
    assert denied['request_id'] != original['request_id']


def test_usuarios_concurrentes_no_comparten_contexto():
    app = context_app()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            tokens = [headers('cliente') for _ in range(8)]
            rows = await asyncio.gather(*[client.get('/context', headers=token) for token in tokens])
            assert len({row.json()['actor_id'] for row in rows}) == 8
            assert len({row.json()['request_id'] for row in rows}) == 8
            assert audit_context.get() == {}
    asyncio.run(run())


class Query(Consulta):
    def gte(self, key, value): self.filtros.append(lambda row: row[key] >= value); return self
    def lte(self, key, value): self.filtros.append(lambda row: row[key] <= value); return self
    def or_(self, expression):
        actor = expression.split(',')[0].split('.eq.')[1]
        self.filtros.append(lambda row: row.get('user_id') == actor or row.get('actor_id') == actor)
        return self


@pytest.fixture
def api(monkeypatch, spool):
    db = BaseDatos([])
    db.table = lambda name: Query(db, name)
    actor = str(uuid4())
    db.tablas['audit_logs'] = [{
        'id': str(uuid4()), 'user_id': actor, 'action': 'PRODUCTO_ACTUALIZADO',
        'entity': 'productos', 'created_at': f'2026-11-{day:02d}T10:00:00+00:00',
        'payload_before': {'precio': 10}, 'payload_after': {'precio': 12, 'password': 'secreto'},
    } for day in range(1, 27)]
    monkeypatch.setattr(routers_auditoria, 'get_supabase_admin_client', lambda: db)
    app = FastAPI(); app.include_router(routers_auditoria.router)
    return SimpleNamespace(client=TestClient(app), db=db, actor=actor)


@pytest.mark.parametrize('role', ['cliente', 'cajero', 'gerente_comercial', 'authenticated'])
def test_auditoria_solo_admin_incluso_si_user_metadata_dice_admin(api, role):
    response = api.client.get('/api/v1/admin/auditoria', headers=headers(role, user_metadata={'role': 'administrador'}))
    assert response.status_code == 403


def test_auditoria_exige_token_y_no_expone_escrituras(api):
    assert api.client.get('/api/v1/admin/auditoria').status_code == 401
    assert api.client.delete('/api/v1/admin/auditoria', headers=headers()).status_code == 405


def test_auditoria_filtra_pagina_y_redacta_historicos(api):
    auth = headers('authenticated', app_metadata={'role': 'administrador'})
    response = api.client.get('/api/v1/admin/auditoria?page=2', headers=auth)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['total'] == 26 and len(data['items']) == 6 and data['total_paginas'] == 2
    assert data['items'][0]['payload_after']['password'] == '[REDACTED]'
    assert data['items'][0]['actor_id'] == api.actor
    assert response.headers['Cache-Control'] == 'no-store'
    response = api.client.get('/api/v1/admin/auditoria', params={
        'accion': 'PRODUCTO_ACTUALIZADO', 'entidad': 'productos', 'actor': api.actor,
        'desde': '2026-11-20T00:00:00Z', 'hasta': '2026-11-22T23:59:00Z',
    }, headers=auth)
    assert response.status_code == 200 and response.json()['total'] == 3


def test_auditoria_no_oculta_caidas_de_base_de_datos(api):
    api.db.error = True
    assert api.client.get('/api/v1/admin/auditoria', headers=headers()).status_code == 503
    assert api.client.get('/api/v1/admin/auditoria?desde=2026-11-12T00:00:00Z&hasta=2026-11-01T00:00:00Z', headers=headers()).status_code == 422


def test_migracion_y_persistencia_real_de_metadatos(postgres, monkeypatch, spool):
    from pathlib import Path
    conn = postgres()
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE audit_logs(id UUID PRIMARY KEY,user_id UUID,user_role VARCHAR(50),
            ip_address VARCHAR(45),action VARCHAR(100),entity VARCHAR(100),entity_id UUID,
            payload_before JSONB,payload_after JSONB,created_at TIMESTAMPTZ DEFAULT now())''')
        cur.execute((Path(__file__).parents[1] / 'db/migrations/20261110040056_auditoria_estructurada.sql').read_text(encoding='utf-8'))
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'production')
    actor, request_id = str(uuid4()), str(uuid4())
    reset = audit_context.set({'actor_id': actor, 'role': 'administrador', 'ip_address': '192.0.2.20',
        'request_id': request_id, 'request_method': 'PATCH', 'request_path': '/api/v1/catalogo/productos/1', 'user_agent': 'Prueba'})
    try:
        event = registrar_auditoria(LocalSupabase(postgres), current_user={}, accion='PRODUCTO_ACTUALIZADO',
            entidad='productos', antes={'precio': 100}, despues={'precio': 120})
    finally:
        audit_context.reset(reset)
    assert event['persistencia'] == 'supabase'
    assert audit_spool.summary()['pendientes'] == 0
    with conn.cursor() as cur:
        cur.execute('SELECT actor_id,request_id::text,ip_address,payload_before,payload_after FROM audit_logs WHERE id=%s', (event['id'],))
        row = cur.fetchone()
        assert row == (actor, request_id, '192.0.2.20', {'precio': 100}, {'precio': 120})
    conn.close()


def test_endpoint_auditado_conserva_snapshots_y_resultado(monkeypatch):
    from backend.shared import audit_operations
    state = {'id': str(uuid4()), 'precio': 100}
    events = []
    class Client:
        def table(self, name):
            class Query:
                def select(self, *_): return self
                def eq(self, *_): return self
                def limit(self, *_): return self
                def insert(self, row): events.append(row); return self
                def execute(self): return SimpleNamespace(data=[dict(state)])
            return Query()
    monkeypatch.setattr(audit_operations, 'get_supabase_admin_client', lambda: Client())
    @audit_operations.audit_operation('PRODUCTO_ACTUALIZADO', 'productos', id_arg='id')
    async def update(id, current_user):
        state['precio'] = 120
        return dict(state)
    result = asyncio.run(update(id=state['id'], current_user={'sub': str(uuid4()), 'role': 'administrador'}))
    assert result['precio'] == 120
    assert len(events) == 1
    assert events[0]['payload_before']['precio'] == 100
    assert events[0]['payload_after']['precio'] == 120
