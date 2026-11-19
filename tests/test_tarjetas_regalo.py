"""Pruebas API y PostgreSQL reales en una BD temporal, nunca contra Supabase.

VALES_TEST_DSN=host=127.0.0.1 port=55439 dbname=postgres user=postgres
python -m pytest backend/tests/test_tarjetas_regalo.py -q
"""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.shared import vales
from backend.shared.config import settings
from backend.shared.security import create_access_token
from backend.services.ordenes.app import routers, routers_pagos
from backend.services.ordenes.app.main import app


def test_codigos_seguros_y_normalizacion(monkeypatch):
    monkeypatch.setattr(settings, "VALES_CODIGO_SECRET", "s" * 48)
    a = vales.generar_codigo(str(uuid.uuid4()), "inicial")
    b = vales.generar_codigo(str(uuid.uuid4()), "inicial")
    assert a != b
    assert vales.hash_codigo(a) == vales.hash_codigo(a.lower().replace("-", " "))
    with pytest.raises(HTTPException):
        vales.hash_codigo("MAXI-123")
    monkeypatch.setattr(settings, "VALES_CODIGO_SECRET", "")
    with pytest.raises(HTTPException) as error:
        vales.generar_codigo("id", "version")
    assert error.value.status_code == 503


@pytest.fixture(scope="module")
def postgres():
    dsn = os.getenv("VALES_TEST_DSN")
    if not dsn:
        pytest.skip("Requiere VALES_TEST_DSN apuntando a PostgreSQL local para crear una BD efímera.")
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import sql
    from psycopg2.extensions import parse_dsn
    config = parse_dsn(dsn)
    assert config.get("host") in {"localhost", "127.0.0.1"}, "Solo se permiten pruebas de dinero en PostgreSQL local."
    nombre = "vales_test_" + uuid.uuid4().hex
    maintenance = psycopg2.connect(dsn)
    maintenance.autocommit = True
    with maintenance.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(nombre)))
    config["dbname"] = nombre

    def conectar():
        conn = psycopg2.connect(**config)
        conn.autocommit = True
        return conn

    conn = conectar()
    try:
        with conn.cursor() as cur:
            for role in ("anon", "authenticated", "service_role"):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                if not cur.fetchone():
                    cur.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
            cur.execute("""
                CREATE TYPE metodo_pago_enum AS ENUM ('efectivo','tarjeta','qr','transferencia','pasarela');
                CREATE TYPE canal_venta_enum AS ENUM ('web','pos');
                CREATE TYPE tipo_despacho_enum AS ENUM ('domicilio','retiro_sucursal');
                CREATE TYPE estado_orden_enum AS ENUM ('pendiente','confirmada','cancelada');
                CREATE TABLE ordenes(id UUID PRIMARY KEY,codigo_orden TEXT,cliente_id UUID,sucursal_id UUID,
                    canal canal_venta_enum,tipo_despacho tipo_despacho_enum,direccion_entrega_id UUID,
                    subtotal NUMERIC,descuento NUMERIC,costo_envio NUMERIC,total NUMERIC,
                    estado estado_orden_enum,tracking_number TEXT,cuf_factura TEXT);
                CREATE TABLE orden_items(id UUID DEFAULT gen_random_uuid(),orden_id UUID REFERENCES ordenes(id),
                    variante_id UUID,sku TEXT,nombre_producto TEXT,cantidad INT,precio_unitario NUMERIC,total_linea NUMERIC);
                CREATE TABLE pagos(id UUID DEFAULT gen_random_uuid(),orden_id UUID REFERENCES ordenes(id),
                    transaccion_id TEXT UNIQUE,metodo metodo_pago_enum,monto NUMERIC,moneda TEXT,estado TEXT,raw_payload JSONB);
                CREATE TABLE variantes(id UUID PRIMARY KEY,producto_id UUID,created_at TIMESTAMPTZ DEFAULT now());
            """)
            migrations = Path(__file__).parents[1] / "db" / "migrations"
            cur.execute((migrations / "20261022_confirmar_orden_atomica.sql").read_text(encoding="utf-8"))
            cur.execute((migrations / "20261105_tarjetas_regalo.sql").read_text(encoding="utf-8"))
        yield conectar
    finally:
        conn.close()
        with maintenance.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nombre)))
        maintenance.close()


class LocalSupabase:
    """Adaptador de pruebas: ejecuta los RPC y consultas reales en PostgreSQL local."""
    def __init__(self, conectar):
        self.conectar = conectar

    def rpc(self, nombre, params):
        from psycopg2 import sql
        from psycopg2.extras import Json
        conn = self.conectar()
        try:
            with conn.cursor() as cur:
                argumentos = sql.SQL(",").join(sql.SQL("{} := %s").format(sql.Identifier(k)) for k in params)
                cur.execute(sql.SQL("SELECT public.{}({})").format(sql.Identifier(nombre), argumentos),
                            [Json(v) if isinstance(v, (dict, list)) else v for v in params.values()])
                data = cur.fetchone()[0]
        finally:
            conn.close()
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

    def table(self, nombre):
        return LocalQuery(self.conectar, nombre)


class LocalQuery:
    def __init__(self, conectar, tabla):
        self.conectar, self.tabla = conectar, tabla
        self.columnas, self.filtros, self.orden, self.limite, self.inicio = '*', [], None, 100, 0

    def select(self, columnas):
        self.columnas = columnas
        return self

    def eq(self, key, value):
        self.filtros.append((key, value))
        return self

    def in_(self, key, values):
        self.filtros.append((key, values))
        return self

    def or_(self, expr):
        self.disyuncion = [parte.split('.eq.', 1) for parte in expr.split(',')]
        return self

    def order(self, columna, desc=False):
        self.orden = columna, desc
        return self

    def limit(self, limite):
        self.limite = limite
        return self

    def range(self, inicio, fin):
        self.inicio, self.limite = inicio, fin - inicio + 1
        return self

    def execute(self):
        from psycopg2 import sql
        from psycopg2.extras import RealDictCursor
        if hasattr(self, 'fila'):
            from psycopg2.extras import Json
            conn = self.conectar()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                        sql.Identifier(self.tabla), sql.SQL(',').join(map(sql.Identifier, self.fila)),
                        sql.SQL(',').join(sql.Placeholder() for _ in self.fila)),
                        [Json(v) if isinstance(v, (dict, list)) else v for v in self.fila.values()])
                return SimpleNamespace(data=[])
            finally:
                conn.close()
        cols = sql.SQL('*') if self.columnas == '*' else sql.SQL(',').join(map(sql.Identifier, self.columnas.split(',')))
        query = sql.SQL('SELECT {} FROM {} WHERE TRUE').format(cols, sql.Identifier(self.tabla))
        params = []
        for key, value in self.filtros:
            query += sql.SQL(' AND {} = ANY(%s::uuid[])' if isinstance(value, list) else ' AND {} = %s').format(sql.Identifier(key))
            params.append(value)
        if hasattr(self, 'disyuncion'):
            query += sql.SQL(' AND (') + sql.SQL(' OR ').join(sql.SQL('{} = %s').format(sql.Identifier(k)) for k, _ in self.disyuncion) + sql.SQL(')')
            params.extend(v for _, v in self.disyuncion)
        if self.orden:
            query += sql.SQL(' ORDER BY {} {}').format(sql.Identifier(self.orden[0]), sql.SQL('DESC' if self.orden[1] else 'ASC'))
        query += sql.SQL(' LIMIT %s OFFSET %s')
        conn = self.conectar()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params + [self.limite, self.inicio])
                return SimpleNamespace(data=json.loads(json.dumps([dict(row) for row in cur.fetchall()], default=str)))
        finally:
            conn.close()

    def insert(self, fila):
        self.fila = fila
        return self


@pytest.fixture
def sistema(postgres, monkeypatch):
    local = LocalSupabase(postgres)
    monkeypatch.setattr(settings, "VALES_CODIGO_SECRET", "test-secret-" * 5)
    monkeypatch.setattr(vales, "get_supabase_admin_client", lambda: local)
    monkeypatch.setattr(routers, "get_supabase_admin_client", lambda: local)
    monkeypatch.setattr(routers, "_get_supabase_safe", lambda: local)
    monkeypatch.setattr(routers, "_ORDENES_DB", {})
    monkeypatch.setattr(routers_pagos, "_get_supabase_safe", lambda: None)
    monkeypatch.setattr(routers_pagos, "_transacciones_cache", {})
    async def ok(*args, **kwargs):
        return {"estado": "aprobado", "status": "OK"}
    for objeto, metodo in ((routers.pagos_client, "procesar_cobro"), (routers.pagos_client, "reversar_cobro"),
                           (routers.pagos_client, "emitir_factura"), (routers.inventarios_client, "descuento_definitivo"),
                           (routers.inventarios_client, "reingreso_por_devolucion"),
                           (routers.contabilidad_client, "registrar_asiento_venta"),
                           (routers.crm_client, "consultar_o_canjear_puntos")):
        monkeypatch.setattr(objeto, metodo, ok)
    return TestClient(app), local, postgres


def headers(id=None, role="cliente"):
    return {"Authorization": "Bearer " + create_access_token({"sub": id or str(uuid.uuid4()), "role": role})}


BASE = "/api/v1/ordenes/vales"


def emitir(sistema, monto=100):
    client, _, _ = sistema
    cliente = str(uuid.uuid4())
    res = client.post(BASE + "/admin", headers=headers(role="administrador"), json={
        "solicitud_id": str(uuid.uuid4()), "comprador_id": cliente, "monto": monto, "motivo": "Prueba autorizada"})
    assert res.status_code == 201, res.text
    return res.json(), cliente


def reservar(sistema, tarjeta, cliente, total=80, checkout=None):
    return sistema[0].post(BASE + "/reservas", headers=headers(cliente), json={
        "codigo": tarjeta["codigo"], "total": total, "checkout_id": checkout or str(uuid.uuid4())})


def test_rbac_y_motivo(sistema):
    client, _, _ = sistema
    assert client.get(BASE + "/").status_code == 401
    assert client.get(BASE + "/admin", headers=headers()).status_code == 403
    assert client.post(BASE + "/admin", headers=headers(), json={}).status_code == 403
    tarjeta, _ = emitir(sistema)
    assert client.patch(BASE + f"/admin/{tarjeta['id']}/estado", headers=headers(role="administrador"),
                        json={"estado": "bloqueada", "motivo": "   "}).status_code == 422


def test_gestion_rotacion_historial_y_privacidad(sistema):
    client, _, _ = sistema
    tarjeta, cliente = emitir(sistema)
    assert "codigo_hash" not in tarjeta and "codigo_version" not in tarjeta
    otro = headers()
    assert client.get(BASE + f"/{tarjeta['id']}/codigo", headers=otro).status_code == 404
    assert client.get(BASE + f"/{tarjeta['id']}/movimientos", headers=otro).status_code == 404
    for estado in ("bloqueada", "activa"):
        result = client.patch(BASE + f"/admin/{tarjeta['id']}/estado", headers=headers(role="administrador"),
                              json={"estado": estado, "motivo": "Gestión de prueba"})
        assert result.status_code == 200
        consulta = client.post(BASE + "/consultar", headers=headers(cliente), json={"codigo": tarjeta["codigo"]})
        assert consulta.status_code == (409 if estado == "bloqueada" else 200)
    result = client.post(BASE + f"/admin/{tarjeta['id']}/regenerar", headers=headers(role="administrador"), json={"motivo": "Código extraviado"})
    assert result.status_code == 200
    assert result.json()["codigo"] != tarjeta["codigo"]
    assert result.json()["saldo"] == tarjeta["saldo"]
    assert client.post(BASE + "/consultar", headers=headers(cliente), json={"codigo": tarjeta["codigo"]}).status_code == 404
    movimientos = client.get(BASE + f"/{tarjeta['id']}/movimientos", headers=headers(cliente)).json()
    assert {m["tipo"] for m in movimientos} >= {"emision", "estado:bloqueada", "estado:activa", "regenerar:activa"}


def test_compra_pendiente_rechazada_y_confirmada_una_sola_vez(sistema):
    client, _, _ = sistema
    cliente = str(uuid.uuid4())
    auth = headers(cliente)
    tx = client.post('/api/v1/pagos/iniciar', headers=auth, json={"monto": 150, "metodo_pago": "qr",
        "proposito": "vale", "cliente_id": cliente}).json()['transaccion_id']
    assert client.post(BASE + "/comprar", headers=auth, json={"transaccion_id": tx}).status_code == 409
    routers_pagos._transacciones_cache[tx]['estado'] = 'rechazado'
    assert client.post(BASE + "/comprar", headers=auth, json={"transaccion_id": tx}).status_code == 409
    routers_pagos._transacciones_cache[tx]['estado'] = 'aprobado'
    first = client.post(BASE + "/comprar", headers=auth, json={"transaccion_id": tx})
    second = client.post(BASE + "/comprar", headers=auth, json={"transaccion_id": tx})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(client.get(BASE + "/", headers=auth).json()) == 1
    assert client.post(BASE + "/comprar", headers=headers(), json={"transaccion_id": tx}).status_code == 409


def test_pago_vale_exige_identidad_y_no_admite_vale_para_comprar_vale(sistema):
    client, _, _ = sistema
    body = {"monto": 50, "metodo_pago": "qr", "proposito": "vale", "cliente_id": str(uuid.uuid4())}
    assert client.post('/api/v1/pagos/iniciar', json=body).status_code == 401
    assert client.post('/api/v1/pagos/iniciar', headers=headers(), json=body).status_code == 403
    body['vale_reserva_id'] = str(uuid.uuid4())
    assert client.post('/api/v1/pagos/iniciar', headers=headers(body['cliente_id']), json=body).status_code == 422


def test_reserva_reintento_liberacion_y_bloqueo(sistema):
    client, _, _ = sistema
    tarjeta, cliente = emitir(sistema)
    checkout = str(uuid.uuid4())
    a = reservar(sistema, tarjeta, cliente, checkout=checkout).json()
    b = reservar(sistema, tarjeta, cliente, checkout=checkout).json()
    assert a['id'] == b['id']
    assert client.patch(BASE + f"/admin/{tarjeta['id']}/estado", headers=headers(role="administrador"),
                        json={"estado": "bloqueada", "motivo": "Esperar checkout"}).status_code == 409
    assert client.delete(BASE + f"/reservas/{a['id']}", headers=headers()).status_code == 404
    for _ in range(2):
        assert client.delete(BASE + f"/reservas/{a['id']}", headers=headers(cliente)).status_code == 200
    saldo = client.post(BASE + '/consultar', headers=headers(cliente), json={'codigo': tarjeta['codigo']}).json()['saldo']
    assert float(saldo) == 100


def test_concurrencia_no_gasta_dos_veces_el_saldo(sistema):
    _, local, _ = sistema
    tarjeta, _ = emitir(sistema)
    def intento(_):
        return local.rpc('operar_vale', {'p_accion': 'reservar', 'p_actor': str(uuid.uuid4()), 'p_datos': {
            'codigo_hash': vales.hash_codigo(tarjeta['codigo']), 'checkout_id': str(uuid.uuid4()),
            'total': '80.00', 'reserva_id': str(uuid.uuid4())}}).execute().data
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(intento, range(8)))
    assert sum(float(r.get('monto', 0)) for r in resultados) == 100
    assert sum('error' not in r for r in resultados) == 2


def test_expiracion_reintegra_solo_una_vez(sistema):
    _, local, conectar = sistema
    tarjeta, cliente = emitir(sistema)
    reserva = reservar(sistema, tarjeta, cliente).json()
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute("UPDATE reservas_vale SET expira_en=now()-interval '1 second' WHERE id=%s", (reserva['id'],))
    conn.close()
    for _ in range(2):
        assert float(vales.operar('consultar', cliente, codigo_hash=vales.hash_codigo(tarjeta['codigo']))['saldo']) == 100
    assert vales.operar('reserva', cliente, reserva_id=reserva['id'])['estado'] == 'liberada'


def test_vale_vencido_y_anulado(sistema):
    client, _, conectar = sistema
    tarjeta, cliente = emitir(sistema)
    result = client.patch(BASE + f"/admin/{tarjeta['id']}/estado", headers=headers(role="administrador"),
                          json={"estado": "anulada", "motivo": "Anulación definitiva"})
    assert result.status_code == 200
    assert reservar(sistema, tarjeta, cliente).status_code == 409
    assert client.patch(BASE + f"/admin/{tarjeta['id']}/estado", headers=headers(role="administrador"),
                        json={"estado": "activa", "motivo": "Intentar reactivar"}).status_code == 409
    tarjeta, cliente = emitir(sistema)
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute("UPDATE tarjetas_regalo SET vence_en=now()-interval '1 second' WHERE id=%s", (tarjeta['id'],))
    conn.close()
    assert reservar(sistema, tarjeta, cliente).status_code == 409


def datos_orden(sistema, tarjeta, cliente, total=80):
    _, _, conectar = sistema
    checkout = str(uuid.uuid4())
    reserva = reservar(sistema, tarjeta, cliente, total, checkout).json()
    variante = str(uuid.uuid4())
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO variantes(id,producto_id) VALUES(%s,%s)', (variante, str(uuid.uuid4())))
    conn.close()
    body = {'cliente_id': cliente, 'tipo_despacho': 'retiro_sucursal', 'subtotal': total,
            'total': total, 'vale_reserva_id': reserva['id'], 'reserva_id': checkout,
            'items': [{'variante_id': variante, 'sku': 'VALE-TEST', 'nombre_producto': 'Artículo', 'cantidad': 1, 'precio_unitario': total}]}
    return body, reserva


@pytest.mark.parametrize('saldo,total', [(100, 80), (100, 100), (50, 80)])
def test_checkout_total_parcial_e_idempotencia(sistema, monkeypatch, saldo, total):
    client, _, _ = sistema
    tarjeta, cliente = emitir(sistema, saldo)
    body, reserva = datos_orden(sistema, tarjeta, cliente, total)
    async def stock(_):
        return {'status': 'ACTIVA'}
    async def confirmar(_):
        return True
    monkeypatch.setattr(routers, 'consultar_reserva', stock)
    monkeypatch.setattr(routers, 'confirmar_reserva_stock', confirmar)
    monkeypatch.setattr(routers_pagos, 'consultar_reserva', stock)
    if saldo < total:
        pago = client.post('/api/v1/pagos/iniciar', headers=headers(cliente), json={
            'monto': total - saldo, 'metodo_pago': 'tarjeta', 'cliente_id': cliente,
            'tipo_despacho': 'retiro_sucursal', 'reserva_id': body['reserva_id'], 'vale_reserva_id': reserva['id']})
        assert pago.status_code == 201, pago.text
        body['transaccion_id'] = pago.json()['transaccion_id']
    result = client.post('/api/v1/ordenes/', headers=headers(cliente), json=body)
    assert result.status_code == 201, result.text
    assert result.json()['pagos'][0]['metodo'] == 'vale'
    assert len(result.json()['pagos']) == (2 if saldo < total else 1)
    repeat = client.post('/api/v1/ordenes/', headers=headers(cliente), json=body)
    assert repeat.json()['id'] == result.json()['id']
    if saldo < total:
        routers_pagos._transacciones_cache.clear()
        monkeypatch.setattr(routers_pagos, '_get_supabase_safe', lambda: sistema[1])
        restaurado = client.post('/api/v1/ordenes/', headers=headers(cliente), json=body)
        assert restaurado.status_code == 201, restaurado.text
        assert restaurado.json()['id'] == result.json()['id']
    assert vales.operar('reserva', cliente, reserva_id=reserva['id'])['estado'] == 'consumida'


def test_commit_fallido_revierte_consumo_y_orden(sistema):
    _, local, _ = sistema
    tarjeta, cliente = emitir(sistema)
    body, reserva = datos_orden(sistema, tarjeta, cliente)
    orden = {**body, 'id': str(uuid.uuid4()), 'estado': 'confirmada', 'codigo_orden': 'TEST', 'canal': 'web'}
    pago = {'metodo': 'vale', 'monto': reserva['monto'], 'transaccion_id': 'VALE-' + reserva['id']}
    # Fuerza fallo dentro del RPC de persistencia después de consumir el vale.
    with pytest.raises(Exception):
        local.rpc('confirmar_orden_con_vale', {'p_orden': orden, 'p_items': [{'variante_id': 'uuid-invalido'}], 'p_pagos': [pago]})
    assert vales.operar('reserva', cliente, reserva_id=reserva['id'])['estado'] == 'reservada'
    assert not local.table('ordenes').select('*').eq('id', orden['id']).execute().data


def test_reintegro_idempotente_y_compensacion(sistema):
    _, _, _ = sistema
    tarjeta, cliente = emitir(sistema)
    reserva = reservar(sistema, tarjeta, cliente).json()
    vales.operar('consumir', cliente, reserva_id=reserva['id'], orden_id=str(uuid.uuid4()))
    for _ in range(2):
        assert vales.reintegrar('VALE-' + reserva['id'])['estado'] == 'reintegrada'
    assert float(vales.operar('consultar', cliente, codigo_hash=vales.hash_codigo(tarjeta['codigo']))['saldo']) == 100
    vales.operar('restaurar_consumo', 'sistema', reserva_id=reserva['id'])
    assert float(vales.operar('consultar', cliente, codigo_hash=vales.hash_codigo(tarjeta['codigo']))['saldo']) == 20


def test_webhook_produccion_exige_firma_y_no_permite_simulacion(sistema, monkeypatch):
    import hashlib
    import hmac
    client, _, _ = sistema
    cliente = str(uuid.uuid4())
    inicio = client.post('/api/v1/pagos/iniciar', headers=headers(cliente), json={
        'proposito': 'vale', 'metodo_pago': 'qr', 'monto': 100, 'cliente_id': cliente})
    tx = inicio.json()['transaccion_id']
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'production')
    monkeypatch.setattr(settings, 'PAGOS_WEBHOOK_SECRET', 'test-webhook-secret')
    body = {'transaccion_id': tx, 'evento': 'pago.aprobado', 'monto': 100}
    assert client.post('/api/v1/pagos/webhook', json=body).status_code == 401
    assert client.post('/api/v1/pagos/simular-webhook', json={'transaccion_id': tx, 'resultado': 'aprobado'}).status_code == 403
    body['firma_hmac'] = hmac.new(b'test-webhook-secret', f'{tx}|pago.aprobado|100.00'.encode(), hashlib.sha256).hexdigest()
    assert client.post('/api/v1/pagos/webhook', json=body).status_code == 200


def test_no_emite_por_efectivo_ni_por_tarjeta_pendiente(sistema, monkeypatch):
    client, _, _ = sistema
    cliente = str(uuid.uuid4())
    body = {'proposito': 'vale', 'metodo_pago': 'efectivo', 'monto': 100, 'cliente_id': cliente}
    assert client.post('/api/v1/pagos/iniciar', headers=headers(cliente), json=body).status_code == 422
    async def pendiente(*args, **kwargs):
        return {'estado': 'pendiente'}
    monkeypatch.setattr(routers.pagos_client, 'procesar_cobro', pendiente)
    body['metodo_pago'] = 'tarjeta'
    pago = client.post('/api/v1/pagos/iniciar', headers=headers(cliente), json=body)
    assert pago.status_code == 201
    assert pago.json()['estado'] == 'pendiente'
    assert client.post(BASE + '/comprar', headers=headers(cliente), json={'transaccion_id': pago.json()['transaccion_id']}).status_code == 409
