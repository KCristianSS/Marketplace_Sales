from fastapi.testclient import TestClient

from backend.services.catalogo.app.main import app as catalogo_app

client = TestClient(catalogo_app)


def test_recomendados_por_producto_devuelve_cross_sell_y_bundle():
    productos = client.get("/api/v1/catalogo/productos").json()
    productos = productos.get("productos", productos) if isinstance(productos, dict) else productos
    assert productos, "El catálogo de prueba debe tener productos"

    resp = client.get(f"/api/v1/catalogo/productos/{productos[0]['id']}/recomendados")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, dict), "El frontend espera un objeto, no una lista plana"
    assert "recomendaciones" in data
    assert "frecuentemente_comprados_juntos" in data
