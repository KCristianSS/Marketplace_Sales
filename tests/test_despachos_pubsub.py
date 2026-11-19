"""Flujo real de outbox PostgreSQL + frontera Pub/Sub simulada, sin enviar a GCP.

Usa la BD efímera y el adaptador SQL de pruebas de tarjetas de regalo.
Configurar VALES_TEST_DSN hacia PostgreSQL local para las pruebas transaccionales.
"""
import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.tests.test_tarjetas_regalo import postgres, LocalSupabase, headers
from backend.shared import despachos
from backend.shared.pubsub_client import GooglePubSubClient
from backend.scripts.simular_entregas import SimuladorEntregas
from backend.services.ordenes.app import routers_despachos
from backend.services.ordenes.app.main import app


@pytest.fixture(scope='module')
def db(postgres):
    conn = postgres()
    with conn.cursor() as cur:
        for estado in ('en_preparacion','despachada','entregada'):
            cur.execute('ALTER TYPE estado_orden_enum ADD VALUE IF NOT EXISTS %s', (estado,))
        migrations = Path(__file__).parents[1] / 'db' / 'migrations'
        cur.execute((migrations / '20261102_cotizacion_flete.sql').read_text(encoding='utf-8'))
        cur.execute(next(migrations.glob('*_despachos_pubsub.sql')).read_text(encoding='utf-8'))
    conn.close()
    return LocalSupabase(postgres), postgres


@pytest.fixture
def sistema(db, monkeypatch):
    local, conectar = db
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('TRUNCATE despachos_inbox,despachos_outbox,despachos,orden_items,pagos,ordenes CASCADE')
    conn.close()
    monkeypatch.setattr(despachos, 'get_supabase_admin_client', lambda: local)
    monkeypatch.setattr(routers_despachos, 'get_supabase_admin_client', lambda: local)
    enviados = []
    async def publicar(self, tipo, payload, **kwargs):
        enviados.append({'event_id': kwargs['event_id'], 'event_type': tipo,
            'source': 'maxiconecta.marketplace.grupo-e', 'destination': 'entregas',
            'correlation_id': kwargs['correlation_id'], 'payload': payload})
        return {'status': 'PUBLICADO', 'message_id': 'gcp-test-' + kwargs['event_id'], 'simulated': False}
    monkeypatch.setattr(GooglePubSubClient, 'publish_event', publicar)
    return local, conectar, enviados


def crear(sistema, despacho='domicilio', estado='confirmada'):
    local, conectar, _ = sistema
    oid, cliente = str(uuid.uuid4()), str(uuid.uuid4())
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO ordenes(id,codigo_orden,cliente_id,estado,tipo_despacho,entrega) VALUES(%s,%s,%s,%s,%s,%s)',
            (oid, 'ORD-TEST', cliente, estado, despacho, json.dumps({'direccion': 'Av. Arce 123', 'ciudad': 'La Paz'})))
        cur.execute('INSERT INTO orden_items(orden_id,sku,nombre_producto,cantidad) VALUES(%s,%s,%s,1)', (oid,'SKU-1','Artículo'))
    conn.close()
    return oid, cliente


def datos(sistema, oid):
    return sistema[0].rpc('operar_despacho', {'p_accion': 'obtener', 'p_datos': {'orden_id': oid}}).execute().data


def test_trigger_solo_confirmadas_domicilio_una_vez(sistema):
    oid, _ = crear(sistema)
    assert len(datos(sistema, oid)['eventos']) == 1
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute("UPDATE ordenes SET estado='confirmada' WHERE id=%s", (oid,))
    conn.close()
    assert len(datos(sistema, oid)['eventos']) == 1
    retiro, _ = crear(sistema, despacho='retiro_sucursal')
    pendiente, _ = crear(sistema, estado='pendiente')
    assert datos(sistema, retiro)['error']
    assert datos(sistema, pendiente)['status'] == 404


def test_rollback_orden_no_deja_solicitud_ni_publica(sistema):
    conn = sistema[1]()
    conn.autocommit = False
    oid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("INSERT INTO ordenes(id,codigo_orden,cliente_id,estado,tipo_despacho) VALUES(%s,'ROLLBACK',%s,'confirmada','domicilio')", (oid,str(uuid.uuid4())))
        cur.execute('SELECT count(*) FROM despachos WHERE orden_id=%s', (oid,))
        assert cur.fetchone()[0] == 1
        # Otro proceso no puede ver ni publicar una orden sin commit.
        assert asyncio.run(despachos.publicar_pendientes()) == 0
    conn.rollback()
    conn.close()
    assert not sistema[2]
    assert datos(sistema, oid)['status'] == 404


def test_publicacion_automatica_despues_del_commit_y_respuesta(sistema, tmp_path):
    oid, _ = crear(sistema)
    assert not datos(sistema, oid)['guia']
    assert asyncio.run(despachos.publicar_pendientes()) == 1
    assert len(sistema[2]) == 1
    enviado = sistema[2][0]
    assert enviado['event_type'] == 'despacho.solicitado'
    assert enviado['payload']['orden_id'] == oid
    assert enviado['payload']['entrega']['direccion'] == 'Av. Arce 123'
    assert datos(sistema, oid)['eventos'][0]['estado'] == 'publicado'
    assert not datos(sistema, oid)['guia']  # Publicar no inventa la guía.
    respuesta = SimuladorEntregas(str(tmp_path/'erp.sqlite3')).responder(enviado)
    assert despachos.procesar_respuesta(respuesta)['aplicado']
    assert datos(sistema, oid)['guia'].startswith('TRK-SIM-')
    assert datos(sistema, oid)['transportista'] == 'Transportista simulado'


def test_fallback_reintenta_mismo_evento_sin_fingir_envio(sistema, monkeypatch):
    oid, _ = crear(sistema)
    enviados = []
    async def fallback(self, tipo, payload, **kwargs):
        enviados.append(kwargs['event_id'])
        return {'status':'FALLBACK_OFFLINE','message_id':'sim-123','simulated':True}
    monkeypatch.setattr(GooglePubSubClient, 'publish_event', fallback)
    asyncio.run(despachos.publicar_pendientes())
    evento = datos(sistema, oid)['eventos'][0]
    assert evento['estado'] == 'pendiente' and not evento['message_id'] and evento['ultimo_error']
    despachos.operar('reintentar', orden_id=oid, actor='admin')
    asyncio.run(despachos.publicar_pendientes())
    assert enviados == [evento['id'], evento['id']]
    assert datos(sistema, oid)['eventos'][0]['intentos'] == 2


def test_workers_concurrentes_no_reclaman_el_mismo_evento(sistema):
    for _ in range(16):
        crear(sistema)
    def reclamar(_):
        return sistema[0].rpc('operar_despacho', {'p_accion':'reclamar','p_datos':{}}).execute().data['eventos']
    with ThreadPoolExecutor(max_workers=4) as pool:
        lotes = list(pool.map(reclamar, range(4)))
    ids = [e['id'] for lote in lotes for e in lote]
    assert len(ids) == len(set(ids)) == 16


def test_recupera_lease_y_descarta_ack_del_worker_anterior(sistema):
    oid, _ = crear(sistema)
    a = despachos.operar('reclamar')['eventos'][0]
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute("UPDATE despachos_outbox SET lease_hasta=now()-interval '1 second' WHERE id=%s", (a['id'],))
    conn.close()
    b = despachos.operar('reclamar')['eventos'][0]
    assert a['id'] == b['id'] and a['lease_id'] != b['lease_id']
    assert not despachos.operar('finalizar',event_id=a['id'],lease_id=a['lease_id'],message_id='ack-viejo')['actualizado']
    assert despachos.operar('finalizar',event_id=b['id'],lease_id=b['lease_id'],message_id='ack-vigente')['actualizado']


def test_consulta_publica_mensaje_y_respuestas_repetidas_o_atrasadas(sistema, tmp_path):
    oid, _ = crear(sistema)
    simulador = SimuladorEntregas(str(tmp_path/'erp.sqlite3'), avanzar=True)
    asyncio.run(despachos.publicar_pendientes())
    respuesta = simulador.responder(sistema[2][0])
    assert respuesta == simulador.responder(sistema[2][0])
    assert despachos.procesar_respuesta(respuesta)['aplicado']
    assert despachos.procesar_respuesta(respuesta)['duplicado']
    despachos.operar('consultar', orden_id=oid, actor='admin')
    asyncio.run(despachos.publicar_pendientes())
    assert sistema[2][-1]['event_type'] == 'despacho.estado.consultado'
    nueva = simulador.responder(sistema[2][-1])
    assert despachos.procesar_respuesta(nueva)['aplicado']
    assert datos(sistema, oid)['estado'] == 'en_preparacion'
    respuesta['event_id'] = str(uuid.uuid4())
    assert not despachos.procesar_respuesta(respuesta)['aplicado']
    assert datos(sistema, oid)['estado'] == 'en_preparacion'


def test_cancelacion_no_publica_despacho_pendiente(sistema):
    oid, _ = crear(sistema)
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute("UPDATE ordenes SET estado='cancelada' WHERE id=%s", (oid,))
    conn.close()
    asyncio.run(despachos.publicar_pendientes())
    assert [e['event_type'] for e in sistema[2]] == ['despacho.cancelacion.solicitada']
    assert datos(sistema, oid)['estado'] == 'cancelado'


def test_aislamiento_roles_y_consultas_api(sistema):
    oid, cliente = crear(sistema)
    client = TestClient(app)
    assert client.get(f'/api/v1/ordenes/{oid}/despacho').status_code == 401
    assert client.get(f'/api/v1/ordenes/{oid}/despacho',headers=headers()).status_code == 404
    assert client.get(f'/api/v1/ordenes/{oid}/despacho',headers=headers(cliente)).status_code == 200
    assert client.post(f'/api/v1/ordenes/{oid}/despacho/consultar',headers=headers(cliente)).status_code == 202
    assert client.post(f'/api/v1/ordenes/{oid}/despacho/reintentar',headers=headers(cliente)).status_code == 403
    assert client.post(f'/api/v1/ordenes/{oid}/despacho/reintentar',headers=headers(role='administrador')).status_code == 202
    assert len(datos(sistema, oid)['eventos']) == 2


def test_tablas_y_rpc_no_expuestos_a_anonimos(sistema):
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute("SELECT has_function_privilege('anon','public.operar_despacho(text,jsonb)','EXECUTE')")
        assert cur.fetchone()[0] is False
        cur.execute("SELECT has_table_privilege('authenticated','public.despachos_outbox','SELECT')")
        assert cur.fetchone()[0] is False
    conn.close()


def test_mensaje_sin_direccion_no_se_publica(sistema):
    oid, _ = crear(sistema)
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute('UPDATE ordenes SET entrega=NULL WHERE id=%s', (oid,))
    conn.close()
    asyncio.run(despachos.publicar_pendientes())
    assert not sistema[2]
    assert datos(sistema, oid)['eventos'][0]['estado'] == 'pendiente'
    assert 'dirección' in datos(sistema, oid)['eventos'][0]['ultimo_error']


def test_entrega_actualiza_orden_y_no_admite_respuestas_de_otro_despacho(sistema, tmp_path):
    oid, _ = crear(sistema)
    simulador = SimuladorEntregas(str(tmp_path/'erp.sqlite3'), avanzar=True)
    asyncio.run(despachos.publicar_pendientes())
    respuesta = simulador.responder(sistema[2][-1])
    despachos.procesar_respuesta(respuesta)
    for esperado in ('en_preparacion','en_transito','entregado'):
        despachos.operar('consultar', orden_id=oid, actor='admin')
        asyncio.run(despachos.publicar_pendientes())
        respuesta = simulador.responder(sistema[2][-1])
        despachos.procesar_respuesta(respuesta)
        assert datos(sistema, oid)['estado'] == esperado
    conn = sistema[1]()
    with conn.cursor() as cur:
        cur.execute('SELECT estado FROM ordenes WHERE id=%s', (oid,))
        assert cur.fetchone()[0] == 'entregada'
    conn.close()
    respuesta['event_id'] = str(uuid.uuid4())
    respuesta['payload']['orden_id'] = str(uuid.uuid4())
    with pytest.raises(HTTPException):
        despachos.procesar_respuesta(respuesta)


def test_roles_editables_del_cliente_no_otorgan_administracion(sistema):
    from backend.shared.security import create_access_token
    oid, cliente = crear(sistema)
    token = create_access_token({'sub': cliente, 'role': 'authenticated', 'user_metadata': {'role': 'administrador'}})
    res = TestClient(app).post(f'/api/v1/ordenes/{oid}/despacho/reintentar', headers={'Authorization': f'Bearer {token}'})
    assert res.status_code == 403


def test_checkout_real_encola_solo_despues_de_confirmar_pago_y_persistir(sistema, monkeypatch):
    from backend.shared import redis_client, flete
    from backend.services.ordenes.app import routers, routers_pagos
    client = TestClient(app)
    local, conectar, enviados = sistema
    cliente, variante, reserva = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO variantes(id,producto_id) VALUES(%s,%s)', (variante,str(uuid.uuid4())))
    conn.close()
    monkeypatch.setattr(redis_client, '_redis_unavailable', True)
    monkeypatch.setattr(redis_client, '_in_memory_store', {})
    monkeypatch.setattr(routers, '_get_supabase_safe', lambda: local)
    monkeypatch.setattr(routers, 'get_supabase_admin_client', lambda: local)
    monkeypatch.setattr(routers, '_ORDENES_DB', {})
    monkeypatch.setattr(routers_pagos, '_get_supabase_safe', lambda: None)
    async def ok(*args, **kwargs):
        return {'status':'OK','estado':'aprobado'}
    async def no_http(*args, **kwargs):
        raise AssertionError('No se debe invocar Entregas por HTTP desde el checkout')
    for obj, metodo in ((routers.inventarios_client,'descuento_definitivo'),(routers.pagos_client,'procesar_cobro'),
            (routers.pagos_client,'emitir_factura'),(routers.contabilidad_client,'registrar_asiento_venta'),
            (routers.crm_client,'consultar_o_canjear_puntos')):
        monkeypatch.setattr(obj,metodo,ok)
    monkeypatch.setattr(routers.entregas_client,'solicitar_despacho',no_http)
    item = {'variante_id':variante,'sku':'TEST-SHIP','nombre':'Artículo','cantidad':1,'precio_unitario':100}
    asyncio.run(redis_client.crear_reserva_stock(reserva,cliente,[item]))
    cotizacion = client.post('/api/v1/ordenes/flete/calcular',json={
        'ciudad':'La Paz','zona':'Centro','direccion':'Av. Arce 123','reserva_id':reserva})
    assert cotizacion.status_code == 200, cotizacion.text
    token = cotizacion.json()['cotizacion_flete']
    claims = flete.validar_cotizacion(token,reserva,cliente)
    pago = client.post('/api/v1/pagos/iniciar',json={
        'monto':float(claims['total']),'metodo_pago':'tarjeta','cliente_id':cliente,
        'reserva_id':reserva,'cotizacion_flete':token})
    assert pago.status_code == 201, pago.text
    resultado = client.post('/api/v1/ordenes/',json={
        'cliente_id':cliente,'reserva_id':reserva,'tipo_despacho':'domicilio',
        'subtotal':100,'costo_envio':float(claims['costo_flete']),'total':float(claims['total']),
        'cotizacion_flete':token,'transaccion_id':pago.json()['transaccion_id'],
        'items':[{**item,'nombre_producto':'Artículo'}]})
    assert resultado.status_code == 201, resultado.text
    oid = resultado.json()['id']
    assert resultado.json()['tracking_number'] is None
    assert not enviados
    assert datos(sistema,oid)['estado'] == 'pendiente'
    asyncio.run(despachos.publicar_pendientes())
    assert len(enviados) == 1 and enviados[0]['payload']['orden_id'] == oid


def test_respuesta_invalida_no_se_confirma_y_error_db_se_reentrega(monkeypatch):
    ack = []
    class Subscriber:
        def pull(self, **kwargs):
            return SimpleNamespace(received_messages=[SimpleNamespace(ack_id='ack-1',message=SimpleNamespace(
                message_id='msg-1',data=b'{}',attributes={'destino':'maxiconecta'}))])
        def acknowledge(self, request):
            ack.extend(request['ack_ids'])
    asyncio.run(despachos.consumir_lote(Subscriber(), 'sub-test'))
    assert ack == ['ack-1']
    ack.clear()
    def fallo(_, **_metadata):
        raise HTTPException(503,'BD caída')
    monkeypatch.setattr(despachos,'procesar_respuesta',fallo)
    asyncio.run(despachos.consumir_lote(Subscriber(), 'sub-test'))
    assert not ack
