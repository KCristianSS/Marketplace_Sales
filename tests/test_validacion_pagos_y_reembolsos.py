"""KAN-54 (validación de pagos de una orden) y KAN-55 (reembolsos totales/parciales)."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from fastapi.testclient import TestClient

from backend.services.ordenes.app.main import app as ordenes_app
from backend.services.pos.app.main import app as pos_app
from backend.shared.audit import AUDIT_LOGS_EN_MEMORIA
from backend.shared.caja_store import CAJAS_EN_MEMORIA
from backend.shared.erp_clients.contabilidad import ContabilidadClient
from backend.shared.pagos_firma import firmar_webhook
from backend.shared.security import create_access_token

ordenes = TestClient(ordenes_app)
pos = TestClient(pos_app)


def _auth(role: str, uid: str | None = None):
    uid = uid or str(uuid.uuid4())
    return {"Authorization": f"Bearer {create_access_token({'sub': uid, 'role': role})}"}, uid


def _orden(total: float = 100.0, headers=None, cliente_id=None, canal="pos"):
    headers = headers or _auth("cajero")[0]
    body = {"canal": canal, "items": [{"variante_id": str(uuid.uuid4()), "sku": "SKU-1", "nombre_producto": "Producto", "cantidad": 1, "precio_unitario": total}]}
    if cliente_id:
        body["cliente_id"] = cliente_id
    r = ordenes.post("/api/v1/ordenes/pendiente", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _caja(headers):
    r = pos.post("/api/v1/pos/caja/abrir", json={"sucursal_id": str(uuid.uuid4()), "fondo_inicial": 100}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _pagar(orden_id, metodo, monto, headers, **extra):
    return ordenes.post("/api/v1/pagos/registrar", json={"orden_id": orden_id, "metodo": metodo, "monto": monto, **extra}, headers=headers)


def _webhook(tx, evento="pago.aprobado", firma=True, monto=None, client=None):
    body = {"transaccion_id": tx, "evento": evento}
    if monto is not None:
        body["monto"] = monto
    if firma:
        body["firma_hmac"] = firmar_webhook(tx, evento, monto)
    return (client or ordenes).post("/api/v1/pagos/webhook", json=body)


def _estado(orden_id, headers):
    return ordenes.get(f"/api/v1/ordenes/{orden_id}/pagos", headers=headers).json()


# ================================== KAN-54 ==================================
def test_orden_permanece_pendiente_hasta_que_la_suma_aprobada_iguale_el_total():
    h, _ = _auth("cajero")
    _caja(h)
    oid = _orden(100, h)
    r1 = _pagar(oid, "efectivo", 40, h, monto_recibido=50)
    assert r1.status_code == 201 and r1.json()["pago"]["estado"] == "aprobado" and Decimal(r1.json()["cambio"]) == 10
    st = _estado(oid, h)
    assert st["estado_orden"] == "pendiente" and Decimal(st["saldo_pendiente"]) == 60 and st["apta_para_preparacion"] is False

    r2 = _pagar(oid, "qr", 60, h)
    assert r2.status_code == 201 and r2.json()["pago"]["estado"] == "pendiente" and r2.json()["qr_payload"]
    assert _estado(oid, h)["estado_orden"] == "pendiente"

    assert _webhook(r2.json()["pago"]["transaccion_id"]).status_code == 200
    st = _estado(oid, h)
    assert st["estado_orden"] == "entregada" and st["apta_para_preparacion"] is True and Decimal(st["saldo_pendiente"]) == 0
    nuevos = [(x["tipo"], x["estado_nuevo"]) for x in st["historial"]]
    assert ("pago", "aprobado") in nuevos and ("orden", "entregada") in nuevos


def test_webhook_repetido_es_idempotente():
    h, _ = _auth("cajero")
    oid = _orden(80, h)
    tx = _pagar(oid, "tarjeta", 80, h).json()["pago"]["transaccion_id"]
    primero = _webhook(tx).json()
    assert primero["duplicado"] is False and primero["estado_orden"] == "entregada"
    n_hist = len(_estado(oid, h)["historial"])
    for _ in range(3):
        rep = _webhook(tx)
        assert rep.status_code == 200 and rep.json()["duplicado"] is True
    st = _estado(oid, h)
    assert len(st["historial"]) == n_hist and len(st["pagos"]) == 1 and Decimal(st["total_aprobado"]) == 80


def test_webhook_tardio_contradictorio_no_cambia_un_pago_ya_aprobado():
    h, _ = _auth("cajero")
    oid = _orden(50, h)
    tx = _pagar(oid, "qr", 50, h).json()["pago"]["transaccion_id"]
    _webhook(tx, "pago.aprobado")
    r = _webhook(tx, "pago.rechazado")
    assert r.json()["duplicado"] is True and r.json()["conflicto"] is True
    assert _estado(oid, h)["pagos"][0]["estado"] == "aprobado"


def test_webhooks_simultaneos_se_aplican_una_sola_vez():
    h, _ = _auth("cajero")
    oid = _orden(70, h)
    tx = _pagar(oid, "qr", 70, h).json()["pago"]["transaccion_id"]
    # Un único portal ASGI comparte el event loop, igual que Uvicorn. Crear un
    # loop por hilo bloquea asyncio.Lock aunque el servicio sea correcto.
    with TestClient(ordenes_app) as concurrent_client, ThreadPoolExecutor(4) as pool:
        res = [f.result().json() for f in [pool.submit(_webhook, tx, client=concurrent_client) for _ in range(4)]]
    assert sum(1 for r in res if r["duplicado"] is False) == 1
    assert len([x for x in _estado(oid, h)["historial"] if x["tipo"] == "orden"]) == 1


def test_firma_hmac_obligatoria_y_valida():
    h, _ = _auth("cajero")
    oid = _orden(30, h)
    tx = _pagar(oid, "qr", 30, h).json()["pago"]["transaccion_id"]
    assert _webhook(tx, firma=False).status_code == 401
    mala = ordenes.post("/api/v1/pagos/webhook", json={"transaccion_id": tx, "evento": "pago.aprobado", "firma_hmac": "0" * 64})
    assert mala.status_code == 401
    # firma de un evento distinto no sirve para este
    cruzada = ordenes.post("/api/v1/pagos/webhook", json={"transaccion_id": tx, "evento": "pago.aprobado", "firma_hmac": firmar_webhook(tx, "pago.rechazado")})
    assert cruzada.status_code == 401
    assert _estado(oid, h)["pagos"][0]["estado"] == "pendiente"


def test_pago_rechazado_no_avanza_la_orden_y_permite_reintentar_con_otro_medio():
    h, _ = _auth("cajero")
    _caja(h)
    oid = _orden(90, h)
    p = _pagar(oid, "tarjeta", 90, h).json()["pago"]
    rech = _webhook(p["transaccion_id"], "pago.rechazado").json()
    assert rech["estado_pago"] == "rechazado"
    st = _estado(oid, h)
    assert st["estado_orden"] == "pendiente" and Decimal(st["saldo_pendiente"]) == 90

    reintento = _pagar(oid, "efectivo", 90, h, reintento_de=p["id"])
    assert reintento.status_code == 201 and reintento.json()["pago"]["intento"] == 2
    assert reintento.json()["estado_orden"] == "entregada"
    # no se puede reintentar algo que no está rechazado
    assert _pagar(_orden(10, h), "efectivo", 10, h, reintento_de=reintento.json()["pago"]["id"]).status_code == 422


def test_efectivo_exige_caja_abierta_y_suma_al_turno():
    h, _ = _auth("cajero")
    oid = _orden(60, h)
    r = _pagar(oid, "efectivo", 60, h)
    assert r.status_code == 403 and "caja abierta" in r.json()["detail"]
    assert _estado(oid, h)["pagos"] == []

    caja_id = _caja(h)
    assert _pagar(oid, "efectivo", 60, h).status_code == 201
    assert CAJAS_EN_MEMORIA[caja_id]["total_efectivo"] == 60.0
    assert _estado(oid, h)["pagos"][0]["caja_turno_id"] == caja_id


def test_pago_en_efectivo_entra_al_esperado_del_arqueo_ciego():
    h, _ = _auth("cajero")
    caja_id = _caja(h)  # fondo 100
    _pagar(_orden(60, h), "efectivo", 60, h)
    rep = pos.post(f"/api/v1/pos/caja/{caja_id}/arqueo-ciego", json={"desglose": [{"denominacion": 100, "cantidad": 1}, {"denominacion": 50, "cantidad": 1}, {"denominacion": 10, "cantidad": 1}]}, headers=h).json()
    assert Decimal(rep["total_esperado"]) == 160 and rep["resultado"] == "cuadrado"


def test_monto_mayor_al_saldo_y_orden_no_pendiente_se_rechazan():
    h, _ = _auth("cajero")
    oid = _orden(100, h)
    assert _pagar(oid, "qr", 100.01, h).status_code == 422
    _pagar(oid, "qr", 60, h)
    assert _pagar(oid, "tarjeta", 50, h).status_code == 422  # 60 ya está en curso: solo faltan 40
    tx = _pagar(oid, "tarjeta", 40, h).json()["pago"]["transaccion_id"]
    _webhook(tx)
    assert _pagar(oid, "qr", 1, h).status_code == 422  # 40 aprobados + 60 en curso: nada por cubrir
    oid2 = _orden(10, h)
    tx2 = _pagar(oid2, "qr", 10, h).json()["pago"]["transaccion_id"]
    _webhook(tx2)
    assert _pagar(oid2, "qr", 1, h).status_code == 409  # orden ya entregada
    assert _pagar(str(uuid.uuid4()), "qr", 1, h).status_code == 404


def test_registrar_es_idempotente_por_transaccion_id():
    h, _ = _auth("cajero")
    oid = _orden(100, h)
    a = _pagar(oid, "qr", 50, h, transaccion_id="TX-CLIENTE-001")
    b = _pagar(oid, "qr", 50, h, transaccion_id="TX-CLIENTE-001")
    assert a.status_code == 201 and b.status_code == 201 and b.json()["duplicado"] is True
    assert len(_estado(oid, h)["pagos"]) == 1
    assert _pagar(oid, "qr", 20, h, transaccion_id="TX-CLIENTE-001").status_code == 409


def test_permisos_de_pagos_cliente_dueno_y_efectivo():
    cli, cid = _auth("cliente")
    oid = _orden(40, cliente_id=cid)
    assert _pagar(oid, "efectivo", 40, cli).status_code == 403
    assert _pagar(oid, "qr", 40, cli).status_code == 201
    assert ordenes.get(f"/api/v1/ordenes/{oid}/pagos", headers=cli).status_code == 200
    otro, _ = _auth("cliente")
    assert ordenes.get(f"/api/v1/ordenes/{oid}/pagos", headers=otro).status_code == 403
    assert _pagar(oid, "qr", 1, otro).status_code == 403
    assert ordenes.get(f"/api/v1/ordenes/{oid}/pagos").status_code == 401


def test_simular_webhook_aprueba_y_confirma():
    h, _ = _auth("cajero")
    oid = _orden(25, h)
    tx = _pagar(oid, "pasarela", 25, h).json()["pago"]["transaccion_id"]
    r = ordenes.post("/api/v1/pagos/simular-webhook", json={"transaccion_id": tx, "resultado": "aprobado"})
    assert r.status_code == 200 and r.json()["estado_orden"] == "entregada"


# ================================== KAN-55 ==================================
def _orden_pagada(metodos):
    """Crea una orden y la paga con [(metodo, monto)], devolviendo (orden_id, [pagos])."""
    h, _ = _auth("cajero")
    _caja(h)
    oid = _orden(sum(m for _, m in metodos), h)
    pagos = []
    for metodo, monto in metodos:
        r = _pagar(oid, metodo, monto, h).json()
        if metodo != "efectivo":
            _webhook(r["pago"]["transaccion_id"])
        pagos.append(r["pago"])
    return oid, pagos


def _reembolsar(body, headers=None):
    return ordenes.post("/api/v1/reembolsos", json=body, headers=headers or _auth("administrador")[0])


def test_vale_no_puede_reembolsarse_ni_incluirse_en_orden_mixta():
    from backend.services.ordenes.app.pagos_repo import repo
    oid, (pago,) = _orden_pagada([('tarjeta', 60)])
    vale = repo.insertar_pago({'orden_id': oid, 'metodo': 'vale', 'monto': Decimal('40'),
                               'estado': 'aprobado', 'transaccion_id': f'VALE-{uuid.uuid4()}'})
    assert _reembolsar({'pago_id': vale['id'], 'motivo': 'Devolución'}).status_code == 422
    assert _reembolsar({'orden_id': oid, 'monto': 100, 'motivo': 'Devolución'}).status_code == 422
    resultado = _reembolsar({'orden_id': oid, 'motivo': 'Devolución'})
    assert resultado.status_code == 201
    assert Decimal(resultado.json()['monto_total']) == 60
    assert all(r['metodo'] != 'vale' for r in resultado.json()['reembolsos'])


def test_reembolso_mayor_al_saldo_reembolsable_se_rechaza():
    oid, (p,) = _orden_pagada([("tarjeta", 100)])
    assert _reembolsar({"pago_id": p["id"], "monto": 100.01, "motivo": "Exceso"}).status_code == 422
    ok = _reembolsar({"pago_id": p["id"], "monto": 60, "motivo": "Devolución parcial"})
    assert ok.status_code == 201 and ok.json()["completados"] == 1
    assert Decimal(ok.json()["reembolsos"][0]["saldo_reembolsable_pago"]) == 40
    assert _reembolsar({"pago_id": p["id"], "monto": 40.01, "motivo": "Excede lo restante"}).status_code == 422
    final = _reembolsar({"pago_id": p["id"], "motivo": "Resto"})  # sin monto = saldo
    assert final.status_code == 201 and Decimal(final.json()["monto_total"]) == 40
    assert _reembolsar({"pago_id": p["id"], "motivo": "Otra vez"}).status_code == 422  # sin saldo
    h = _auth("administrador")[0]
    assert ordenes.get(f"/api/v1/ordenes/{oid}/pagos", headers=h).json()["pagos"][0]["estado"] == "reembolsado"


def test_pago_dividido_se_reembolsa_por_tramo_y_medio():
    oid, (efectivo, qr) = _orden_pagada([("efectivo", 60), ("qr", 40)])
    r = _reembolsar({"orden_id": oid, "monto": 70, "motivo": "Devolución de producto"})
    assert r.status_code == 201
    por_metodo = {x["metodo"]: Decimal(x["monto"]) for x in r.json()["reembolsos"]}
    assert por_metodo == {"qr": Decimal(40), "efectivo": Decimal(30)}  # último tramo primero, cada uno por su medio
    exceso = _reembolsar({"orden_id": oid, "monto": 31, "motivo": "Excede"})  # quedan 30
    assert exceso.status_code == 422
    assert _reembolsar({"pago_id": qr["id"], "monto": 1, "motivo": "Tramo ya devuelto"}).status_code == 422


def test_reembolso_fallido_queda_fallido_y_se_puede_reintentar():
    oid, (p,) = _orden_pagada([("tarjeta", 50)])
    r = _reembolsar({"pago_id": p["id"], "monto": 50, "motivo": "Cliente desistió", "simular_fallo": True}).json()
    assert r["fallidos"] == 1 and r["reembolsos"][0]["estado"] == "fallido" and r["reembolsos"][0]["error"]
    rid = r["reembolsos"][0]["id"]
    # el fallido no consume saldo, pero no se puede duplicar mientras tanto sin pasar saldo: se reintenta
    h = _auth("administrador")[0]
    again = ordenes.post(f"/api/v1/reembolsos/{rid}/reintentar", json={}, headers=h)
    assert again.status_code == 200 and again.json()["estado"] == "completado" and again.json()["intento"] == 2
    assert ordenes.post(f"/api/v1/reembolsos/{rid}/reintentar", json={}, headers=h).status_code == 409
    assert ordenes.post(f"/api/v1/reembolsos/{uuid.uuid4()}/reintentar", json={}, headers=h).status_code == 404


def test_reintento_falla_si_el_saldo_ya_fue_usado_por_otro_reembolso():
    oid, (p,) = _orden_pagada([("tarjeta", 50)])
    fallido = _reembolsar({"pago_id": p["id"], "monto": 50, "motivo": "Primero", "simular_fallo": True}).json()["reembolsos"][0]
    assert _reembolsar({"pago_id": p["id"], "monto": 50, "motivo": "Segundo"}).status_code == 201
    r = ordenes.post(f"/api/v1/reembolsos/{fallido['id']}/reintentar", json={}, headers=_auth("administrador")[0])
    assert r.status_code == 422


def test_reembolso_completado_notifica_contabilidad_y_audita(monkeypatch):
    notificados = []

    async def espia(self, data):
        notificados.append(data)
        return {"asiento_id": "ASI-1", "estado": "asentado"}

    monkeypatch.setattr(ContabilidadClient, "registrar_reembolso", espia)
    oid, (p,) = _orden_pagada([("qr", 30)])
    antes = len(AUDIT_LOGS_EN_MEMORIA)
    r = _reembolsar({"pago_id": p["id"], "monto": 30, "motivo": "Error de cobro"}).json()["reembolsos"][0]
    assert notificados and notificados[0]["reembolso_id"] == r["id"] and r["contabilidad"]["asiento_id"] == "ASI-1"
    assert any(a["action"] == "REEMBOLSO_COMPLETADO" and a["entity_id"] == r["id"] for a in AUDIT_LOGS_EN_MEMORIA[antes:])
    assert r["comprobante"] is None  # no es efectivo


def test_reembolso_de_efectivo_genera_comprobante_de_egreso():
    oid, (p,) = _orden_pagada([("efectivo", 45)])
    r = _reembolsar({"pago_id": p["id"], "monto": 45, "motivo": "Devolución"}).json()["reembolsos"][0]
    assert r["numero_comprobante"].startswith("CE-") and r["comprobante"]["metodo"] == "efectivo"
    assert Decimal(r["comprobante"]["monto"]) == 45 and r["comprobante"]["codigo_orden"].startswith("ORD-")


def test_solo_pagos_aprobados_y_solo_administrador():
    h, _ = _auth("cajero")
    oid = _orden(30, h)
    pendiente = _pagar(oid, "qr", 30, h).json()["pago"]
    assert _reembolsar({"pago_id": pendiente["id"], "motivo": "No aprobado"}).status_code == 409
    assert _reembolsar({"pago_id": str(uuid.uuid4()), "motivo": "No existe"}).status_code == 404
    assert _reembolsar({"pago_id": pendiente["id"], "motivo": "Cajero"}, headers=h).status_code == 403
    assert ordenes.get("/api/v1/reembolsos", headers=h).status_code == 403
    assert _reembolsar({"pago_id": pendiente["id"], "orden_id": oid, "motivo": "Ambos"}).status_code == 422
    assert _reembolsar({"pago_id": pendiente["id"], "motivo": "x"}).status_code == 422  # motivo muy corto


def test_listado_con_filtros_y_paginacion():
    oid, (p,) = _orden_pagada([("tarjeta", 20)])
    _reembolsar({"pago_id": p["id"], "monto": 5, "motivo": "Uno"})
    _reembolsar({"pago_id": p["id"], "monto": 5, "motivo": "Dos", "simular_fallo": True})
    h = _auth("administrador")[0]
    todos = ordenes.get(f"/api/v1/reembolsos?orden_id={oid}", headers=h).json()
    assert todos["total"] == 2 and {x["estado"] for x in todos["items"]} == {"completado", "fallido"}
    assert todos["items"][0]["codigo_orden"].startswith("ORD-")
    fallidos = ordenes.get(f"/api/v1/reembolsos?orden_id={oid}&estado=fallido", headers=h).json()
    assert fallidos["total"] == 1
    pag = ordenes.get(f"/api/v1/reembolsos?orden_id={oid}&limit=1&page=2", headers=h).json()
    assert len(pag["items"]) == 1 and pag["total"] == 2
    assert ordenes.get(f"/api/v1/reembolsos/{todos['items'][0]['id']}", headers=h).status_code == 200


def test_pago_completo_web_confirma_sin_marcar_entregado():
    headers, cliente_id = _auth("cliente")
    oid = _orden(50, headers, cliente_id=cliente_id, canal="web")
    tx = _pagar(oid, "qr", 50, headers).json()["pago"]["transaccion_id"]
    assert _webhook(tx).status_code == 200
    assert _estado(oid, headers)["estado_orden"] == "confirmada"
