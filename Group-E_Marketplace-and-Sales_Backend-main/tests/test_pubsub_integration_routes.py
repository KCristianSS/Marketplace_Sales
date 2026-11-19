import uuid

from fastapi.testclient import TestClient

from backend.services.ordenes.app import routers as ordenes_routers
from backend.services.ordenes.app.main import app
from backend.shared.security import create_access_token


client = TestClient(app)


def test_admin_puede_publicar_reintegro_desde_integracion_pubsub():
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "administrador"})

    response = client.post(
        "/api/v1/ordenes/integraciones/pubsub/reintegro-stock",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "orden_id": "ORD-UI-TEST-1",
            "motivo": "prueba de integración",
            "origen": "marketplace",
            "sucursal_id": "SUC-LP-CENTRAL",
            "items": [{"sku": "SKU-TEST", "nombre": "Producto de prueba", "cantidad": 2}],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["evento"]["status"] == "FALLBACK_OFFLINE"
    assert body["evento"]["topic"] == "projects/project-a96e5fe1-5ba6-4698-a85/topics/ucb-sis323-sub-e"
    assert body["evento"]["payload"]["tipo_movimiento"] == "REINTEGRO_DEVOLUCION"
    assert body["evento"]["payload"]["items"][0]["sku"] == "SKU-TEST"


def test_cliente_no_puede_usar_pantalla_de_integracion_pubsub():
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "cliente"})

    response = client.get(
        "/api/v1/ordenes/integraciones/pubsub/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_estado_pubsub_informa_credenciales_ausentes():
    token = create_access_token({"sub": str(uuid.uuid4()), "role": "gerente_comercial"})

    response = client.get(
        "/api/v1/ordenes/integraciones/pubsub/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["hasCredentialsFile"] is False
    assert response.json()["mode"] == "OFFLINE"