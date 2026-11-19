"""Regresiones del historial persistido: fechas PostgreSQL, paginación y fallos de DB."""
import json
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.services.ordenes.app import routers
from backend.services.ordenes.app.main import app
from backend.shared.security import create_access_token


class Consulta:
    def __init__(self, db, tabla):
        self.db, self.tabla = db, tabla
        self.filtros, self.orden, self.rango = [], [], None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, campo, valor):
        self.filtros.append(lambda row: str(row.get(campo)) == str(valor))
        return self

    def or_(self, expresion):
        textos = [(campo, json.loads(patron).strip('%').casefold()) for campo, patron in
                  re.findall(r'(\w+)\.ilike\.("(?:\\.|[^"\\])*")', expresion)]
        ids = re.search(r'id\.in\.\(([^)]+)\)', expresion)
        ids = set(ids.group(1).split(',')) if ids else set()
        self.filtros.append(lambda row: str(row.get('id')) in ids or any(
            texto in str(row.get(campo) or '').casefold() for campo, texto in textos))
        return self

    def order(self, campo, desc=False):
        self.orden.append((campo, desc))
        return self

    def range(self, inicio, fin):
        self.rango = (inicio, fin)
        return self

    def limit(self, cantidad):
        return self.range(0, cantidad - 1)

    def execute(self):
        if self.db.error:
            raise RuntimeError('Base de datos no disponible')
        rows = [r for r in self.db.tablas[self.tabla] if all(f(r) for f in self.filtros)]
        for campo, desc in reversed(self.orden):
            rows.sort(key=lambda r: r[campo], reverse=desc)
        total = len(rows)
        if self.rango:
            inicio, fin = self.rango
            rows = rows[inicio:fin + 1]
        return SimpleNamespace(data=rows, count=total)


class BaseDatos:
    def __init__(self, rows):
        self.tablas = {'ordenes': rows, 'orden_items': [], 'pagos': []}
        for row in rows:
            self.tablas['orden_items'].extend(row['orden_items'])
        self.error = False

    def table(self, tabla):
        return Consulta(self, tabla)


def orden(cliente_id, dia=9, fraccion='78347', producto='Producto habitual'):
    oid = str(uuid4())
    return {
        'id': oid, 'codigo_orden': f'ORD-{dia:02d}-{oid[:8]}', 'cliente_id': cliente_id,
        'canal': 'web', 'tipo_despacho': 'retiro_sucursal', 'estado': 'confirmada',
        'subtotal': 100, 'total': 100, 'created_at': f'2026-11-{dia:02d}T03:56:59.{fraccion}+00:00',
        'orden_items': [{
            'id': str(uuid4()), 'orden_id': oid, 'variante_id': str(uuid4()),
            'sku': 'SKU-HABITUAL', 'nombre_producto': producto,
            'cantidad': 1, 'precio_unitario': 100, 'total_linea': 100,
        }], 'pagos': [],
    }


@pytest.fixture
def entorno(monkeypatch):
    cliente_id = str(uuid4())
    db = BaseDatos([orden(cliente_id, dia) for dia in range(1, 14)] + [orden(str(uuid4()))])
    monkeypatch.setattr(routers, '_get_supabase_safe', lambda: db)
    monkeypatch.setattr(routers, '_ORDENES_DB', {})
    token = create_access_token({'sub': cliente_id, 'role': 'cliente'})
    return SimpleNamespace(db=db, cliente_id=cliente_id, client=TestClient(app),
                           headers={'Authorization': f'Bearer {token}'})


@pytest.mark.parametrize('fraccion', ['1', '12', '123', '1234', '78347', '123456'])
def test_historial_y_detalle_aceptan_precision_postgresql(entorno, fraccion):
    row = orden(entorno.cliente_id, fraccion=fraccion)
    entorno.db.tablas['ordenes'] = [row]
    response = entorno.client.get('/api/v1/ordenes/', headers=entorno.headers)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 1
    assert response.json()['items'][0]['id'] == row['id']
    detail = entorno.client.get(f"/api/v1/ordenes/{row['id']}", headers=entorno.headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()['created_at'] == response.json()['items'][0]['created_at']


@pytest.mark.parametrize(('monto', 'esperado'), [(0, 'sin_reembolso'), (30, 'parcial'), (100, 'total')])
def test_historial_muestra_reembolso_segun_importe_registrado(entorno, monto, esperado):
    row = orden(entorno.cliente_id)
    row['pagos'] = [{'metodo': 'tarjeta', 'monto': 100, 'estado': 'aprobado',
                     'transaccion_id': 'TX-1', 'monto_reembolsado': monto}]
    entorno.db.tablas['ordenes'] = [row]
    result = entorno.client.get('/api/v1/ordenes/', headers=entorno.headers)
    assert result.status_code == 200
    assert result.json()['items'][0]['estado_reembolso'] == esperado


def test_pagina_todos_los_pedidos_persistidos_del_cliente_sin_memoria(entorno):
    ids = []
    for pagina, cantidad in [(1, 8), (2, 5)]:
        response = entorno.client.get(f'/api/v1/ordenes/?page={pagina}&limit=8', headers=entorno.headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['total'] == 13
        assert data['total_paginas'] == 2
        assert len(data['items']) == cantidad
        assert all(row['cliente_id'] == entorno.cliente_id for row in data['items'])
        ids.extend(row['id'] for row in data['items'])
    assert len(set(ids)) == 13


@pytest.mark.parametrize('campo', ['codigo_orden', 'producto', 'sku', 'tracking_number', 'cuf_factura'])
def test_busqueda_encuentra_pedidos_fuera_de_la_primera_pagina(entorno, campo):
    row = entorno.db.tablas['ordenes'][0]  # El más antiguo, fuera de la página inicial.
    if campo == 'producto':
        row['orden_items'][0]['nombre_producto'] = 'Especial, (azul)'
    elif campo == 'sku':
        row['orden_items'][0]['sku'] = 'Especial, (azul)'
    else:
        row[campo] = 'Especial, (azul)'
    response = entorno.client.get('/api/v1/ordenes/', params={'busqueda': 'Especial, (azul)', 'limit': 8}, headers=entorno.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['total'] == 1
    assert [r['id'] for r in data['items']] == [row['id']]


def test_busqueda_conserva_total_y_paginacion_y_no_filtra_clientes_ajenos(entorno):
    response = entorno.client.get('/api/v1/ordenes/?busqueda=habitual&page=2&limit=8', headers=entorno.headers)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 13
    assert len(response.json()['items']) == 5
    assert response.json()['total_paginas'] == 2


def test_error_de_base_no_devuelve_historial_local_incompleto(entorno, monkeypatch):
    local = routers.OrdenResponse(**{**entorno.db.tablas['ordenes'][0], 'items': []})
    monkeypatch.setattr(routers, '_ORDENES_DB', {str(local.id): local})
    entorno.db.error = True
    response = entorno.client.get('/api/v1/ordenes/', headers=entorno.headers)
    assert response.status_code == 503
    assert 'historial completo' in response.json()['detail']


def test_sin_base_en_desarrollo_no_se_presenta_memoria_como_historial(entorno, monkeypatch):
    monkeypatch.setattr(routers, '_get_supabase_safe', lambda: None)
    monkeypatch.setattr(routers.settings, 'ENVIRONMENT', 'development')
    response = entorno.client.get('/api/v1/ordenes/', headers=entorno.headers)
    assert response.status_code == 503
