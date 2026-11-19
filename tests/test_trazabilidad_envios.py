"""Auditoría y cotizaciones simuladas contra PostgreSQL local efímero, sin publicar en GCP."""
import asyncio
import json
import logging
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.shared import envios_eventos, flete
from backend.shared.config import settings
from backend.shared.flete_config import ConfiguracionFlete, configuracion_inicial
from backend.shared.pubsub_client import GooglePubSubClient
from backend.services.ordenes.app.main import app
from backend.services.ordenes.app.schemas import CalculoFleteRequest
from backend.tests.test_despachos_pubsub import db as db_despachos, postgres
from backend.tests.test_tarjetas_regalo import headers
from backend.scripts.simular_entregas import SimuladorEntregas


@pytest.fixture(scope='module')
def db_trazas(db_despachos):
    local, conectar = db_despachos
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute((Path(__file__).parents[1] / 'db/migrations/20261109171752_trazabilidad_envios.sql').read_text(encoding='utf-8'))
    conn.close()
    return local, conectar


@pytest.fixture
def entorno(db_trazas, monkeypatch):
    local, conectar = db_trazas
    conn = conectar()
    with conn.cursor() as cur:
        cur.execute('TRUNCATE envios_mensajes_log,envios_cotizaciones_outbox')
    conn.close()
    monkeypatch.setattr(envios_eventos, 'get_supabase_admin_client', lambda: local)
    monkeypatch.setattr(settings, 'PUBSUB_COTIZACIONES_SIMULACION_ENABLED', True)
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'development')
    monkeypatch.setattr(GooglePubSubClient, '_resolve_credentials_path', lambda self: '__emulator__')
    enviados = []
    def publicar(self, envelope, attrs, _credentials):
        enviados.append((envelope, attrs))
        return 'gcp-confirmado-' + envelope['event_id']
    monkeypatch.setattr(GooglePubSubClient, '_publicar_google_cloud', publicar)
    return local, conectar, enviados


def consulta(entorno, sql, params=()):
    conn = entorno[1]()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    return rows


def encolar(entorno):
    identificador = str(uuid.uuid4())
    payload = dict(simulacion=True, cotizacion_id=identificador, calculo={'costo_flete':'35.00','total':'435.00'})
    envios_eventos.operar_cotizacion('encolar', id=identificador, payload=payload)
    return identificador


def test_publica_calculo_y_guarda_mensaje_confirmado_y_log(entorno, caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error.pubsub')
    eid = encolar(entorno)
    assert asyncio.run(envios_eventos.publicar_cotizaciones_pendientes()) == 1
    enviado, attrs = entorno[2][0]
    assert enviado['event_type'] == 'despacho.cotizacion.calculada'
    assert enviado['event_id'] == enviado['correlation_id'] == eid
    assert enviado['payload']['simulacion'] is True
    assert attrs['simulacion'] == 'true'
    assert consulta(entorno, 'SELECT estado,intentos FROM envios_cotizaciones_outbox') == [('publicado',1)]
    guardado = consulta(entorno, 'SELECT estado,mensaje,message_id FROM envios_mensajes_log')[0]
    assert guardado[0] == 'publicado' and guardado[1] == enviado
    assert guardado[2] == 'gcp-confirmado-' + eid
    assert 'MENSAJE ENVIADO' in caplog.text and eid in caplog.text


def test_sin_confirmacion_no_se_marca_enviado_y_reintenta_mismo_evento(entorno, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error.pubsub')
    eid = encolar(entorno)
    monkeypatch.setattr(GooglePubSubClient, '_resolve_credentials_path', lambda self: None)
    asyncio.run(envios_eventos.publicar_cotizaciones_pendientes())
    assert consulta(entorno, 'SELECT estado,message_id,intentos FROM envios_cotizaciones_outbox') == [('pendiente',None,1)]
    assert consulta(entorno, 'SELECT estado,message_id FROM envios_mensajes_log') == [('error_publicacion',None)]
    assert 'MENSAJE ENVIADO' not in caplog.text
    conn = entorno[1]()
    with conn.cursor() as cur:
        cur.execute("UPDATE envios_cotizaciones_outbox SET disponible_desde=now()-interval '1 second'")
    conn.close()
    monkeypatch.setattr(GooglePubSubClient, '_resolve_credentials_path', lambda self: '__emulator__')
    asyncio.run(envios_eventos.publicar_cotizaciones_pendientes())
    assert entorno[2][0][0]['event_id'] == eid
    assert consulta(entorno, 'SELECT estado,intentos FROM envios_cotizaciones_outbox') == [('publicado',2)]
    assert consulta(entorno, 'SELECT count(*) FROM envios_mensajes_log')[0][0] == 2


def test_lease_impide_doble_publicacion_y_finalizacion_atrasada(entorno):
    eid = encolar(entorno)
    primero = envios_eventos.operar_cotizacion('reclamar')['eventos'][0]
    assert not envios_eventos.operar_cotizacion('reclamar')['eventos']
    conn = entorno[1]()
    with conn.cursor() as cur:
        cur.execute("UPDATE envios_cotizaciones_outbox SET lease_hasta=now()-interval '1 second'")
    conn.close()
    segundo = envios_eventos.operar_cotizacion('reclamar')['eventos'][0]
    assert primero['id'] == segundo['id'] == eid
    assert not envios_eventos.operar_cotizacion('finalizar', id=eid, lease_id=primero['lease_id'], message_id='viejo')['actualizado']
    assert envios_eventos.operar_cotizacion('finalizar', id=eid, lease_id=segundo['lease_id'], message_id='nuevo')['actualizado']


def test_simulador_confirma_cotizacion_sin_crear_despacho_y_es_idempotente(entorno, tmp_path):
    eid = encolar(entorno)
    asyncio.run(envios_eventos.publicar_cotizaciones_pendientes())
    evento = entorno[2][0][0]
    simulador = SimuladorEntregas(str(tmp_path / 'erp.sqlite3'))
    respuesta = simulador.responder(evento)
    assert simulador.responder(evento) == respuesta
    assert respuesta['event_type'] == 'despacho.cotizacion.recibida'
    assert respuesta['payload']['calculo'] == evento['payload']['calculo']
    assert envios_eventos.registrar_respuesta_cotizacion(respuesta, atributos={'destino':'maxiconecta'}, message_id='respuesta-gcp')['recibido']
    assert consulta(entorno, "SELECT estado,direccion FROM envios_mensajes_log WHERE direccion='entrada'") == [('recibido','entrada')]
    assert consulta(entorno, "SELECT message_id,atributos FROM envios_mensajes_log WHERE direccion='entrada'") == [('respuesta-gcp',{'destino':'maxiconecta'})]
    with sqlite3.connect(simulador.archivo) as conn:
        assert conn.execute('SELECT count(*) FROM solicitudes').fetchone()[0] == 0
    respuesta['correlation_id'] = str(uuid.uuid4())
    with pytest.raises(ValueError):
        envios_eventos.registrar_respuesta_cotizacion(respuesta)


def test_vista_conserva_pendientes_publicados_y_respuestas_sin_limite_20(entorno):
    for _ in range(25):
        encolar(entorno)
    asyncio.run(envios_eventos.publicar_cotizaciones_pendientes())
    assert consulta(entorno, "SELECT count(*) FROM envios_trazabilidad WHERE simulacion AND registro='estado_actual'") == [(25,)]
    assert consulta(entorno, "SELECT count(*) FROM envios_trazabilidad WHERE simulacion AND registro='mensaje' AND estado='publicado'") == [(10,)]


def test_tablas_vista_y_rpc_no_son_publicos(entorno):
    for role in ['anon','authenticated']:
        assert consulta(entorno, "SELECT has_table_privilege(%s,'envios_trazabilidad','SELECT'), has_table_privilege(%s,'envios_cotizaciones_outbox','SELECT'), has_function_privilege(%s,'operar_cotizacion_envio(text,jsonb)','EXECUTE')", (role,role,role)) == [(False,False,False)]


@pytest.mark.parametrize('role', ['cliente','cajero'])
def test_trazabilidad_restringida_a_administracion(role):
    r = TestClient(app).get('/api/v1/ordenes/despachos/trazabilidad', headers=headers(role=role))
    assert r.status_code == 403


def test_calculo_reserva_incluye_desglose_sin_token_ni_direccion(monkeypatch):
    capturados = []
    monkeypatch.setattr(settings, 'PUBSUB_COTIZACIONES_SIMULACION_ENABLED', True)
    monkeypatch.setattr(envios_eventos, 'operar_cotizacion', lambda accion, **datos: capturados.append(datos))
    config = configuracion_inicial()
    async def obtener(): return {'version': 7, 'configuracion':config}
    async def reserva(_): return {'status':'ACTIVA','cliente_id':'cliente','expires_at':9999999999,
        'items':[{'variante_id':str(uuid.uuid4()),'cantidad':4,'precio_unitario':100}]}
    monkeypatch.setattr(flete, 'obtener_configuracion', obtener)
    monkeypatch.setattr(flete, 'consultar_reserva', reserva)
    payload = CalculoFleteRequest(ciudad='La Paz',zona='Centro',direccion='Privada 123',reserva_id='reserva',
                                  tipo_envio='express_mismo_dia',puntos_canjeados=10)
    resultado = asyncio.run(flete.cotizar_flete(payload))
    evento = capturados[0]['payload']
    assert evento['simulacion'] is True and evento['configuracion_version'] == 7
    assert evento['calculo']['costo_flete'] == 35
    assert evento['calculo']['total'] == 430
    assert evento['entradas']['descuento_puntos'] == 5
    assert evento['calculo']['desglose']['recargo_peso'] == 5
    assert 'cotizacion_flete' in resultado
    assert 'cotizacion_flete' not in json.dumps(evento) and 'Privada 123' not in json.dumps(evento)
    assert 'formulas' in evento
