import pathlib
import sys
import uuid

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "ordenes"))

from backend.services.ordenes.app.main import app
from backend.shared.security import create_access_token


def _token(cliente_id: str, role: str) -> dict[str, str]:
    value = create_access_token({"sub": cliente_id, "user_id": cliente_id, "email": f"{role}@test.bo", "role": role})
    return {"Authorization": f"Bearer {value}"}


def _crear_orden(client: TestClient, cliente_id: str, producto_id: str) -> dict:
    response = client.post("/api/v1/ordenes/", json={
        "cliente_id": cliente_id,
        "canal": "web",
        "tipo_despacho": "retiro_sucursal",
        "subtotal": 100,
        "total": 100,
        "items": [{
            "variante_id": producto_id,
            "sku": f"SKU-{producto_id[:8]}",
            "nombre_producto": "Producto entregado",
            "cantidad": 1,
            "precio_unitario": 100,
        }],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _marcar_entregada(client: TestClient, orden_id: str, headers: dict[str, str]) -> None:
    for state in ("en_preparacion", "despachada", "entregada"):
        response = client.patch(f"/api/v1/ordenes/{orden_id}/estado", headers=headers, json={"nuevo_estado": state})
        assert response.status_code == 200, response.text


def _router_globals():
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/ordenes/resenas")
    endpoint = route.endpoint
    return getattr(endpoint, "__wrapped__", endpoint).__globals__


def test_solo_cliente_con_orden_entregada_puede_enviar_y_publicar_resena(monkeypatch):
    async def noop(*_args, **_kwargs):
        return {"status": "ok"}

    router_globals = _router_globals()
    monkeypatch.setitem(router_globals, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(router_globals["contabilidad_client"], "registrar_asiento_venta", noop)
    client = TestClient(app)
    cliente_id = str(uuid.uuid4())
    producto_id = str(uuid.uuid4())
    cliente_headers = _token(cliente_id, "cliente")
    otro_headers = _token(str(uuid.uuid4()), "cliente")
    admin_headers = _token(str(uuid.uuid4()), "administrador")
    orden = _crear_orden(client, cliente_id, producto_id)
    elegibles_path = f"/api/v1/ordenes/resenas/elegibles/{producto_id}"
    payload = {
        "producto_id": producto_id,
        "orden_id": orden["id"],
        "calificacion": 5,
        "comentario": "El producto llegó en perfecto estado.",
    }

    assert client.get(elegibles_path, headers=cliente_headers).json() == []
    assert client.post("/api/v1/ordenes/resenas", headers=cliente_headers, json=payload).status_code == 403

    _marcar_entregada(client, orden["id"], admin_headers)
    eligible = client.get(elegibles_path, headers=cliente_headers)
    assert eligible.status_code == 200
    assert eligible.json()[0]["orden_id"] == orden["id"]
    assert client.post("/api/v1/ordenes/resenas", headers=otro_headers, json=payload).status_code == 403

    submitted = client.post("/api/v1/ordenes/resenas", headers=cliente_headers, json=payload)
    assert submitted.status_code == 201, submitted.text
    review_id = submitted.json()["id"]
    assert submitted.json()["estado_moderacion"] == "pendiente"
    assert client.get(f"/api/v1/ordenes/resenas/producto/{producto_id}").json() == []
    assert client.post("/api/v1/ordenes/resenas", headers=cliente_headers, json=payload).status_code == 409

    pending = client.get("/api/v1/ordenes/resenas/pendientes", headers=admin_headers)
    assert pending.status_code == 200
    assert any(item["id"] == review_id for item in pending.json())

    rejected = client.patch(f"/api/v1/ordenes/resenas/{review_id}/moderacion", headers=admin_headers, json={"accion": "rechazar"})
    assert rejected.status_code == 422
    approved = client.patch(f"/api/v1/ordenes/resenas/{review_id}/moderacion", headers=admin_headers, json={"accion": "aprobar"})
    assert approved.status_code == 200
    assert approved.json()["estado_moderacion"] == "aprobada"
    public = client.get(f"/api/v1/ordenes/resenas/producto/{producto_id}")
    assert public.status_code == 200
    assert len(public.json()) == 1


def test_rechazo_deja_resena_oculta_y_guarda_motivo(monkeypatch):
    async def noop(*_args, **_kwargs):
        return {"status": "ok"}

    router_globals = _router_globals()
    monkeypatch.setitem(router_globals, "get_supabase_admin_client", lambda: None)
    monkeypatch.setattr(router_globals["contabilidad_client"], "registrar_asiento_venta", noop)
    client = TestClient(app)
    cliente_id = str(uuid.uuid4())
    producto_id = str(uuid.uuid4())
    cliente_headers = _token(cliente_id, "cliente")
    admin_headers = _token(str(uuid.uuid4()), "administrador")
    orden = _crear_orden(client, cliente_id, producto_id)
    _marcar_entregada(client, orden["id"], admin_headers)
    submitted = client.post("/api/v1/ordenes/resenas", headers=cliente_headers, json={
        "producto_id": producto_id,
        "orden_id": orden["id"],
        "calificacion": 1,
        "comentario": "No cumplió mis expectativas.",
    })
    review_id = submitted.json()["id"]

    rejected = client.patch(f"/api/v1/ordenes/resenas/{review_id}/moderacion", headers=admin_headers, json={
        "accion": "rechazar",
        "motivo": "Comentario no relacionado con el producto.",
    })
    assert rejected.status_code == 200
    assert rejected.json()["estado_moderacion"] == "rechazada"
    assert rejected.json()["motivo_rechazo"] == "Comentario no relacionado con el producto."
    assert client.get(f"/api/v1/ordenes/resenas/producto/{producto_id}").json() == []
