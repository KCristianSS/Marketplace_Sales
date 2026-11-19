import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend.tests.test_tarjetas_regalo import postgres


def test_arqueo_y_cierre_se_guardan_juntos_o_se_revierten(postgres):
    from psycopg2 import IntegrityError

    conn = postgres()
    with conn.cursor() as cur:
        cur.execute('CREATE TABLE caja_turnos (id uuid PRIMARY KEY, estado text, monto_cierre_real numeric, diferencia numeric, observaciones text, closed_at timestamptz)')
        migration = Path(__file__).parents[1] / 'db/migrations/20261110065058_arqueo_ciego_atomico.sql'
        cur.execute(migration.read_text(encoding='utf-8'))
        turno, arqueo, cajero, sucursal = (str(uuid4()) for _ in range(4))
        cur.execute("INSERT INTO caja_turnos(id,estado) VALUES (%s,'abierta')", (turno,))
        datos = {'id': arqueo, 'numero_reporte': 'TEST-1', 'caja_turno_id': turno,
                 'cajero_id': cajero, 'sucursal_id': sucursal, 'fondo_inicial': 100,
                 'ventas_efectivo': 0, 'entradas_extraordinarias': 0, 'retiros_boveda': 0,
                 'total_esperado': 100, 'total_declarado': 100, 'diferencia': 0,
                 'estado_cuadre': 'cuadrado', 'con_diferencia': False, 'observaciones': None,
                 'total_tarjeta': 0, 'total_qr': 0, 'notificacion_contabilidad': None,
                 'created_at': '2026-11-10T00:00:00Z'}
        invalido = [{'tipo': 'billete', 'denominacion': 99, 'cantidad': 1, 'subtotal': 99}]
        with pytest.raises(IntegrityError):
            cur.execute('SELECT public.confirmar_arqueo_ciego(%s::jsonb,%s::jsonb)', (json.dumps(datos), json.dumps(invalido)))
        cur.execute('SELECT estado FROM caja_turnos WHERE id=%s', (turno,))
        assert cur.fetchone()[0] == 'abierta'
        cur.execute('SELECT count(*) FROM arqueo_caja WHERE id=%s', (arqueo,))
        assert cur.fetchone()[0] == 0
        detalle = [{'tipo': 'billete', 'denominacion': 100, 'cantidad': 1, 'subtotal': 100}]
        cur.execute('SELECT public.confirmar_arqueo_ciego(%s::jsonb,%s::jsonb)', (json.dumps(datos), json.dumps(detalle)))
        assert cur.fetchone()[0] is True
        cur.execute('SELECT public.confirmar_arqueo_ciego(%s::jsonb,%s::jsonb)', (json.dumps(datos), json.dumps(detalle)))
        assert cur.fetchone()[0] is False
        cur.execute('SELECT estado FROM caja_turnos WHERE id=%s', (turno,))
        assert cur.fetchone()[0] == 'cerrada'
        cur.execute('SELECT count(*) FROM arqueo_detalle WHERE arqueo_id=%s', (arqueo,))
        assert cur.fetchone()[0] == 1
    conn.close()
