import asyncio
import pathlib
import sys
import uuid
from typing import Any, Dict

ROOT = pathlib.Path(__file__).resolve().parents[1]
POS_PATH = str(ROOT / "services" / "pos")
for module_name in ("app.schemas", "app.routers", "app"):
    sys.modules.pop(module_name, None)
sys.path.insert(0, POS_PATH)

from backend.services.pos.app import routers as pos_routers


def _emitir_venta_pos(
    monkeypatch,
    respuesta_fiscal: Dict[str, Any],
    *,
    modalidad: str = "con_factura",
    nit_ci: str = "1020304050",
    razon_social: str = "EMPRESA DE PRUEBA S.A.",
):
    solicitud_fiscal: Dict[str, Any] = {}

    async def obtener_caja(caja_id):
        return {"id": str(caja_id), "estado": "abierta", "cajero_id": str(uuid.uuid4())}

    async def acumular_venta(caja_id, metodo, monto):
        return None

    async def descontar_stock(items, orden_id, **kwargs):
        return {"status": "DESCONTADO"}

    async def procesar_cobro(monto, metodo, moneda="BOB", **kwargs):
        return {"estado": "aprobado", "transaccion_id": "TX-TEST-001"}

    async def emitir_factura(datos_fiscales):
        solicitud_fiscal.update(datos_fiscales)
        return respuesta_fiscal

    async def publicar_evento(evento):
        return {"publicado": True}

    monkeypatch.setattr(pos_routers, "obtener_caja", obtener_caja)
    monkeypatch.setattr(pos_routers, "acumular_venta", acumular_venta)
    monkeypatch.setattr(pos_routers.inventarios_client, "descuento_directo", descontar_stock)
    monkeypatch.setattr(pos_routers.pagos_client, "procesar_cobro", procesar_cobro)
    monkeypatch.setattr(pos_routers.pagos_client, "emitir_factura", emitir_factura)
    monkeypatch.setattr(pos_routers, "publicar_order_paid_event", publicar_evento)

    payload = pos_routers.VentaPOSRequest(
        caja_id=uuid.uuid4(),
        sucursal_id=uuid.uuid4(),
        cliente_nit_ci=nit_ci,
        cliente_razon_social=razon_social,
        modalidad=modalidad,
        tipo_documento="NIT",
        email_facturacion="facturacion@example.com",
        guardar_perfil=True,
        metodo_pago="tarjeta",
        items=[
            {"variante_id": uuid.uuid4(), "sku": "SKU-1", "nombre": "Producto uno", "cantidad": 2, "precio_unitario": 100},
            {"variante_id": uuid.uuid4(), "sku": "SKU-2", "nombre": "Producto dos", "cantidad": 1, "precio_unitario": 50},
        ],
    )
    user_id = str(uuid.uuid4())
    current_user = {
        "user_id": user_id,
        "role": "cajero",
        "payload": {"sub": user_id, "role": "cajero"},
    }
    respuesta = asyncio.run(pos_routers.procesar_venta_pos(payload, current_user=current_user))
    return respuesta, solicitud_fiscal


def test_ticket_pos_datos_fiscales_y_respuesta_erp_anidada(monkeypatch):
    respuesta, solicitud = _emitir_venta_pos(monkeypatch, {
        "mensaje": "Factura autorizada",
        "factura": {
            "numero_factura": 10099,
            "cuf": "CUF-TEST-TRIBUTARIO",
            "cufd": "CUFD-TEST",
            "estado": "timbrada",
            "codigo_qr": "https://siat.example/consulta?cuf=CUF-TEST-TRIBUTARIO",
        },
    })

    assert solicitud["modalidad"] == "con_factura"
    assert solicitud["tipo_documento"] == "NIT"
    assert solicitud["email_facturacion"] == "facturacion@example.com"
    assert len(solicitud["items"]) == 2
    assert solicitud["monto_iva"] == 28.76
    assert respuesta.factura_estado == "autorizada"
    assert respuesta.numero_factura == 10099
    assert respuesta.cuf == "CUF-TEST-TRIBUTARIO"
    assert respuesta.qr_url.startswith("https://siat.example/")
    assert "Producto uno" in respuesta.ticket_impresion
    assert "Factura No: 10099" in respuesta.ticket_impresion


def test_ticket_pos_erp_caido_entrega_comprobante_pendiente(monkeypatch):
    respuesta, _ = _emitir_venta_pos(monkeypatch, {
        "numero_factura": None,
        "cuf": None,
        "estado": "pendiente",
        "modo": "fallback",
    })

    assert respuesta.factura_estado == "pendiente"
    assert respuesta.numero_factura is None
    assert respuesta.cuf is None
    assert respuesta.qr_url is None
    assert respuesta.qr_code is None
    assert "PENDIENTE DE AUTORIZACIÓN" in respuesta.ticket_impresion
    assert "CUF:" not in respuesta.ticket_impresion


def test_ticket_pos_no_confia_en_cuf_sin_estado_de_autorizacion(monkeypatch):
    respuesta, _ = _emitir_venta_pos(monkeypatch, {
        "numero_factura": 10100,
        "cuf": "CUF-SIN-ESTADO",
    })

    assert respuesta.factura_estado == "pendiente"
    assert respuesta.numero_factura is None
    assert respuesta.cuf is None


def test_ticket_pos_normaliza_consumidor_final(monkeypatch):
    _, solicitud = _emitir_venta_pos(
        monkeypatch,
        {"numero_factura": 10101, "cuf": "CUF-CF", "estado": "timbrada"},
        nit_ci="0",
        razon_social="CONSUMIDOR FINAL",
    )

    assert solicitud["modalidad"] == "sin_factura"
    assert solicitud["nit_ci"] == "0"
    assert solicitud["razon_social"] == "CONSUMIDOR FINAL"
