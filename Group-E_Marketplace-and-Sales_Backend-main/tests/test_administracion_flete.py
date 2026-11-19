import asyncio
from copy import deepcopy
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.shared import flete_config, redis_client
from backend.shared.security import create_access_token
from backend.services.ordenes.app.main import app
from backend.services.ordenes.app import routers_pagos

URL = "/api/v1/ordenes/flete"


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(flete_config, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(flete_config, "_MEMORIA", None)
    monkeypatch.setattr(redis_client, "_redis_unavailable", True)
    monkeypatch.setattr(redis_client, "_in_memory_store", {})
    return TestClient(app)


def headers(rol="administrador"):
    token = create_access_token({"sub": "admin-envios", "role": rol})
    return {"Authorization": f"Bearer {token}"}


def editar(client):
    data = client.get(f"{URL}/configuracion", headers=headers()).json()
    return {"version": data["version"], "configuracion": data["configuracion"]}


def cotizar(client, **cambios):
    return client.post(f"{URL}/calcular", json={"ciudad": "La Paz", "zona": "Centro", **cambios})


def test_configuracion_exige_autenticacion_y_rol(admin):
    assert admin.get(f"{URL}/configuracion").status_code == 401
    assert admin.put(f"{URL}/configuracion", json={}).status_code == 401
    assert admin.get(f"{URL}/configuracion", headers=headers("cliente")).status_code == 403
    payload = editar(admin)
    assert admin.put(f"{URL}/configuracion", headers=headers("cajero"), json=payload).status_code == 403
    assert admin.put(f"{URL}/configuracion", headers=headers("gerente_comercial"), json=payload).status_code == 200
    assert admin.get(f"{URL}/opciones").status_code == 200


def test_rol_administrador_en_metadata_de_supabase(admin):
    token = create_access_token({"sub": "admin-supabase", "role": "authenticated", "app_metadata": {"role": "administrador"}})
    assert admin.get(f"{URL}/configuracion", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_administrador_actualiza_tarifa_recargos_plazos_y_promocion(admin):
    payload = editar(admin)
    config = payload["configuracion"]
    config.update(envio_gratis_habilitado=False, recargo_express=9, peso_incluido_kg=2, recargo_por_kg=4)
    config["zonas"][0].update(tarifa_base=30, plazo_express="Entrega en 8 horas hábiles")
    guardado = admin.put(f"{URL}/configuracion", headers=headers(), json=payload)
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["version"] == payload["version"] + 1
    assert guardado.json()["actualizado_por"] == "admin-envios"
    tarifa = cotizar(admin, tipo_envio="express_mismo_dia", peso_estimado_kg=7, subtotal_productos=1000)
    assert tarifa.status_code == 200
    assert float(tarifa.json()["costo_flete"]) == 59  # 30 + (7 - 2) * 4 + 9
    assert tarifa.json()["flete_gratis"] is False
    assert tarifa.json()["tiempo_estimado"] == "Entrega en 8 horas hábiles"


def test_envio_gratis_usa_umbral_administrado(admin):
    payload = editar(admin)
    payload["configuracion"]["umbral_envio_gratis"] = 200
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 200
    assert cotizar(admin, subtotal_productos=199.99).json()["flete_gratis"] is False
    assert cotizar(admin, subtotal_productos=200).json()["flete_gratis"] is True


def test_nueva_ciudad_cobertura_y_modalidades(admin):
    payload = editar(admin)
    nueva = {**payload["configuracion"]["zonas"][0], "id": str(uuid.uuid4()), "ciudad": "Potosí", "nombre": "Centro",
             "tarifa_base": 45, "express_habilitado": False}
    payload["configuracion"]["zonas"].append(nueva)
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 200
    opciones = admin.get(f"{URL}/opciones").json()
    assert any(z["ciudad"] == "Potosí" for z in opciones["zonas"])
    assert "actualizado_por" not in opciones
    assert cotizar(admin, ciudad="Potosí", zona="Centro").status_code == 200
    assert cotizar(admin, ciudad="Potosí", zona="Centro", tipo_envio="express_mismo_dia").status_code == 422
    payload = editar(admin)
    payload["configuracion"]["zonas"][-1]["activa"] = False
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 200
    assert not any(z["ciudad"] == "Potosí" for z in admin.get(f"{URL}/opciones").json()["zonas"])
    assert cotizar(admin, ciudad="Potosí", zona="Centro").status_code == 422


@pytest.mark.parametrize("cambio", ["duplicada", "tarifa_negativa", "sin_modalidad", "plazo_vacio"])
def test_rechaza_reglas_invalidas_sin_guardar(admin, cambio):
    payload = editar(admin)
    zona = payload["configuracion"]["zonas"][0]
    if cambio == "duplicada":
        payload["configuracion"]["zonas"].append({**zona, "id": str(uuid.uuid4()), "nombre": zona["nombre"].upper()})
    elif cambio == "tarifa_negativa":
        zona["tarifa_base"] = -1
    elif cambio == "sin_modalidad":
        zona.update(estandar_habilitado=False, express_habilitado=False)
    else:
        zona["plazo_estandar"] = "  "
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 422
    assert editar(admin)["version"] == 1


def test_evitar_sobrescribir_cambios_de_otro_administrador(admin):
    primero = editar(admin)
    segundo = deepcopy(primero)
    primero["configuracion"]["recargo_express"] = 50
    segundo["configuracion"]["recargo_express"] = 99
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=primero).status_code == 200
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=segundo).status_code == 409
    assert float(editar(admin)["configuracion"]["recargo_express"]) == 50


def test_cotizacion_emitida_se_respeta_tras_cambio_de_reglas(admin, monkeypatch):
    async def erp_stub(**kwargs):
        return {"status": "OK"}

    monkeypatch.setattr(routers_pagos.pagos_client, "procesar_cobro", erp_stub)
    monkeypatch.setattr(routers_pagos, "_get_supabase_safe", lambda: None)
    monkeypatch.setattr(routers_pagos, "_transacciones_cache", {})
    asyncio.run(redis_client.crear_reserva_stock("RES-REGLAS", "cliente-envios", [
        {"variante_id": str(uuid.uuid4()), "cantidad": 1, "precio_unitario": 100},
    ]))
    emitida = cotizar(admin, reserva_id="RES-REGLAS", direccion="Av. Arce 123").json()
    payload = editar(admin)
    payload["configuracion"]["zonas"][0]["activa"] = False
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 200
    assert cotizar(admin).status_code == 422
    pago = admin.post("/api/v1/pagos/iniciar", json={"cliente_id": "cliente-envios", "reserva_id": "RES-REGLAS",
        "metodo_pago": "qr", "monto": 115, "cotizacion_flete": emitida["cotizacion_flete"]})
    assert pago.status_code == 201, pago.text


def test_persistencia_y_control_de_version_en_base_datos(admin, monkeypatch):
    class BaseSimulada:
        def __init__(self):
            self.row = {"id": 1, "version": 1, "configuracion": flete_config.configuracion_inicial(),
                        "actualizado_por": None, "actualizado_en": None}

        def table(self, nombre):
            assert nombre == "flete_configuracion"
            base = self

            class Consulta:
                def __init__(self):
                    self.cambios = None
                    self.version = None

                def select(self, *args): return self
                def limit(self, *args): return self

                def update(self, cambios):
                    self.cambios = cambios
                    return self

                def eq(self, columna, valor):
                    if columna == "version": self.version = valor
                    return self

                def execute(self):
                    if self.cambios:
                        if self.version != base.row["version"]: return SimpleNamespace(data=[])
                        base.row.update(deepcopy(self.cambios))
                    return SimpleNamespace(data=[deepcopy(base.row)])

            return Consulta()

    base = BaseSimulada()
    monkeypatch.setattr(flete_config, "get_supabase_admin_client", lambda: base)
    payload = editar(admin)
    payload["configuracion"]["zonas"][0]["tarifa_base"] = 42
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 200
    monkeypatch.setattr(flete_config, "_MEMORIA", None)
    assert float(cotizar(admin).json()["costo_flete"]) == 42
    assert admin.get(f"{URL}/configuracion", headers=headers()).json()["almacenamiento"] == "base_datos"
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 409


def test_error_base_datos_no_reemplaza_reglas_con_valores_locales(admin, monkeypatch):
    class BaseNoDisponible:
        def table(self, nombre):
            raise RuntimeError("sin conexión")

    payload = editar(admin)
    monkeypatch.setattr(flete_config, "get_supabase_admin_client", lambda: BaseNoDisponible())
    assert admin.get(f"{URL}/opciones").status_code == 503
    assert cotizar(admin).status_code == 503
    assert admin.put(f"{URL}/configuracion", headers=headers(), json=payload).status_code == 503
