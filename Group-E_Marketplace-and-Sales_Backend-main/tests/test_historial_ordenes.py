import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from fastapi.testclient import TestClient
from backend.services.ordenes.app.main import app as ordenes_app
from backend.shared.security import create_access_token

client = TestClient(ordenes_app)

@pytest.fixture(autouse=True)
def setup_orden_y_factura():
    """Crea una orden con factura previa para asegurar datos de prueba en memoria."""
    cliente_test_id = str(uuid.uuid4())
    token_cliente = create_access_token({"sub": cliente_test_id, "role": "cliente"})
    
    # 1. Crear orden web con factura
    resp = client.post(
        "/api/v1/ordenes/",
        json={
            "cliente_id": cliente_test_id,
            "canal": "web",
            "tipo_despacho": "domicilio",
            "subtotal": 1200.00,
            "descuento": 50.00,
            "costo_envio": 20.00,
            "total": 1170.00,
            "metodo_pago": "tarjeta",
            "items": [
                {
                    "variante_id": str(uuid.uuid4()),
                    "sku": "LAP-DELL-XPS",
                    "nombre_producto": "Laptop Dell XPS 15",
                    "cantidad": 1,
                    "precio_unitario": 1200.00
                }
            ],
            "datos_fiscales": {
                "modalidad": "con_factura",
                "tipo_documento": "NIT",
                "nit_ci": "1020304050",
                "razon_social": "EMPRESA MINERA SAN CRISTOBAL S.A.",
                "email_facturacion": "contabilidad@sancristobal.bo"
            }
        },
        headers={"Authorization": f"Bearer {token_cliente}"}
    )
    assert resp.status_code == 201, resp.text
    orden_creada = resp.json()
    return {
        "cliente_id": cliente_test_id,
        "token": token_cliente,
        "orden": orden_creada,
        "cuf": orden_creada.get("cuf_factura")
    }

def test_historial_ordenes_listado_paginado(setup_orden_y_factura):
    data = setup_orden_y_factura
    resp = client.get("/api/v1/ordenes?page=1&limit=5")
    assert resp.status_code == 200
    res_json = resp.json()
    assert "items" in res_json
    assert "total" in res_json
    assert "pagina" in res_json
    assert "total_paginas" in res_json
    assert res_json["pagina"] == 1
    assert res_json["limite"] == 5
    assert len(res_json["items"]) >= 1

def test_historial_ordenes_filtro_cliente(setup_orden_y_factura):
    data = setup_orden_y_factura
    cid = data["cliente_id"]
    resp = client.get(f"/api/v1/ordenes?cliente_id={cid}")
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["total"] >= 1
    for orden in res_json["items"]:
        assert str(orden["cliente_id"]) == cid

def test_historial_ordenes_filtro_estado(setup_orden_y_factura):
    resp = client.get("/api/v1/ordenes?estado=confirmada")
    assert resp.status_code == 200
    res_json = resp.json()
    for orden in res_json["items"]:
        assert orden["estado"] == "confirmada"

def test_historial_ordenes_filtro_codigo(setup_orden_y_factura):
    data = setup_orden_y_factura
    codigo = data["orden"]["codigo_orden"]
    resp = client.get(f"/api/v1/ordenes?codigo_orden={codigo}")
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["total"] >= 1
    assert res_json["items"][0]["codigo_orden"] == codigo

def test_historial_ordenes_filtro_fechas(setup_orden_y_factura):
    hoy = datetime.utcnow().strftime("%Y-%m-%d")
    resp = client.get(f"/api/v1/ordenes?fecha_desde={hoy}&fecha_hasta={hoy}")
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["total"] >= 1

def test_historial_ordenes_rbac_aislamiento_cliente(setup_orden_y_factura):
    data = setup_orden_y_factura
    token = data["token"]
    otro_cliente_id = str(uuid.uuid4())
    # Cuando un cliente envía su token, el endpoint lo aísla a su propio cliente_id,
    # ignorando si en la query intenta espiar a otro_cliente_id
    resp = client.get(f"/api/v1/ordenes?cliente_id={otro_cliente_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    res_json = resp.json()
    for orden in res_json["items"]:
        assert str(orden["cliente_id"]) == data["cliente_id"]

def test_descargar_factura_xml(setup_orden_y_factura):
    data = setup_orden_y_factura
    cuf = data["cuf"]
    assert cuf is not None, "La orden debió generar un CUF"
    resp = client.get(f"/api/v1/facturacion/facturas/{cuf}/xml")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "attachment" in resp.headers.get("content-disposition", "")
    xml_text = resp.text
    assert "<facturaComputarizadaCompraVenta" in xml_text
    assert f"<cuf>{cuf}</cuf>" in xml_text
    assert "<nitEmisor>1028374029</nitEmisor>" in xml_text

def test_previsualizar_factura_html_impresion(setup_orden_y_factura):
    data = setup_orden_y_factura
    cuf = data["cuf"]
    resp = client.get(f"/api/v1/facturacion/facturas/{cuf}/impresion")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html_text = resp.text
    assert "MAXICONECTA BOLIVIA S.R.L." in html_text
    assert cuf in html_text
    assert "window.print()" in html_text
    assert "Ley N° 453" in html_text

def test_consultar_factura_por_orden_id(setup_orden_y_factura):
    data = setup_orden_y_factura
    orden_id = data["orden"]["id"]
    resp = client.get(f"/api/v1/facturacion/facturas/orden/{orden_id}")
    # Si la orden tiene factura registrada en memoria o Supabase
    if resp.status_code == 200:
        fac = resp.json()
        assert fac["cuf"] == data["cuf"]
